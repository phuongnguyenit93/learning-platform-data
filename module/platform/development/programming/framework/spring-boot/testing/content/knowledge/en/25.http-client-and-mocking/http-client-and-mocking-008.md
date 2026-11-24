# Spring Boot Testing: Fallbacks, Circuit Breakers, and Preventing Unintended Duplicate Calls

## 1. Problem statement and completion criteria

A Spring Boot application frequently calls an external HTTP service for quotes, shipping, payments, inventory checks, or user details. When upstream returns 503, drops connections, sends malformed responses, or stalls, multiple mechanisms can interact simultaneously: retries, circuit breakers, fallbacks, caches, and HTTP client middleware.

A test asserting only `result != null` is inadequate. It can PASS even when the app calls upstream three times instead of once, keeps calling while the circuit is OPEN, swallows 404 errors, or returns a fabricated fallback value that corrupts business logic.

This lesson requires verifying simultaneously:

1. **Outcome**: returns the real price or a clearly specified degraded state.
2. **Circuit breaker**: transitions CLOSED → OPEN → HALF_OPEN → CLOSED/OPEN under the configured rules.
3. **Remote attempts**: exact **actual HTTP request count**, including **zero calls** when blocked.
4. **Error classification**: 5xx/network faults, 4xx, invalid bodies, and programming bugs are never lumped together.
5. **Fallback/retry safety**: never issues duplicate requests outside policy or creates duplicate side effects.
6. **Test stability**: never depends on `Thread.sleep()`, live internet access, execution order, or leaked breaker state from earlier tests.

The example use case fetches product price `SKU-1` via `GET /prices/SKU-1`. If the vendor returns price 125.50, the app returns `REMOTE`. If the vendor is unavailable, the app returns `UNAVAILABLE` **with `amount=null`**—never fabricating price `0`. When the breaker is OPEN, new calls fall back **before sending HTTP**.

### Learning objectives

You will learn how to write tests with `RestClient`, `MockRestServiceServer`, and Resilience4j; assert exact request counts; understand failure rates, sliding windows, and half-open probes; verify 404 is never masked by fallbacks; know when to use WireMock/MockWebServer; spot double retries caused by Spring AOP + HTTP client stacking; and design timeouts, backoff, idempotency, and observability.

## 2. Distinguishing resilience mechanisms

| Mechanism | Primary role | What it does NOT guarantee by itself |
| --- | --- | --- |
| Fallback | Returns an alternate result or unavailable state | Does not reduce HTTP requests if upstream is still called |
| Circuit breaker | Rejects new calls when a dependency exceeds failure thresholds | Does not abort an already in-flight hanging HTTP attempt |
| Retry | Re-attempts transient failures within a cap | Does not prevent duplicate side effects |
| Timeout | Bounds wait time per client/operation | Does not substitute for fallback or retry |
| Bulkhead | Caps concurrent calls, isolating resources | Does not determine whether upstream is healthy |
| Rate limiter | Throttles call rate | Not a circuit breaker |
| Cache | Returns previously stored values | Does not guarantee data is fresh or acceptable |
| Idempotency key | Makes replayed write requests safer when supported by the server | Does not reduce network attempts |

There are three separate numbers to track:

- **Logical calls**: how many times users/use cases invoke the application facade.
- **HTTP attempts**: how many real HTTP requests the client sends upstream.
- **Fallback invocations**: how many times the application returns a fallback outcome.

One logical call might generate three HTTP attempts due to retries while returning one final result. Conversely, an OPEN breaker might trigger one fallback invocation with zero HTTP attempts.

### 2.1 Properly scoped flow diagram

~~~text
Controller / scheduled worker / message consumer
     |
     +--> validate input, authentication, business policy
     |
     v
Application facade
     |
     +--> CircuitBreaker acquires permission
     |       |
     |       +-- OPEN -> CallNotPermittedException -> FALLBACK
     |       |
     |       +-- CLOSED / permitted HALF_OPEN
     |                    |
     |                    v
     |                Retry policy (if configured)
     |                    |
     |                    v
     |                Spring RestClient
     |                    |
     |                    v
     |                HTTP upstream
     |                    |
     |                    +-- 200 / 404 / 429 / 503 / timeout
     |
     +--> classify outcome, record metrics, selective FALLBACK
     |
     v
Result with explicit status: REMOTE / UNAVAILABLE / STALE
~~~

**Important:** the order of `Retry` and `CircuitBreaker` varies depending on programmatic decorators vs. Spring AOP aspects. Never treat the order in which annotations appear in Java source as proof of runtime execution order.

## 3. Circuit breaker: states and thresholds

| State | Permits upstream calls? | Behavior |
| --- | --- | --- |
| `CLOSED` | Yes | Records failure/success/slow-call metrics |
| `OPEN` | No | Rejects before invoking the protected supplier |
| `HALF_OPEN` | Limited probes only | Tests recovery with a capped number of calls |
| `FORCED_OPEN` | No | Administratively forced open |
| `DISABLED` | Yes | Bypasses state machine tracking |
| `METRICS_ONLY` | Yes | Records metrics without tripping OPEN |

Common Resilience4j settings:

- `slidingWindowType`: `COUNT_BASED` (call count) or `TIME_BASED` (time window).
- `slidingWindowSize`: window size.
- `minimumNumberOfCalls`: minimum samples before failure rate is evaluated.
- `failureRateThreshold`: failure percentage threshold to trip OPEN.
- `slowCallRateThreshold`, `slowCallDurationThreshold`: trips OPEN when too many calls are slow.
- `waitDurationInOpenState`: wait duration before allowing `HALF_OPEN`.
- `permittedNumberOfCallsInHalfOpenState`: number of probes allowed in `HALF_OPEN`.
- `automaticTransitionFromOpenToHalfOpenEnabled`: whether to transition automatically without waiting for a new request.

