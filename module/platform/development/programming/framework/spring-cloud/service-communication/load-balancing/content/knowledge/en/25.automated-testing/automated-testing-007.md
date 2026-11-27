# Testing Bounded Retries and Actual Backend Receipt Counts

When `order-service` calls `catalog-service` through **Spring Cloud LoadBalancer**, the HTTP client or resilience layer may resend a request after a transient failure. Configuring "retry at most twice" sounds simple, yet tests that only verify the final response is HTTP 200 are insufficient. A request might attempt three times while hitting the backend handler only twice because one attempt failed to connect. Conversely, stacked retry layers can send far more requests to the backend than budgeted.

This lesson belongs to the **Automated Testing** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. We will separate a **business operation**, **HTTP attempts**, **LoadBalancer `ServiceInstance` selections**, requests **actually received by backends**, and **committed business side effects**. Next, we build an integration test with two real HTTP servers, a `@LoadBalanced RestClient`, controlled 503/400 errors, and counters inside the HTTP handlers. The final sections extend this to WebClient, OpenFeign, retries/timeouts, idempotency, and failure observability.

> Principle: **counting retries on the caller does not prove the backend received that many requests; counting backend receipts does not prove the business logic committed that many times**. Assert at the exact boundary the requirement intends to guarantee.

## 1. Five counts that must stay separate

| Count | Definition | Where to measure |
|---|---|---|
| **Logical operations** | Number of business intents from the caller | Business service entry point |
| **HTTP attempts** | Number of times the retry policy/HTTP transport tries to perform a request | Retry wrapper and client instrumentation |
| **Instance selections** | Number of times LoadBalancer looks up/picks a `ServiceInstance` | LoadBalancer lifecycle/tracing |
| **Backend received** | Number of requests actually entering the target instance's HTTP handler | Counter, access log, or stub server |
| **Business side effects** | Number of transactions/side effects actually completed | Database, ledger, outbox, or provider |

Example:

~~~text
logicalOperations = 1
maxAttempts       = 3
httpAttempts      = 3
lbSelections      = potentially 3, depending on retry layer
backendReceived   = 2, if one attempt failed before reaching the HTTP handler
businessWrites    = 0, if the request is a read-only GET
~~~

**Never treat `httpAttempts == backendReceived` as a universal invariant.** An attempt can fail before sending HTTP. A processed request can lose its response and trigger a caller retry. A gateway or transport may also retry internally without exposing each attempt to the caller.

Conventions used in this lesson:

- `maxAttempts = 3` means at most **three tries including the initial attempt**.
- `maxRetries = 2` means at most **two retries after the initial attempt**.
- **Received** in the lab is recorded when the server's handler is actually invoked.
- **Success** on the caller is recorded only when a contract-valid response arrives.

~~~mermaid
flowchart LR
    O["1 business operation"] --> A1["Attempt 1"]
    A1 -->|503| A2["Attempt 2"]
    A2 -->|503| A3["Attempt 3"]
    A3 -->|200| OK["Caller success"]
    A1 --> H["Backend received counter"]
    A2 --> H
    A3 --> H
~~~

In the scenario above, if all three attempts reach the handler, the backend counter must equal **3**. That conclusion applies to **the backend-generated 503 failure scenario**, not to every possible network error.

## 2. Which layers does a request pass through?

~~~mermaid
flowchart TD
    O["Business code calls catalog"] --> R["Retry policy / deadline"]
    R --> A["HTTP attempt n"]
    A --> LB{"LoadBalancer picks an instance?"}
    LB -->|No| NI["No-instance error: never enters backend"]
    LB -->|Yes| NET{"Connect & send HTTP succeed?"}
    NET -->|No| IO["Connect refused / TLS / network"]
    NET -->|Yes| HANDLER["Backend handler: received++"]
    HANDLER --> EXEC["Business processing, may commit"]
    EXEC --> RESP{"Response reaches caller on time?"}
    RESP -->|2xx| OK["Success"]
    RESP -->|503/429| RE["Eligible for retry if policy permits"]
    RESP -->|Timeout/lost response| UN["Outcome UNKNOWN if side effects exist"]
    NI --> RE
    IO --> RE
    RE --> R
~~~

`ServiceInstanceListSupplier` obtains candidates from discovery/cache/health; the selection policy chooses an instance. Only then does the HTTP client open a connection and send the request. Without an instance, no request enters the backend. On connection refused, no HTTP handler runs either. If the handler returns 503, the backend definitely received that request.