Test configuration example:

~~~text
slidingWindowType                  COUNT_BASED
slidingWindowSize                  2
minimumNumberOfCalls              2
failureRateThreshold              50%
permittedNumberOfCallsInHalfOpen  1
waitDurationInOpenState           10 minutes
~~~

With **two initial 503 calls**, the breaker collects 2 samples at 100% failure rate → OPEN. The third call is rejected and emits no HTTP request. After **only the first 503**, the breaker stays CLOSED because `minimumNumberOfCalls=2` has not been reached.

### 3.1 OPEN does not mean the system has recovered

The OPEN state exists to **shed load off a failing upstream**, not to prove upstream is still broken or healthy again. After the wait duration, `HALF_OPEN` permits a small number of probes. Passing probes transition back to CLOSED; failing probes re-open the circuit.

For logic tests, avoid `Thread.sleep(Duration...)`. Resilience4j provides `transitionToOpenState()` and `transitionToHalfOpenState()` to force states **in tests**, letting you verify exact request counts cleanly. Production code should not invoke these methods casually in business flows.

### 3.2 Rejected calls must be measured separately

`CircuitBreaker.Metrics.getNumberOfNotPermittedCalls()` increments whenever a call is rejected because the circuit is OPEN (or otherwise blocked). That is **not** a server HTTP 503 response; the server **was never called**.

A trustworthy test suite checks all four:

~~~text
breaker.state = OPEN
breaker.metrics.notPermitted = 1
HTTP attempts remain unchanged
fallback result matches contract
~~~

Observing only an `UNAVAILABLE` fallback cannot tell you whether HTTP calls are still leaking through.

## 4. Fallback: do not catch Exception and fabricate data

A safe policy for a price-lookup API:

| Condition | Handling |
| --- | --- |
| 200 + body with valid amount | `Origin.REMOTE` and real amount |
| 500/502/503/504 | Breaker failure, return `UNAVAILABLE` |
| `IOException`/connect/read timeout | Breaker failure, return `UNAVAILABLE` |
| OPEN/`CallNotPermittedException` | Fallback, **send zero HTTP** |
| 200 with null/negative amount | Validate payload inside protected call, then fall back per policy |
| 400/404 | Propagate or map to domain validation/not-found |
| 401/403 | Never mask auth/permission errors with fallback |
| 429 | Dedicated policy for `Retry-After`/rate limits |
| Unexpected programming bug | Never swallow with catch-all |

Returning **0.00** as a fallback price can create $0 orders. The example returns `amount=null` paired with status `UNAVAILABLE`, forcing callers not to treat it as a valid price.

If a fallback reads a last-known-good cache, the response should carry `origin=STALE`, `asOf`, and a TTL defining how long stale values remain acceptable. For payments or security decisions, "faking success" is usually far more dangerous than failing temporarily.

### 4.1 Fallbacks must never call the same upstream again

Anti-pattern:

~~~text
fetchPrice()
    -> upstream 503
    -> fallback()
         -> retry fetchPrice()  // same failing dependency
            -> upstream 503
            -> fallback()...
~~~

A fallback must either avoid failing dependencies or protect any secondary dependency with its own breaker/timeout. `ExpectedCount.once()` catches a fallback firing a second request immediately.

### 4.2 Never write a catch-all Exception block

~~~java
// Anti-pattern: hides 404, auth errors, and coding bugs.
try {
    return remote.fetch(sku);
} catch (Exception ignored) {
    return BigDecimal.ZERO;
}
~~~

Catch **only the specific exception types eligible for graceful degradation**. If the app defines `InvalidUpstreamPayload`, check for it explicitly rather than silently discarding all JSON parsing or programming bugs.

## 5. How to mock the HTTP client properly

Three levels exist:

1. **Mockito mock of service/port interface**: fast for business logic, yet proves nothing about URL, HTTP method, headers, transport errors, or HTTP request counts leaving the adapter.
2. **Spring `MockRestServiceServer`**: replaces the request factory of `RestClient`/`RestTemplate` and supports `expect(once/times(N))` plus status/body/error simulation. Does not traverse real sockets.
3. **WireMock or OkHttp `MockWebServer`**: runs a localhost HTTP server so the real client opens TCP sockets; better for request journals, delays, connection resets, redirects, compression, and timeouts.

For this topic, the runnable example uses **`RestClient` + `MockRestServiceServer` + Resilience4j Core**. It verifies exact requests with zero internet calls.

### 5.1 Bind to the exact builder before build()

~~~java
RestClient.Builder builder = RestClient.builder()
        .baseUrl("https://vendor.example.test");

MockRestServiceServer mockServer =
        MockRestServiceServer.bindTo(builder).build();

RestClient client = builder.build();
~~~

If the mock server binds to Builder A while production code receives a `RestClient` created from Builder B, tests miss real requests and may even hit the network unintentionally.

### 5.2 Exact count

~~~java
mockServer.expect(
        ExpectedCount.once(),
        requestTo("https://vendor.example.test/prices/SKU-1"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                "{\"amount\":125.50}", MediaType.APPLICATION_JSON));

PriceResult actual = priceClient.getPrice("SKU-1");

mockServer.verify();
~~~

This is an **illustrative snippet; imports and setup appear in the test class below**. `ExpectedCount.once()` enforces one attempt; `ExpectedCount.times(2)` enforces two. Never switch to `manyTimes()` just to make a failing test pass: it hides unintended retries.

### 5.3 MockRestServiceServer does not test real TLS/DNS/connection pools

It mocks `ClientHttpRequestFactory`. When socket behavior, pools, redirects, or timeouts matter, add WireMock/MockWebServer on a dynamic localhost port. Use the real production request factory in TCP tests; otherwise you can miss hidden retries inside an HTTP client implementation.

## 6. Runnable Java 17+ / Spring Boot 3.5.x example

The sample uses a **programmatic `CircuitBreaker`**, needing no Spring AOP or `ApplicationContext` to run JUnit tests. This isolates state and keeps HTTP call counts transparent. The project has two Java source files, Gradle config, and **10 JUnit Jupiter test methods**.

~~~text
http-client-resilience-demo/
  settings.gradle
  build.gradle
  src/
    main/java/example/httpclient/PriceClient.java
    test/java/example/httpclient/PriceClientTest.java
~~~

### 6.1 settings.gradle

~~~groovy
rootProject.name = 'http-client-resilience-demo'
~~~

### 6.2 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'io.github.resilience4j:resilience4j-circuitbreaker:2.3.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This `build.gradle` targets the client module tests with pinned illustrative versions—**not a claim of being the latest releases**. `spring-boot-starter-web` brings `RestClient` and Jackson, while `starter-test` brings JUnit Jupiter and `MockRestServiceServer`. Core Resilience4j needs no Boot AOP starter.

The project declares no `@SpringBootApplication` because it only runs component tests; `./gradlew test` is the target. To build an executable Boot JAR, add a main class/config or keep the module as a dedicated Java library.

## 7. Production source: PriceClient.java

File `src/main/java/example/httpclient/PriceClient.java`:

~~~java
package example.httpclient;

import java.math.BigDecimal;
import java.util.Objects;
import java.util.regex.Pattern;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

public final class PriceClient {

    public enum Origin {
        REMOTE, UNAVAILABLE
    }

    public record PriceResult(
            String sku,
            BigDecimal amount,
            Origin origin) {
    }

    public record PricePayload(BigDecimal amount) {
    }

    public static final class InvalidUpstreamPayload
            extends RuntimeException {
        public InvalidUpstreamPayload(String message) {
            super(message);
        }
    }

    private static final Pattern VALID_SKU =
            Pattern.compile("[A-Z][A-Z0-9-]{0,19}");

    private final RestClient restClient;
    private final CircuitBreaker circuitBreaker;

    public PriceClient(
            RestClient restClient,
            CircuitBreaker circuitBreaker) {
        this.restClient = Objects.requireNonNull(restClient);
        this.circuitBreaker =
                Objects.requireNonNull(circuitBreaker);
    }

    public PriceResult getPrice(String sku) {
        if (sku == null
                || !VALID_SKU.matcher(sku).matches()) {
            throw new IllegalArgumentException("Invalid SKU");
        }

        try {
            return circuitBreaker.executeSupplier(() -> {
                PricePayload payload = restClient.get()
                        .uri("/prices/{sku}", sku)
                        .retrieve()
                        .body(PricePayload.class);

                if (payload == null
                        || payload.amount() == null
                        || payload.amount().signum() < 0) {
                    throw new InvalidUpstreamPayload(
                            "Missing or invalid amount");
                }

                return new PriceResult(
                        sku, payload.amount(), Origin.REMOTE);
            });

        } catch (HttpServerErrorException
                | ResourceAccessException
                | CallNotPermittedException
                | InvalidUpstreamPayload ex) {
            // Fallback NEVER sends another HTTP request.
            return new PriceResult(
                    sku, null, Origin.UNAVAILABLE);
        }
    }
}
~~~

Explanation:

- Validate SKU **before** the breaker and HTTP so invalid inputs do not penalize the circuit breaker.
- `retrieve()` throws `RestClientException` subclasses for 4xx/5xx by default.
- 5xx normally throws `HttpServerErrorException`; request I/O errors throw `ResourceAccessException`.
- A 200 with null/negative amount throws `InvalidUpstreamPayload` **inside the protected supplier**, so the breaker records the failure.
- OPEN throws `CallNotPermittedException` **before calling the supplier**.
- Fallback returns only `UNAVAILABLE` with `amount=null`, never retrying upstream.
- 404 throws `HttpClientErrorException`, **uncaught by fallback**; callers handle it per domain policy.
- No Retry sits inside this class, so one CLOSED logical call makes at most one HTTP attempt.

In production, create the circuit breaker **once per dependency** via a bean or registry. Creating a new breaker inside every `getPrice()` call prevents metrics from accumulating to trip OPEN.

## 8. PriceClientTest.java: ten JUnit Jupiter tests

File `src/test/java/example/httpclient/PriceClientTest.java`:

~~~java
package example.httpclient;