**LoadBalancer selections** and **HTTP transport attempts** may not map 1:1: some retry layers keep the old instance or execute below LoadBalancer. Therefore record both selected instances and total receipts across A and B rather than measuring only one variable.

## 3. Failure matrix and where to place assertions

| Failure window | Caller outcome | Is backend handler invoked? | Useful assertion |
|---|---|---|---|
| No instances | LoadBalancer error or synthetic response depending on integration | No | Backend count = 0 |
| Unlistening port | Connect exception/refused | No | Backend count = 0 |
| Handler returns HTTP 503 | Exception/status 503 | Yes | Counter increments once per received request |
| Handler returns 400 | Exception/status 400 | Yes | Counter = 1 if policy does not retry |
| Handler returns 503, 503, 200 | Succeeds after retries | Yes, all three | Total counter = 3 |
| Handler returns 503 continuously | Fails when budget exhausted | Yes, for every attempt reaching server | Count never exceeds lab `maxAttempts` |
| Server commits then response drops | Read timeout/reset | Yes | Counter may increment; commit count measured separately |
| WebClient unsubscribed | Zero I/O | No | Counter = 0 |
| Gateway retries internally | Caller may see one call | Backend may receive multiple | Counters at both gateway and backend |

Also distinguish a real HTTP `503` returned by the backend from a synthetic `503` generated at a gateway or LoadBalancer when no instance exists: **identical status codes do not imply identical origins**.

## 4. What must the test suite prove?

A bounded retry policy must satisfy all of the following:

1. **Recovery:** two `503`s followed by `200` succeed on the third attempt; backend receives exactly three requests when all three reach the handler.
2. **Termination:** backend constantly returns `503`; caller stops at `maxAttempts` without looping infinitely.
3. **No retry on ineligible errors:** `400`, `401`, `403`, or contract validation errors are not blindly resent.
4. **Distinguish pre-HTTP failures:** no-instance or connection-refused errors do not increment backend handler counts.
5. **No retry multiplication:** client, LoadBalancer, gateway, and service mesh layers do not collectively exceed the total budget.
6. **Write operations:** committed business side effects can remain 1 even when multiple requests are received.

Unit tests that merely mock `RestClient.get()` or `Mono.defer` prove how many times the wrapper retries, **not that real HTTP requests reached the server**.

## 5. Choosing test levels

| Level | Tools | What it proves | What it does not prove |
|---|---|---|---|
| Unit | Mockito, fake delegate, `Mono.defer` | Retry decisions, invocation counts | HTTP requests to backend |
| HTTP integration | JDK HttpServer, WireMock, MockWebServer | Method, path, status, handler count | LoadBalancer if client calls host directly |
| LoadBalancer integration | `@LoadBalanced` + discovery + 2 servers | Service ID, instance selection, total receipts | DB commits if only handler is mocked |
| End-to-end fault | Two processes, DB, gateway/fault proxy | Network failures and real side effects | Cannot cover every failure window in one run |

The lab below runs **JDK `HttpServer`** on two dynamic ports inside JUnit. Each server maintains a counter inside its handler, while the client retry wrapper tracks attempts independently. This gives stronger evidence than `verify(mock, times(3))`.

## 6. Designing a deterministic two-backend lab

Both HTTP servers expose `GET /api/items/42`:

~~~text
A: http://127.0.0.1:<dynamic port A>
B: http://127.0.0.1:<dynamic port B>

totalReceived = receivedA + receivedB
failFirst     = number of initial backend receipts returning 503
forcedStatus  = if non-zero, every receipt returns this status
~~~

When `failFirst = 2`:

~~~text
Backend request #1 -> 503
Backend request #2 -> 503
Backend request #3 -> 200, body "OK"
~~~

Use **dynamic ports** to avoid CI collisions. Do not assert that A specifically takes call #1 and B takes call #2, as that belongs to instance-selection policy and concurrency rather than retry requirements.

### Dependencies

Gradle example with a compatible Spring Boot/Spring Cloud BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`com.sun.net.httpserver.HttpServer` ships with the JDK; in projects using custom JPMS configurations, ensure the `jdk.httpserver` module is available.

> Code snippets in this lesson are instructional documentation. Per STEP 4, **Gradle/JUnit or the Content QA pass have not been executed here**; outcomes listed below are **scenario expectations**, not executed measurements.

## 7. An explicit retry wrapper that retries only 503