import java.io.IOException;
import java.math.BigDecimal;
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.ExpectedCount.times;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class PriceClientTest {

    private static final String URL =
            "https://vendor.example.test/prices/SKU-1";

    private MockRestServiceServer server;
    private CircuitBreaker breaker;
    private PriceClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://vendor.example.test");

        server = MockRestServiceServer.bindTo(builder).build();

        CircuitBreakerConfig config =
                CircuitBreakerConfig.custom()
                        .slidingWindowType(
                                CircuitBreakerConfig
                                        .SlidingWindowType.COUNT_BASED)
                        .slidingWindowSize(2)
                        .minimumNumberOfCalls(2)
                        .failureRateThreshold(50)
                        .permittedNumberOfCallsInHalfOpenState(1)
                        .waitDurationInOpenState(
                                Duration.ofMinutes(10))
                        .recordExceptions(
                                HttpServerErrorException.class,
                                ResourceAccessException.class,
                                PriceClient.InvalidUpstreamPayload.class)
                        .ignoreExceptions(
                                HttpClientErrorException.class)
                        .build();

        breaker = CircuitBreaker.of("pricing-test", config);
        client = new PriceClient(builder.build(), breaker);
    }

    @AfterEach
    void verifyExpectedHttpRequests() {
        server.verify();
    }

    @Test
    @DisplayName("200: one request and real price")
    void successExactlyOnce() {
        server.expect(once(), requestTo(URL))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"amount\":125.50}",
                        MediaType.APPLICATION_JSON));

        PriceClient.PriceResult result =
                client.getPrice("SKU-1");

        assertEquals(PriceClient.Origin.REMOTE, result.origin());
        assertEquals(0, result.amount()
                .compareTo(new BigDecimal("125.50")));
        assertEquals(CircuitBreaker.State.CLOSED,
                breaker.getState());
    }

    @Test
    @DisplayName("First 503 falls back without opening circuit")
    void firstServerFailureFallsBack() {
        server.expect(once(), requestTo(URL))
                .andRespond(
                        withStatus(HttpStatus.SERVICE_UNAVAILABLE));

        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(CircuitBreaker.State.CLOSED,
                breaker.getState());
        assertEquals(1,
                breaker.getMetrics().getNumberOfFailedCalls());
    }

    @Test
    @DisplayName("Two 503s open circuit; third call skips HTTP")
    void twoFailuresOpenAndThirdIsBlocked() {
        server.expect(times(2), requestTo(URL))
                .andRespond(
                        withStatus(HttpStatus.SERVICE_UNAVAILABLE));

        assertUnavailable(client.getPrice("SKU-1"));
        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(CircuitBreaker.State.OPEN,
                breaker.getState());

        // Third call MUST NOT emit HTTP.
        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(CircuitBreaker.State.OPEN,
                breaker.getState());
        assertEquals(1,
                breaker.getMetrics()
                        .getNumberOfNotPermittedCalls());
    }

    @Test
    @DisplayName("Manual OPEN: zero HTTP calls")
    void openStateNeverInvokesRemote() {
        breaker.transitionToOpenState();

        // Register no server.expect(...).
        assertUnavailable(client.getPrice("SKU-1"));

        assertEquals(CircuitBreaker.State.OPEN,
                breaker.getState());
        assertEquals(1,
                breaker.getMetrics()
                        .getNumberOfNotPermittedCalls());
    }

    @Test
    @DisplayName("HALF_OPEN probe 200 -> CLOSED")
    void halfOpenRecoveryCloses() {
        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();

        server.expect(once(), requestTo(URL))
                .andRespond(withSuccess(
                        "{\"amount\":125.50}",
                        MediaType.APPLICATION_JSON));

        PriceClient.PriceResult result =
                client.getPrice("SKU-1");

        assertEquals(PriceClient.Origin.REMOTE, result.origin());
        assertEquals(CircuitBreaker.State.CLOSED,
                breaker.getState());
    }

    @Test
    @DisplayName("HALF_OPEN probe 503 -> OPEN")
    void halfOpenFailureReopens() {
        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();

        server.expect(once(), requestTo(URL))
                .andRespond(
                        withStatus(HttpStatus.SERVICE_UNAVAILABLE));

        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(CircuitBreaker.State.OPEN,
                breaker.getState());

        // Extra logical call rejected; no second request.
        assertUnavailable(client.getPrice("SKU-1"));
    }

    @Test
    @DisplayName("404 is not hidden by fallback")
    void notFoundIsPropagated() {
        server.expect(once(), requestTo(URL))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(HttpClientErrorException.class,
                () -> client.getPrice("SKU-1"));

        assertEquals(CircuitBreaker.State.CLOSED,
                breaker.getState());
        assertEquals(0,
                breaker.getMetrics().getNumberOfFailedCalls());
    }

    @Test
    @DisplayName("Invalid SKU does not call remote")
    void validationRejectsBeforeHttp() {
        assertThrows(IllegalArgumentException.class,
                () -> client.getPrice("../wrong"));

        assertEquals(CircuitBreaker.State.CLOSED,
                breaker.getState());
    }

    @Test
    @DisplayName("200 missing amount counts as upstream failure")
    void malformedPayloadIsRecorded() {
        server.expect(once(), requestTo(URL))
                .andRespond(withSuccess(
                        "{\"amount\":null}",
                        MediaType.APPLICATION_JSON));

        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(1,
                breaker.getMetrics().getNumberOfFailedCalls());
    }

    @Test
    @DisplayName("Transport IOException falls back")
    void ioFailureIsRecorded() {
        server.expect(once(), requestTo(URL))
                .andRespond(withException(
                        new IOException("connection reset")));

        assertUnavailable(client.getPrice("SKU-1"));
        assertEquals(1,
                breaker.getMetrics().getNumberOfFailedCalls());
    }

    private static void assertUnavailable(
            PriceClient.PriceResult result) {
        assertEquals(PriceClient.Origin.UNAVAILABLE,
                result.origin());
        assertEquals("SKU-1", result.sku());
        assertNull(result.amount());
    }
}
~~~

**There are 10 `@Test` methods.** Each `@BeforeEach` creates a fresh mock server, `RestClient`, and `CircuitBreaker`. Zero Spring context caching, zero vendor calls, zero real-time waiting, and zero state leakage across tests.

### 8.1 Expectation table

| Test | HTTP attempts | Final state | Outcome |
| --- | ---: | --- | --- |
| `successExactlyOnce` | 1 | CLOSED | REMOTE, amount 125.50 |
| `firstServerFailureFallsBack` | 1 | CLOSED | UNAVAILABLE, failedCalls=1 |
| `twoFailuresOpenAndThirdIsBlocked` | 2 for 3 logical calls | OPEN | UNAVAILABLE, rejectedCalls=1 |
| `openStateNeverInvokesRemote` | 0 | OPEN | UNAVAILABLE |
| `halfOpenRecoveryCloses` | 1 | CLOSED | REMOTE |
| `halfOpenFailureReopens` | 1 for 2 logical calls | OPEN | UNAVAILABLE |
| `notFoundIsPropagated` | 1 | CLOSED | HTTP client error thrown |
| `validationRejectsBeforeHttp` | 0 | CLOSED | IllegalArgumentException |
| `malformedPayloadIsRecorded` | 1 | CLOSED | UNAVAILABLE, failedCalls=1 |
| `ioFailureIsRecorded` | 1 | CLOSED | UNAVAILABLE, failedCalls=1 |

### 8.2 Why asserting metrics alone is insufficient

`getNumberOfNotPermittedCalls() == 1` proves the breaker rejected once, yet if the fallback fires HTTP through another path, remote attempts still climb. `MockRestServiceServer` must verify zero **extra requests**.

Conversely, verifying zero requests when OPEN without checking state is also incomplete: code might accidentally skip the remote call due to validation or caching. Both assertion types reinforce each other.

### 8.3 Never use manyTimes()

`server.expect(manyTimes(), ...)` lets excessive retries pass silently. When business policy allows at most one attempt, use `once()`. When valid retries permit two attempts, use `times(2)`. Verify the exact HTTP operation (method, URL, headers/body if significant), not merely a counter on the facade.

## 9. How to run and expected outcome

Linux/macOS:

~~~bash
./gradlew test --tests example.httpclient.PriceClientTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.httpclient.PriceClientTest
~~~

**Expected:** JUnit Jupiter runs 10 tests and all PASS given the specified versions/dependencies and file paths. `test` requires no running HTTP server or external network. This is **an expectation from structural review**, not a log from a verified Gradle execution. No fixed stdout is promised; Gradle/IDE may output `BUILD SUCCESSFUL` and write the report to `build/reports/tests/test/index.html`.

If your environment runs Spring Boot 4.x or a different Resilience4j release, check matching starter names/Javadocs; this example intentionally targets Boot 3.5.x and Resilience4j Core 2.3.0.

## 10. Why not put @CircuitBreaker annotations right inside the demo?

The programmatic API tests each step directly:

~~~java
CircuitBreaker breaker =
        CircuitBreaker.of("pricing-test", config);

return breaker.executeSupplier(
        () -> restClient.get().uri(...).retrieve().body(...));
~~~

With annotations such as `@CircuitBreaker(name="pricing", fallbackMethod="fallback")`, Spring AOP proxies, bean lifecycles, aspect ordering, starter configs, and potential self-invocation enter the picture. The demo's aim is **proving HTTP attempt counts first**, after which integration tests can cover annotation wiring.

### 10.1 Fallback method signatures with Resilience4j annotations

Conceptual pattern:

~~~java
@CircuitBreaker(name = "pricing", fallbackMethod = "fallback")
public PriceResult find(String sku) {
    return remote.fetch(sku);
}

private PriceResult fallback(
        String sku, CallNotPermittedException ex) {
    return unavailable(sku);
}
~~~

This is an **illustrative snippet**, not part of the runnable source: it requires the Resilience4j Spring Boot 3 starter, AOP support, imports, domain classes, and a bean inside a Spring context. A fallback generally takes **the original parameters + a trailing exception parameter** and returns a compatible type. Multiple overloads by exception type are supported; Resilience4j selects the closest match.

Avoid writing a single fallback taking generic `Exception` that accidentally hides 404, bad credentials, invalid SKUs, and programming bugs.

### 10.2 Watch out for self-invocation

~~~java
@Service
class PricingFacade {
    public PriceResult outer(String sku) {
        return protectedCall(sku); // same bean; may bypass AOP proxy
    }

    @CircuitBreaker(name = "pricing")
    public PriceResult protectedCall(String sku) {
        // ...
    }
}
~~~

This snippet illustrates proxy mechanics, not a class in the demo. Under standard Spring proxy mode, calling `this.protectedCall` bypasses the proxy so the breaker annotation **does not apply**. Move the protected adapter into a separate bean or use programmatic `CircuitBreaker` for an explicit boundary.

### 10.3 Sample starter configuration (not for the Core demo)

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      pricing:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

This is **YAML for Resilience4j Spring Boot integration**, not auto-loaded by `CircuitBreaker.of(...)` in the Core example. When using annotations, the instance name `pricing` must match the config/registry entry and integration dependencies must match your version.

## 11. Retries: the top cause of unexpected duplicate requests

Retries can originate from many layers:

- Resilience4j `@Retry` at the service layer.
- Spring Retry `@Retryable` at the adapter.
- Feign `Retryer` or SDK-specific middleware.
- Apache/JDK HTTP client automatic retries (depending on config).
- Spring Cloud LoadBalancer or reverse proxies/gateways.
- Custom retry loops in `catch`/`for`/`while` blocks.
- Message redelivery or duplicate subscriptions in reactive pipelines.

One logical request can explode into N×M attempts when **two retryers stack**. If the service retries up to 3 times and the underlying SDK also retries 3 times, certain failure paths emit **9 remote attempts**.

### 11.1 maxAttempts includes the initial call

In many retry libraries, `maxAttempts=3` means **at most three total attempts**, not three retries on top of one initial attempt. Always verify the exact semantics of your library, as property names differ across frameworks.

### 11.2 Retry policy by HTTP status

| Scenario | Retry? | Reason |
| --- | --- | --- |
| GET hits 502/503, transient upstream | Possibly, bounded | Idempotent read and infrastructure may recover |
| Connect timeout before request | Possibly | Depends on transport and deadline |
| Read timeout | Cautiously | Server may have processed it even though client missed response |
| 429 | Follow `Retry-After`/quotas | Avoid overloading upstream further |
| 400 invalid input | No | Retrying identical input rarely fixes validation |
| 401/403 | Never retry blindly | Controlled auth/refresh policy |
| 404 | Normally no | Exceptions only if eventual-consistency contract explicitly allows |
| Payment/order POST | Never by default | Requires idempotency key and server-side deduplication |
| Pool exhausted | Never retry infinitely | Can trigger retry storms |