To keep test attempt counts unambiguous, use a single explicit retry policy outside `RestClient`. Disable LoadBalancer's automatic retries in the test configuration below.

~~~java
package demo.retry;

import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;

record CallResult(String body, int attempts) {}

final class BoundedCatalogCaller {

    private static final int MAX_ATTEMPTS = 3;
    private final RestClient client;

    BoundedCatalogCaller(RestClient client) {
        this.client = client;
    }

    CallResult fetchItem42() {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                String body = client.get()
                    .uri("/api/items/42")
                    .retrieve()
                    .body(String.class);

                return new CallResult(body, attempt);
            } catch (HttpServerErrorException.ServiceUnavailable ex) {
                // Retry only when HTTP status is 503.
                if (attempt == MAX_ATTEMPTS) {
                    throw ex;
                }
            }
        }

        throw new IllegalStateException("Unreachable");
    }
}
~~~

Design notes:

- `maxAttempts=3` means **one initial attempt plus at most two retries**.
- Catching applies only to HTTP 503 converted by `RestClient.retrieve()` into `HttpServerErrorException.ServiceUnavailable`.
- HTTP 400, decode errors, connection refused, or no-instance failures are **not** retried by this wrapper.
- No backoff is added so request-count tests do not depend on wall-clock sleeps. Production requires backoff/jitter, deadlines, and load shedding.
- The wrapper cannot know on its own how many requests the backend received; hence we measure separately on the servers.

This snippet is a **test policy**, not a recommendation to retry every 503 regardless of contracts and SLOs.

## 8. Starting two HTTP servers with handler-level counters

Create the test class `BoundedRetryTest`. Sections `9` and `10` are added **inside this same class**, not as separate classes.

~~~java
package demo.retry;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = BoundedRetryTest.TestApp.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.main.web-application-type=none",
        "spring.cloud.loadbalancer.retry.enabled=false"
    }
)
@Execution(ExecutionMode.SAME_THREAD)
class BoundedRetryTest {

    private static final AtomicInteger totalReceived =
        new AtomicInteger();

    private static final AtomicInteger receivedA =
        new AtomicInteger();

    private static final AtomicInteger receivedB =
        new AtomicInteger();

    private static volatile int failFirst;
    private static volatile int forcedStatus;

    private static final HttpServer serverA =
        startServer(receivedA);

    private static final HttpServer serverB =
        startServer(receivedB);