Retries need **backoff + jitter**, bounded attempts, an overall deadline, and error classification. Never set a per-attempt timeout alongside infinite retries.

### 11.3 Aspect order shapes attempt counts and breaker metrics

Resilience4j Spring Boot integration has a typical default aspect order:

~~~text
Retry ( CircuitBreaker ( RateLimiter ( TimeLimiter ( Bulkhead ( Function ) ) ) ) )
~~~

When Retry wraps **outside** `CircuitBreaker`, each attempt can be recorded as an event by the circuit breaker. However, if a fallback inside the breaker catches the exception and returns a normal value, the outer Retry sees success and **never retries**. Reversing the order lets the breaker record one logical call wrapping multiple attempts inside.

Never infer aspect order from **annotation declaration order on the Java method**. When combining `@Retry` and `@CircuitBreaker` on one method, test through the real Spring proxy bean and verify HTTP attempts plus breaker metrics. Resilience4j exposes properties `resilience4j.retry.retryAspectOrder` and `resilience4j.circuitbreaker.circuitBreakerAspectOrder` when customization is needed; exact behavior depends on version.

### 11.4 Fallback after retries—do not swallow failures prematurely

An intentional flow:

~~~text
Logical call
    |
    v
Breaker permission
    |
    v
Retry (if operation permits)
    |
    v
HTTP client
    |
    +-- success -> REMOTE
    |
    +-- attempts exhausted -> exception / breaker event
                           |
                           v
                       one fallback
~~~

This is a **conceptual** flow, not a claim about default Resilience4j annotation wiring. Whenever using functional chaining or AOP, verify the resulting order directly.

## 12. Domain-accurate fallbacks and idempotency

Whenever **write** requests can be retried, duplicate side effects must be prevented. HTTP example:

~~~http
POST /payments
Idempotency-Key: order-123-payment
Content-Type: application/json

{"orderId":"123","amount":100}
~~~

This is an **illustrative protocol**; the `Idempotency-Key` header only works if the server enforces it properly. The server must prevent races between concurrent attempts, persist the key and outcome transactionally, and return the original result for duplicate requests.

A dedicated test must prove:

~~~text
one logical payment request
two HTTP attempts may occur
same Idempotency-Key on every attempt
server creates exactly one charge
client never fakes success when status is unknown
~~~

For GET quotes, duplication is less destructive, yet still inflates latency, cost, and rate-limit consumption.

### 12.1 Cache fallbacks need a TTL

A last-known-good cache can serve stale prices. Test:

- Cache hit → return `STALE` with timestamp.
- Cache past TTL → return `UNAVAILABLE`, do not serve expired stale values.
- Cache miss → `UNAVAILABLE`.
- Cache is a separate dependency: if cache is down, fallback must never loop.
- Critical data like authorizations or charge amounts: policy may disallow stale data altogether.
- Separate logs/counters for degraded/stale outcomes—never record them as upstream successes.

## 13. Timeouts are not circuit breakers

A circuit breaker limits **new calls**; it does not force an already hanging synchronous `RestClient` call to abort. Configure timeouts on the HTTP transport/client.

Spring Framework 6.2 `SimpleClientHttpRequestFactory` example:

~~~java
SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();
factory.setConnectTimeout(Duration.ofSeconds(2));
factory.setReadTimeout(Duration.ofSeconds(3));

RestClient client = RestClient.builder()
        .requestFactory(factory)
        .baseUrl("https://vendor.example.test")
        .build();
~~~

This is an **illustrative snippet**, requiring imports and outside the demo tests. If production uses Apache HttpComponents, JDK, or Jetty, configure factory and pool timeouts for that actual client.

**End-to-end deadlines** must account for attempts, backoff, queue/pool wait, and fallback—not just single-attempt timeouts. Three attempts × three seconds exceeds a 5-second controller SLO.

### 13.1 Breakers do not automatically cancel in-flight calls

Even after the breaker trips OPEN following two failures, requests started earlier may still be running. Circuit-breaker tests using a synchronous supplier do not prove cancellation of async calls or `WebClient`. For async/Reactive clients, write separate tests for cancellation, timeouts, and concurrency.

## 14. When to use WireMock / MockWebServer?

`MockRestServiceServer` is fast for testing URL/method/status/responses and exact counts at the client component level, yet it opens no TCP sockets.

If a suspected bug involves:

- DNS/connect timeouts, connection resets;
- HTTP redirects/retries inside client implementations;
- TLS, proxies, connection pooling;
- header/body streaming, chunking, and compression;
- race conditions under concurrent requests;

switch to WireMock or OkHttp `MockWebServer` on a random port using a production-like client request factory, and inspect the request journal.

**Non-standalone illustrative** pattern:

~~~java
@RegisterExtension
static WireMockExtension mock =
        WireMockExtension.newInstance()
                .options(wireMockConfig().dynamicPort())
                .build();

// After stubbing and invoking SUT, verify exact request count:
mock.verify(2, getRequestedFor(
        urlEqualTo("/prices/SKU-1")));
~~~

This is a WireMock 3.x pattern requiring dependencies/imports and injecting the dynamic port into the client base URL. Never hardcode `localhost:8080`, which collides in parallel CI runs.

Even a TCP mock server is not the real vendor and does not verify the full production proxy/TLS topology.

## 15. WebClient, @HttpExchange, and multiple subscriptions

With `WebClient`, a `Mono`/`Flux` can be a cold publisher: **each subscription** may fire a new HTTP call. Subscribing twice to the same publisher does not necessarily share one network response.

~~~java
Mono<Price> result = webClient.get()
        .uri("/prices/{sku}", sku)
        .retrieve()
        .bodyToMono(Price.class);

result.subscribe();
result.subscribe(); // may trigger a second HTTP call
~~~

This is an **explanatory snippet**, not part of the demo. When protecting a reactive client with a circuit breaker, apply the decorator at the **subscription/execution boundary**, not merely when constructing the `Mono`. Use Reactor `StepVerifier`, virtual time, and an HTTP mock server as appropriate.

With Spring declarative `@HttpExchange`/`@GetExchange`, Mockito-mocking the proxy interface cannot prove real transport request counts. Verify at the underlying HTTP mock layer.

## 16. Duplicate requests do not come from Retry alone

Other sources of duplication:

1. A controller invokes the adapter twice while handling a single response.
2. A callback inside a stream executes twice.
3. A message consumer redelivers after an ack timeout.
4. A scheduler fires simultaneously on two replicas.
5. UI double-clicks submit two operations.
6. Manual retry inside a `catch` block runs on top of a retry library.
7. An SDK or API gateway retries silently underneath.
8. A cache loader is invoked concurrently by multiple threads.
9. Misconfigured GraphQL DataLoader/batch mapping.
10. Transaction retries re-run a block that already published an out-of-DB HTTP event.

Hence verify **network attempt counts** and **business side-effect counts** at the right boundaries. For GET, `MockRestServiceServer.expect(once)` suffices for a component test. For payments/orders, add integration tests with a real idempotency store and concurrent requests.

## 17. Metrics and logging to catch bugs outside tests

Observe:

| Metric/trace | Meaning |
| --- | --- |
| Circuit breaker state | CLOSED/OPEN/HALF_OPEN |
| Failure rate | Error ratio inside window |
| Not-permitted calls | Calls blocked before HTTP |
| Upstream HTTP requests | Actual attempts |
| Retry attempts | Retries per logical operation |
| Fallback result | Degraded/unavailable ratio |
| HTTP status | 2xx/4xx/5xx, 429/503 |
| End-to-end latency | Includes attempts and backoff |
| Upstream latency | Per HTTP attempt |
| Logical request ID | Correlates trace across all attempts |

If a fallback returns HTTP 200 at the application layer, monitoring that watches only app 5xx will miss upstream outages. Track degraded/unavailable metrics, alert on SLOs, and log correlation IDs **without leaking credentials, bearer tokens, or PII**.

**Illustrative log example, not test stdout:**

~~~text
trace=abc1 logicalCall=pricing-1 attempt=1 status=503
trace=abc1 logicalCall=pricing-1 fallback=UNAVAILABLE
trace=abc2 logicalCall=pricing-2 breaker=OPEN upstreamAttempt=0
~~~

## 18. Common mistakes and fixes

**1. Asserting only that the fallback returned an object.**  
Add assertions for breaker state, metrics, and exact HTTP attempts.

**2. Expecting one 503 to trip the breaker OPEN immediately.**  
Check `minimumNumberOfCalls` and the sliding window.

**3. Using `Thread.sleep` to wait for HALF_OPEN.**  
Flaky; use manual state transitions in logic tests or a custom `Clock` in a dedicated suite.

**4. Sharing one circuit breaker instance across test methods.**  
State leaks; instantiate a fresh one in `@BeforeEach`.

**5. Creating a new breaker on every production request.**  
Never accumulates enough failures; use a shared registry/bean per dependency.

**6. Fallback calls the same broken upstream again.**  
Defeats the breaker; exact-count tests catch this.

**7. Catching `Exception` and returning 0.00.**  
Hides 404/auth/bugs and can corrupt business calculations.

**8. Counting 404 like 503.**  
Define explicit exception classifiers and domain policies.

**9. Retrying 429 immediately and endlessly.**  
Honor `Retry-After`, quotas, backoff + jitter, and deadlines.

**10. Placing Retry on both the service and the HTTP client.**  
Multiplies attempts; measure at the network boundary.

**11. Inferring aspect order from annotation order on the method.**  
Unreliable; verify Spring AOP config and actual attempts.

**12. `@CircuitBreaker` self-invocation.**  
Proxy never intercepts; extract a separate bean or use programmatic core.

**13. Missing Resilience4j Spring starter/AOP.**  
Compiling annotations does not mean aspects run; verify inside a Spring context.

**14. Breaker is OPEN yet HTTP still fires.**  
Wrong instance/wiring or bypassing path; test OPEN and verify zero requests.

**15. Using `manyTimes()` in mocks.**  
Hides extra attempts; use `once`/`times(N)` per policy.

**16. Omitting `mockServer.verify()`.**  
Leaves unused expectations undetected.

**17. Mocking a service and claiming HTTP statuses/URLs were tested.**  
Service mocks prove service invocations only, not transport.

**18. Mock request factory passes while production fails in TCP/pooling.**  
Add WireMock/MockWebServer using the production client factory.

**19. Missing HTTP client timeouts.**  
Circuit breakers cannot interrupt hanging suppliers.

**20. Retrying POST without idempotency.**  
Timeouts do not prove the server aborted; guard side effects on the server.

**21. Recording fallbacks as successes in breaker metrics.**  
Throw errors inside the protected supplier and handle fallback outside the decorator.

**22. Not testing failed HALF_OPEN probes.**  
The breaker must re-open and block subsequent calls.

**23. Fallback reading cache past TTL.**  
Can serve stale bad data; assert age, origin, and domain constraints.

**24. Checking only Mockito invocation counts on a facade.**  
One facade call can fan out into multiple HTTP attempts; check the HTTP boundary.

**25. Never monitoring degraded ratios in production.**  
The application may return 200 constantly while users never see fresh prices.

## 19. Workflow for designing duplicate-preventing tests