    private static HttpServer startServer(AtomicInteger localCounter) {
        try {
            HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

            server.createContext("/api/items/42", exchange -> {
                int ordinal = totalReceived.incrementAndGet();
                localCounter.incrementAndGet();

                int status = forcedStatus != 0
                    ? forcedStatus
                    : ordinal <= failFirst ? 503 : 200;

                byte[] body = (status == 200 ? "OK" : "ERROR")
                    .getBytes(StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");

                exchange.sendResponseHeaders(status, body.length);

                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }

                exchange.close();
            });

            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    // Continue with discovery, beans, and test methods below.
}
~~~

**Why place counters inside the handler:** `totalReceived.incrementAndGet()` executes only after the HTTP server accepts a request for the matching route; attempts that fail before reaching the backend do not increment the counter. `ordinal` is the sequence **actually received by handlers** in the lab, not the caller's self-reported attempt number.

Both servers share `totalReceived` in the same JVM to create a deterministic initial failure sequence. In production, independent replicas do not share a Java variable like this.

## 9. Registering two dynamic URIs in SimpleDiscoveryClient

Add these methods to `BoundedRetryTest`:

~~~java
@DynamicPropertySource
static void discovery(DynamicPropertyRegistry registry) {
    registry.add(
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
        () -> "http://127.0.0.1:" + serverA.getAddress().getPort()
    );

    registry.add(
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri",
        () -> "http://127.0.0.1:" + serverB.getAddress().getPort()
    );
}

@BeforeEach
void resetBackendState() {
    totalReceived.set(0);
    receivedA.set(0);
    receivedB.set(0);
    failFirst = 0;
    forcedStatus = 0;
}

@AfterAll
static void stopServers() {
    serverA.stop(0);
    serverB.stop(0);
}
~~~

`@DynamicPropertySource` injects properties into the Spring Test context before discovery beans initialize. `@Execution(ExecutionMode.SAME_THREAD)` prevents two test methods in the class from mutating shared counters concurrently if JUnit parallel execution is enabled.

Do not use fixed ports `18081` and `18082` here; CI runners may already occupy them. Do not call `Thread.sleep` just to wait for counters to change: the synchronous test waits for `RestClient`'s response or exception before asserting.

## 10. RestClient bean wired with Spring Cloud LoadBalancer

Add to the same `BoundedRetryTest` class:

~~~java
@Autowired
BoundedCatalogCaller caller;

@SpringBootConfiguration
@EnableAutoConfiguration
static class TestApp {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient catalogClient(
        @Qualifier("loadBalancedBuilder")
        RestClient.Builder builder
    ) {
        return builder.baseUrl("http://catalog-service").build();
    }

    @Bean
    BoundedCatalogCaller boundedCaller(RestClient catalogClient) {
        return new BoundedCatalogCaller(catalogClient);
    }
}
~~~

Thus the caller never talks to the dynamic ports directly. It sends requests to the service ID `catalog-service`, obtains instances from `SimpleDiscoveryClient`, and lets Spring Cloud LoadBalancer pick a real endpoint.

**Note on lab conditions:** `spring.cloud.loadbalancer.retry.enabled=false` is set on `@SpringBootTest` so Spring Cloud does not retry alongside the explicit loop. Ensure no hidden gateway or service-mesh retry exists during the test either. When running on a specific Spring version, verify the expected beans were auto-configured.

Never substitute `RestClient.create("http://catalog-service")` for the `@LoadBalanced` bean: that client will attempt DNS resolution on the logical name and bypass the module's supplier and LoadBalancer.

## 11. Three core automated tests

Place these methods **inside the same `BoundedRetryTest`**, reusing the declared state and beans.

### 11.1. Two 503s followed by success

~~~java
@Test
void retriesTwiceThenSucceedsWithThreeBackendReceipts() {
    failFirst = 2;

    CallResult result = caller.fetchItem42();

    assertThat(result.body()).isEqualTo("OK");
    assertThat(result.attempts()).isEqualTo(3);

    assertThat(totalReceived.get()).isEqualTo(3);
    assertThat(receivedA.get() + receivedB.get()).isEqualTo(3);
}
~~~

This test proves in this setup: one operation, three HTTP attempts, three actual backend receipts (not merely three mock calls), two `503` responses, and a final `200`.

### 11.2. Persistent errors must stop at attempt three

~~~java
@Test
void stopsAfterThreeAttemptsWhenBackendAlwaysReturns503() {
    failFirst = 100;

    assertThatThrownBy(caller::fetchItem42)
        .isInstanceOf(
            HttpServerErrorException.ServiceUnavailable.class
        );

    assertThat(totalReceived.get()).isEqualTo(3);
    assertThat(receivedA.get() + receivedB.get()).isEqualTo(3);
}
~~~

This test catches unbounded retries. Testing only "503, 503, 200" **will not catch** an infinite retry loop if the backend always succeeds on the third call.

### 11.3. HTTP 400 must not be retried

~~~java
@Test
void doesNotRetryBadRequest() {
    forcedStatus = 400;

    assertThatThrownBy(caller::fetchItem42)
        .isInstanceOf(HttpClientErrorException.BadRequest.class);

    assertThat(totalReceived.get()).isEqualTo(1);
}
~~~

HTTP 400 enters the handler once and is converted to an exception by `RestClient.retrieve()`. Our wrapper catches only 503, so it stops immediately.

| Test | Backend response sequence | Expected outcome | Backend received |
|---|---|---|---|
| Retry recovery | 503 → 503 → 200 | Success on attempt 3 | **3** |
| Budget exhausted | 503 → 503 → 503 | Throws 503 | **3** |
| Do not retry 400 | 400 | Throws 400 | **1** |

**These are expectations derived from the test configuration, not executed JUnit results from STEP 4.** Request counts reflect total receipts without asserting A/B order. Testing the Round Robin algorithm itself belongs in a separate test suite with controlled topology and concurrency.

## 12. No ServiceInstance: backend receives 0 requests

When `ServiceInstanceListSupplier` returns an empty list for a service ID, Spring Cloud LoadBalancer cannot route requests to the two lab servers. This is completely different from a backend returning HTTP 503.

~~~text
business operation      = 1
candidate instances     = 0
successful selection    = 0
backend received total  = 0
actual backend HTTP 503 = 0
~~~

In a separate test, you can build a `RestClient` from the **LoadBalancer-managed builder** targeting an unregistered service ID:

~~~java
// Illustrative snippet: inject the @LoadBalanced RestClient.Builder.
RestClient missingClient = loadBalancedBuilder
    .baseUrl("http://missing-service")
    .build();
~~~

Calling `missingClient.get().uri("/api/items/42")` will fail during instance resolution according to the specific integration; **do not hardcode that every version throws the exact same exception class**. Key assertions:

- Backends A and B receive **zero new requests**.
- Service ID `missing-service` has no candidates.
- The failure is classified as **no-instance**, not "the real catalog backend returned 503."

Some integrations represent no-instance with an exception or a synthetic error response generated at the LoadBalancer layer; a final HTTP status alone does not reveal the origin.

## 13. Connection refused: attempts can exceed receipts

Suppose a registry still lists replica B while B's process has stopped. If LoadBalancer selects B, TCP connect fails **before the HTTP handler is invoked**:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant LB as LoadBalancer
    participant A as Backend A
    participant B as Unlistening Port B

    C->>LB: Attempt 1
    LB-->>C: Picks B
    C-xB: TCP connect refused
    Note over B: HTTP handler received = 0
    C->>LB: Attempt 2 (if retried)
    LB-->>C: May pick A
    C->>A: GET /api/items/42
    A-->>C: 200 OK
    Note over C: Attempts = 2; backend received = 1
~~~

Never assert `backendReceived == maxAttempts` across every fault type. For stable tests, use a server or fault proxy whose port/connection lifecycle you control; do not assume a port that "looks free" on a CI machine won't be claimed by another process.

When instance B is down, a retry **may** select A if suppliers and retry policy permit it; there is no guarantee retries always switch to a different instance.

## 14. Spring Cloud LoadBalancer retry settings must be tested for real

Spring Cloud LoadBalancer exposes common properties:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 503
        retry-on-all-operations: false
~~~

**Do not apply this YAML inside the same test using `BoundedCatalogCaller` from Sections 7–11**: those tests already implement explicit retries and set `spring.cloud.loadbalancer.retry.enabled=false` to isolate a single layer.

| Property | Purpose |
|---|---|
| `retry.enabled` | Enables/disables LoadBalancer retry when compatible dependencies/integrations exist |
| `max-retries-on-same-service-instance` | Retries on the selected instance, with per-instance semantics |
| `max-retries-on-next-service-instance` | Retries that select a subsequent instance |
| `retryable-status-codes` | HTTP status codes eligible for retry |
| `retryable-exceptions` | Exception classes eligible for retry |
| `retry-on-all-exceptions` | Adjusts which exceptions trigger retries |
| `retry-on-all-operations` | Enables retries beyond GET; requires idempotency analysis |
| `retry.backoff.*` | Backoff and jitter in supporting integrations |

**Never compute backend requests using `1 + same + next`** without checking per-instance semantics, version details, and error conditions. An attempt may be rejected before reaching a backend; a request method may be ineligible for retry; a retry-aware supplier may pick the same or a different instance depending on remaining candidates.

Spring Cloud Commons documentation describes retry support for non-reactive `RestTemplate` with Spring Retry on the classpath and reactive retries for `WebClient`; RestClient, Feign, and transports have version-dependent integration rules. **Seeing `enabled=true` in YAML does not prove retries actually execute.**

When testing a real framework retry mechanism:

1. Pick **one HTTP client implementation** and a specific Spring Cloud release train.
2. Verify the dependencies and beans that actually activate retry.
3. Disable retries in all other layers to avoid multiplying attempts.
4. Make the backend deliberately return 503, then measure actual received requests.
5. Record the chosen instance per attempt if verifying same/next instance behavior.
6. Test statuses outside the allowlist, `POST` when `retry-on-all-operations=false`, and budget exhaustion.
7. Test both error responses and pre-response connection errors.

References: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html and https://docs.spring.io/spring-cloud-commons/reference/configprops.html.

## 15. Layered retries can multiply request counts

Suppose a business wrapper allows up to **3 attempts**, while the underlying HTTP client allows up to **2 sends per wrapper attempt**:

~~~text
business wrapper: up to 3 client calls
    each call: transport tries sending up to 2 times
    worst case under this assumption: 3 × 2 = 6 sends
~~~

~~~mermaid
flowchart TB
    O["1 operation"] --> W["Wrapper: max 3 client calls"]
    W --> C1["Client call #1"]
    W --> C2["Client call #2"]
    W --> C3["Client call #3"]
    C1 --> S1["Transport retries ≤ 2 sends"]
    C2 --> S2["Transport retries ≤ 2 sends"]
    C3 --> S3["Transport retries ≤ 2 sends"]
    S1 --> B["Backend"]
    S2 --> B
    S3 --> B
~~~

If a gateway or service mesh also retries, backend requests multiply further. At each layer, distinguish "retries" from "attempts," and include the initial attempt when counting total sends. In production, the actual multiplier also depends on error types and each layer's retry rules.

**A policy is safe only when total retry budget across the entire path is controlled**, not merely because each component has its own `maxRetries`. Tests asserting only a final 200 miss retry storms; backend-side counters catch them.

## 16. WebClient: retry subscriptions do not prove backend requests

With WebClient, `retryWhen` resubscribes when the publisher emits an eligible error.

Unit test checking subscription counts:

~~~java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.assertj.core.api.Assertions.assertThat;

class ReactorRetryUnitTest {

    @Test
    void retriesTwiceThenCompletes() {
        AtomicInteger subscriptions = new AtomicInteger();

        Mono<String> operation = Mono.defer(() -> {
            int attempt = subscriptions.incrementAndGet();

            if (attempt <= 2) {
                return Mono.error(
                    new IOException("temporary network failure")
                );
            }

            return Mono.just("OK");
        }).retryWhen(
            Retry.max(2)
                .filter(ex -> ex instanceof IOException)
        );

        StepVerifier.create(operation)
            .expectNext("OK")
            .verifyComplete();

        assertThat(subscriptions.get()).isEqualTo(3);
    }
}
~~~

**There is no HTTP in this example.** `subscriptions=3` proves only Reactor's resubscribe logic, not that three requests entered the backend.

To verify real communication, call the two lab servers with a `@LoadBalanced WebClient`, disable other framework retries, and attach:

~~~java
Mono<String> result = catalogWebClient.get()
    .uri("http://catalog-service/api/items/42")
    .retrieve()
    .bodyToMono(String.class)
    .retryWhen(
        Retry.max(2).filter(error ->
            error instanceof
                org.springframework.web.reactive.function.client
                    .WebClientResponseException.ServiceUnavailable
        )
    );
~~~

After `StepVerifier.create(result).expectNext("OK").verifyComplete()`, inspect backend counters. The "503, 503, 200" sequence on the test servers ties subscriptions to **real requests**. Note that a resubscription does not guarantee the retry goes to a different instance.

With `Mono.timeout`, the signal may be `TimeoutException` rather than `WebClientResponseException`. Tests must match the actual error emitted by the connector. If never subscribed, WebClient sends nothing; reading counters before subscribing sees 0.

## 17. OpenFeign: verify the active Retryer and ErrorDecoder

Example interface:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {
    @GetMapping("/api/items/42")
    String getItem42();
}
~~~

Spring Cloud OpenFeign may default to `Retryer.NEVER_RETRY` in several release trains, unlike core Feign defaults. A custom `ErrorDecoder` can also convert HTTP 503 into another exception type and alter retry eligibility.

Therefore Feign tests must:

- Confirm the `Retryer` applies to the right client/service ID.
- Confirm the actual HTTP transport (HC5, OkHttp, or another transport).
- Verify 503 responses follow the intended retry path.
- Count actual requests on backends A and B rather than only verifying Feign proxy invocations.
- Verify HTTP 400 or 404 is not mistakenly retried.
- Distinguish Feign with a fixed `url` (which can bypass LB) from `name` using a service ID.
- Disable external retry wrappers around Feign when measuring `Retryer` in isolation.

You cannot conclude "Feign retries three times automatically" from `@FeignClient` alone. Request counts require proof at the backend stubs.

## 18. HTTP 429, Retry-After, and overall deadlines

HTTP status is only one input; do not retry every status identically.

| Response or failure | What to test | Significance |
|---|---|---|
| Transient 503 | 503, 503, 200 | Recovers within budget |
| Continuous 503 | Repeated 503s | Stops at max attempts |
| 429 + `Retry-After` | 429, then 200 | Respects wait header and deadline |
| 400/401/403 | Single response | Never blindly retries identical bad inputs/credentials |
| Contract 404 | Single response | Missing resource or wrong route |
| 409 idempotency conflict | Single response | Fix key/body usage rather than retrying |
| 500 after side effect | Error response | May have committed; outcome needs verification |
| Read timeout | Incomplete response | May require UNKNOWN handling for POST |

If `Retry-After` is 120 seconds while the caller's deadline has 2 seconds left, the policy must stop or return an appropriate status instead of waiting past the SLO.

Actual attempts may be **fewer than `maxAttempts`** due to an overall deadline or circuit breaker. Limit tests should assert **never exceeding the cap**, without forcing every error to exhaust all attempts.

## 19. Timeout after backend commit: separating receipts from side effects

For write operations like a POST creating a reservation, the backend can commit successfully before the response is lost. The caller sees only a timeout and may retry onto another instance.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant LB as LoadBalancer
    participant A as Instance A
    participant DB as Shared DB
    participant B as Instance B

    C->>LB: POST operation K, attempt 1
    LB-->>C: Picks A
    C->>A: Idempotency-Key=K
    A->>DB: COMMIT reservation #101
    A--xC: Response lost
    Note over C: Outcome UNKNOWN
    C->>LB: Retry same K, attempt 2
    LB-->>C: May pick B
    C->>B: POST key=K
    B->>DB: Look up shared key K
    DB-->>B: Already COMMITTED #101
    B-->>C: Return receipt #101
~~~

Assertions that must stay separate:

~~~text
logicalOperations = 1
httpAttempts      = actual tries attempted
backendReceived   = sum of handler invocations across replicas
businessWrites(K) = 1
idempotencyKey    = same K on every attempt
~~~

**The backend receiving two POSTs does not mean two records were created.** Conversely, if each instance keeps only an in-memory map, retrying to another instance can create two records. To prove multi-replica idempotency, tests must use a shared durable store with a unique constraint/transaction or equivalent mechanism.

A read timeout, connection reset, or HTTP 504 never proves the server rolled back. When the outcome is unknown, query status using the operation ID/key before issuing a new business intent.

## 20. Two instances: verify total count first, distribution second

Suppose:

~~~text
receivedA = 2
receivedB = 1
total     = 3
~~~

When the goal is **retry budget**, the essential lab assertion is `total=3`. Asserting `A=2, B=1` should not be a rigid requirement when selectors, instance health, retry-aware suppliers, or concurrency can vary the order.

When the dedicated goal is testing **Round Robin**, fix candidate lists, health states, caller counts, and execution order. That belongs to an **instance-selection algorithm suite**, never mixed into retry tests.

When retries can switch instances, sum counters across **all selectable replicas**, not just the first server. If gateways or sidecars sit in front of backends, measure at each hop to see how far requests traveled.

## 21. WireMock, MockWebServer, and fault proxies

JDK `HttpServer` creates a self-contained lab; real projects can choose:

- **WireMock:** scenarios `503 → 503 → 200`, verifying exact counts per HTTP path/method/header received by the stub server.
- **MockWebServer:** enqueue responses and inspect `RecordedRequest`; great for exact request inspection.
- **Testcontainers:** run real backends, registries, and databases close to deployment topology for cross-process tests.
- **Toxiproxy** or an equivalent fault proxy: inject controlled connect failures, latency, resets, or dropped responses.

Example once a `WireMockServer` is running and stubbed for the endpoint:

~~~java
// Illustrative DSL: requires WireMock dependencies and imports.
wireMock.verify(
    3,
    getRequestedFor(urlEqualTo("/api/items/42"))
);
~~~

This count proves **WireMock received three GETs to that path**. If the caller hits WireMock's URL directly, it **does not prove** LoadBalancer selected an instance by service ID; pair it with an integration test via `@LoadBalanced` or Feign.

## 22. Observability: operation ID and attempt ID

One operation must be traceable across attempts and instances:

| Field | Meaning | Source |
|---|---|---|
| `operationId` | One business intent | Caller |
| `attemptNumber` | Which attempt | Retry wrapper |
| `serviceId` | Downstream logical service | LB |
| `selectedInstance` | Chosen instance | LB/trace |
| `retryReason` | Condition triggering retry | Retry policy |
| `httpStatus` | Received response status | Client/backend |
| `exceptionCause` | Connect, timeout, decode, etc. | Client |
| `backendReceivedAt` | When handler received request | Backend |
| `sideEffectId` | Committed transaction/result | DB/ledger |
| `remainingDeadlineMs` | Remaining budget | Caller |
| `dedupOutcome` | NEW/REPLAY/CONFLICT | Backend idempotency |

Desired log example:

~~~text
caller op=op42 attempt=1 service=catalog-service selected=A
backend-A op=op42 received=true status=503
caller op=op42 retry=1 reason=HTTP_503
caller op=op42 attempt=2 service=catalog-service selected=B
backend-B op=op42 received=true status=503
caller op=op42 retry=2 reason=HTTP_503
caller op=op42 attempt=3 service=catalog-service selected=A
backend-A op=op42 received=true status=200
caller op=op42 outcome=SUCCESS attempts=3
~~~

This is an illustrative format, not Spring Cloud LoadBalancer's default log format. Never put raw operation IDs or idempotency keys into high-cardinality metric tags; use controlled logs/traces and aggregate metrics by service, status, and retry reason. Never log `Authorization` headers or sensitive payloads.

## 23. Common retry-testing mistakes

1. Asserting only final 200 without counting actual backend receipts.
2. Counting mock invocations and treating them as HTTP requests.
3. Counting on only one instance when LoadBalancer can switch instances.
4. Enabling retries simultaneously in wrappers, LoadBalancer, Feign, gateways, and meshes.
5. Confusing `maxAttempts` with `maxRetries`, being off by one send.
6. Hardcoding A/B order even though topology/concurrency is unlocked.
7. Triggering connection refused while expecting backend handler counts to rise.
8. Skipping persistent-503 tests, missing unbounded retry loops.
9. Retrying all HTTP 4xx statuses, including validation, auth, and conflict errors.
10. Using `Thread.sleep` or fixed ports, making CI tests flaky.
11. Failing to reset/isolate counters between tests or running parallel tests over shared state.
12. Testing POST retries without counting business writes.
13. Generating a fresh idempotency key on every retry of the same operation.
14. Omitting an overall deadline, allowing total latency to multiply across attempts.
15. Confusing no-instance errors with backend- or gateway-emitted 503s.
16. Forgetting to subscribe to a `Mono`, leaving WebClient sending zero requests.
17. Measuring requests only at a gateway rather than the final backend.
18. Letting health probes pollute request counters without filtering by path/method.
19. Failing to inspect the actual retry configuration of the active client/version.
20. Having no test timeout to stop a hung server or fault proxy.

## 24. Pre-CI test checklist

- Clearly define **one business operation**, one attempt, and total permitted retries.
- Verify success-on-first-attempt, 503-then-success, persistent 503, and no-retry on 400.
- Assert **server handler counts** for backend-generated 503s.
- Separate caller attempts, LB selections, backend receipts, and business writes where needed.
- Disable retry layers outside test scope or enforce a single shared system budget.
- Ensure clients call **the service ID via LoadBalancer** rather than bypassing it with direct URLs.
- Use dynamic ports, isolated test state, and no arbitrary sleeps/timing assumptions.
- Inject the exact fault needed: connect failure, response timeout, HTTP status, or no-instance.
- For POST, reuse the same idempotency key across attempts and verify side effects commit per contract.
- For WebClient, ensure subscription and awaited completion; for Feign, verify `Retryer`/`ErrorDecoder`.
- Across multi-instance topologies, sum backend counters across all instances.
- Capture safe log/trace correlation, retry reasons, selected instances, and timeout causes.
- Configure timeouts on the test runner itself so a failure never hangs CI.
- Label assertions accurately as **requests received by backend handlers**, not vague "sends."

## 25. Summary

**Proper retry testing goes beyond seeing a final successful response.** Tests must prove the policy **stops at budget exhaustion**, **retries only eligible failures**, and checks **actual HTTP receipts on backends** at the right boundary. The `BoundedRetryTest` lab uses two HTTP servers, controlled `503` failures, and handler counters to verify deterministic behavior: **503 → 503 → 200** yields three actual backend receipts, **persistent 503** stops after three attempts, and **400** hits the backend only once.

With Spring Cloud LoadBalancer, an attempt can fail during discovery, `ServiceInstance` selection, or transport before ever reaching a server. `RestClient`, `WebClient`, and OpenFeign differ in retry and exception mechanics, so test real integrations, avoid stacked retry multiplication, and separate **received requests** from **committed side effects** for writes. Only with clear evidence across **logical operations, HTTP attempts, LoadBalancer selections, backend receipts, and business outcomes** can retries act as a reliability mechanism rather than a source of overload or duplicate writes.

## References

- Spring Cloud Commons – Common Abstractions / Retrying Failed Requests: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud Commons – Configuration Properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Cloud Commons – LoadBalancer: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Framework – RestClient: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Reactor Core – Error Handling / Retry: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