1. Define the logical operation and upstream endpoint.
2. Classify errors into fallback, retry, bypass, and propagate.
3. Specify the exact **max HTTP attempts** per logical call.
4. Define breaker window/minimumCalls/threshold and expected state transitions.
5. Place input validation before HTTP/breaker.
6. Use a `RestClient.Builder` bound to `MockRestServiceServer` **before `build()`**.
7. Instantiate a fresh breaker for every test.
8. Verify the happy path with `once()`.
9. Verify a single 503: proper fallback, breaker still CLOSED when below minimum samples.
10. Verify enough failures trip OPEN and the next call fires zero HTTP.
11. Verify HALF_OPEN success/failure via controlled transitions, without sleeping.
12. Verify 404/400/auth errors are never swallowed.
13. Verify invalid inputs/payloads, I/O faults, and error classification.
14. If adding retries, update exact expected attempts and verify no hidden retry layers exist.
15. For write requests, verify idempotency and DB/service side-effect counts in integration tests.
16. If a defect is network-level, add TCP mock server tests.
17. Observe metrics and logs by logical operation vs. attempts.
18. Run CI repeatedly to catch state/timing leaks without touching real vendors.

### Final checklist

- [ ] Fallback results carry an explicit degraded status.
- [ ] Zero price is never returned as a real price when upstream is down.
- [ ] Breaker CLOSED/OPEN/HALF_OPEN states have assertions.
- [ ] OPEN emits zero extra HTTP calls, verified by the mock server.
- [ ] Minimum calls and failure rate match configured thresholds.
- [ ] 404 and HTTP client errors follow explicit policies.
- [ ] HTTP 429 is never retried aggressively.
- [ ] Exact attempts verified, without `manyTimes` masking bugs.
- [ ] Fallbacks never call the same upstream again.
- [ ] Tests isolate breaker/registry state.
- [ ] No `Thread.sleep` used for state assertions.
- [ ] Timeouts and overall deadlines explicitly configured.
- [ ] No stacked duplicate retries across layers.
- [ ] Spring AOP/aspect order verified when using annotations.
- [ ] Write APIs have idempotency/duplicate side-effect tests.
- [ ] HTTP mock layer matches test goal (factory vs. TCP).
- [ ] Observability covers degraded outcomes, OPEN state, retry attempts, and request counts.

## 20. Self-check questions

**1.** Does an `UNAVAILABLE` fallback after 503 prove the breaker is OPEN?  
**No.** The first failure may not yet have reached `minimumNumberOfCalls`.

**2.** Why must an OPEN test verify zero HTTP requests?  
Because a fallback could run *after* firing a request; you must prove the supplier was blocked before transport.

**3.** Should 404 return fallback 0.00?  
Normally no: 404 reflects a not-found/client policy, not evidence of a vendor outage.

**4.** What is the drawback of `Thread.sleep` waiting for HALF_OPEN?  
Flakiness due to schedulers/CI load; use manual transitions or a controlled `Clock` in tests.

**5.** Two stacked retry layers with max 3 can generate up to how many HTTP attempts?  
On certain failure paths, up to 9 for a single logical operation.

**6.** Does a circuit breaker replace connect/read timeouts?  
No. It governs permitting/rejecting calls and recording outcomes.

**7.** How does mocking `RestClient`'s factory differ from WireMock over TCP?  
`MockRestServiceServer` uses no sockets; WireMock tests real transport behavior.

**8.** If a supplier catches 503 itself and returns a successful fallback, what does the breaker record?  
It records success instead of failure; let exceptions reach the breaker before falling back.

**9.** Does a payment POST timeout prove the server never processed it?  
No. Retries require an idempotency policy and server-side deduplication.

**10.** Why shouldn't production code call `CircuitBreaker.of(...)` per request?  
Each new instance loses accumulated metrics and cannot share OPEN state across calls.

## 21. Conclusion

For Spring Boot HTTP client integrations, verifying fallback output **does not** prove the circuit breaker works, much less that duplicate requests are prevented. A strong test suite asserts **right outcome, right breaker state, and exact remote HTTP attempts**. Use `RestClient` + `MockRestServiceServer` to verify these boundaries, Resilience4j Core for deterministic state transitions, and add Spring AOP/WireMock and idempotency tests whenever production uses retries, annotations, or complex network transport.

**Core principle:** when the circuit is OPEN, fallbacks must run **without calling upstream again**; when retries are permitted, attempt counts must be **explicitly bounded and verified**, especially on side-effecting operations.

### Official references

- [Spring Framework — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): `MockRestServiceServer`, `ExpectedCount`, `RestClient`/`RestTemplate`.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, default status errors, and `onStatus`.
- [Spring Framework 6.2 — MockRestServiceServer Java API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): `bindTo(RestClient.Builder)`, `expect`, and `verify`.
- [Resilience4j — Circuit Breaker](https://resilience4j.readme.io/docs/circuitbreaker): states, failure rates, thresholds, and sliding windows.
- [Resilience4j — Spring Boot 3 Getting Started](https://resilience4j.readme.io/docs/getting-started-3): `@CircuitBreaker`, `fallbackMethod`, and aspect order.
- [Resilience4j — CircuitBreaker API source](https://github.com/resilience4j/resilience4j/blob/master/resilience4j-circuitbreaker/src/main/java/io/github/resilience4j/circuitbreaker/CircuitBreaker.java): `decorateSupplier`, `executeSupplier`, state transitions.
- [Resilience4j — CircuitBreakerConfig API source](https://github.com/resilience4j/resilience4j/blob/master/resilience4j-circuitbreaker/src/main/java/io/github/resilience4j/circuitbreaker/CircuitBreakerConfig.java): `minimumNumberOfCalls`, `recordExceptions`/`ignoreExceptions`, custom clock.
- [WireMock — JUnit Jupiter](https://wiremock.org/docs/junit-jupiter/): HTTP mock server extension, dynamic port, and request journal.
