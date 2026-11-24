# Application-Configured Timeouts, Fallbacks, and Circuit Breakers

Within the **Contracts and Resilience** group of **Spring Boot - testing**, applications must be tested for how they react when an HTTP upstream becomes slow, unreachable, returns 429 or 5xx, and eventually recovers. These three mechanisms relate closely yet **cannot substitute for one another**:

- **Timeout:** the client stops waiting after a deadline; it does not prove the upstream rolled back or stopped processing.
- **Circuit breaker:** records call outcomes in a sliding window; once the failure rate crosses a threshold with enough samples, it transitions to OPEN to **block new calls**.
- **Fallback:** intentional degraded behavior applied only to permitted failures; it must never turn a failed operation into fabricated valid data or mask auth/validation errors.

This lesson uses **Java 17, Spring Boot 3.5, JUnit Jupiter, JDK HttpClient, and Resilience4j CircuitBreaker 2.3.0**. It provides full source files and Gradle dependencies, real breaker tests, a `@ConfigurationProperties` test matrix, loopback HTTP tests with real timeouts, and `MockMvc` HTTP contract tests. A standalone Java SE demo without Spring includes `javac/java` commands and exact stdout.

**Example contract:** the app fetches catalog data via GET from upstream. On success, it returns real data with `degraded=false`. On HTTP timeout/429/5xx or OPEN circuit, if fallback is enabled, it returns `Catalog temporarily unavailable` with `degraded=true` and HTTP **503**, without pretending real catalog data exists. On upstream 4xx other than 429, it skips fallback and returns 502 per the demo gateway contract. This suits catalog data **not involving money or permissions**; payments, auth, and inventory control require stricter safety policies.

## 1. Four boundaries that must be tested separately

```text
Inbound HTTP
    |
    v
CatalogController
    |
    v
CatalogService
    |        (circuitEnabled=false -> call port directly)
    +---- CircuitBreaker.decorateSupplier
    |         |
    |         +-- CLOSED/HALF_OPEN -> CatalogPort.fetch
    |         |                         |
    |         |                         v
    |         |                   HttpCatalogAdapter
    |         |                         |
    |         |                JDK HttpClient timeout
    |         |                         |
    |         |                         v
    |         |                      Upstream
    |         |
    |         +-- OPEN -> CallNotPermittedException
    |
    +-- primary success -> CatalogResult(body, false)
    +-- permitted failure + fallback -> CatalogResult(message, true)
    +-- unsupported failure -> exception/advice
```

**Test boundary map:**

| Test layer | Proves | Does not prove |
| --- | --- | --- |
| JUnit + fake `CatalogPort` | Business fallback, OPEN/HALF_OPEN circuit, and call counts | Real HTTP timeouts |
| `ApplicationContextRunner` | Property binding, breaker bean construction, invalid config rejection | HTTP/Servlet behavior |
| JDK `HttpServer` on loopback | TCP/HTTP statuses, UTF-8, and real request timeouts | Circuit state if testing adapter alone |
| `@WebMvcTest` + MockMvc | Response status/headers/JSON on success/degraded | Upstream, network, breaker logic |
| Full application/E2E | Full bean graph and infrastructure in a live environment | Unsimulated production incidents |

Merely invoking a method with a mocked exception is not a network timeout test. Testing only HTTP 200 does not prove the breaker OPENS properly. And passing a fake fallback test does not prove stale production caching is safe.

## 2. Connect timeouts differ from request timeouts and deadlines

```text
Incoming API deadline (example): 2000 ms
  |
  +-- connection setup <= 500 ms
  +-- HTTP attempt <= 300 ms
  +-- optional retry/backoff (not implemented in this lesson)
  +-- fallback/serialization time
```

- `HttpClient.Builder.connectTimeout(Duration)` applies to connection setup in the JDK client, not the whole request.
- `HttpRequest.Builder.timeout(Duration)` applies to the request, including waiting for the response per JDK `HttpClient` semantics. It does not guarantee the upstream avoided side effects.
- **Pool acquisition timeout** bounds waiting for a connection/permit, distinct from network I/O timeouts.
- **TimeLimiter** in Resilience4j bounds async/`CompletionStage` waits, yet cancelling a `Future` does not automatically abort every blocking network operation or remote transaction.
- **Overall deadlines** must propagate across retries and downstream calls; adding individual timeouts together does not automatically enforce a hard end-to-end deadline.
- Distinguish **JUnit test** timeouts such as `Future.get(5, SECONDS)` from **HTTP client** timeouts. If the `Future` times out because a thread hung, you cannot conclude `HttpRequest.timeout` worked.

**When retrying mutating requests:** client timeout does not imply server rollback. Use stable idempotency keys, outboxes/inboxes, reconciliation, and pending/unknown business states. Under **at-least-once delivery** messaging, duplicates can also happen; never claim exactly-once from breakers or retries alone.

## 3. CircuitBreaker state machine and parameters

```text
       failure rate >= threshold after minimum calls
CLOSED ----------------------------------------------> OPEN
  ^                                                     |
  |                                                     | waitDurationInOpenState
  |                                                     | elapsed + next permission
  |                                                     | request (auto transition off)
  |                                                     v
  +-------------------- enough healthy probes ------ HALF_OPEN
                                failed probes --------> OPEN
```

- **CLOSED:** all calls are permitted; the breaker records outcomes without limiting concurrency.
- **OPEN:** throws `CallNotPermittedException` for **new** calls; the gateway is never called. In-flight calls admitted earlier may still finish.
- **HALF_OPEN:** permits a bounded number of probe calls. Enough healthy probes → CLOSED; failed probes exceeding threshold → OPEN.
- `slidingWindowType=COUNT_BASED` and `slidingWindowSize=4` track the **last 4 calls**, not 4 seconds.
- `minimumNumberOfCalls=4` means the first 1–3 failures will not trip the breaker to OPEN based on failure rate yet.
- `failureRateThreshold=50` means 2 failures out of 4 recorded calls meets the 50% threshold.
- `waitDurationInOpenState` is how long the breaker stays OPEN before HALF_OPEN is allowed. By default it does not transition automatically on sleep alone: a permission request may be needed to trigger the transition.
- `permittedNumberOfCallsInHalfOpenState=2` limits probing to two calls.

**Distinctions:** `CircuitBreaker` is not a Retry, Bulkhead, or RateLimiter. It neither aborts in-flight calls nor caps thread pools; combine it with HTTP timeouts and resource limits. Special states like `DISABLED`, `METRICS_ONLY`, and `FORCED_OPEN` carry different semantics than CLOSED/OPEN/HALF_OPEN.

## 4. Which errors count for the breaker? Which trigger fallback?

| Upstream/adapter result | Exception | Breaker | Fallback |
| --- | --- | --- | --- |
| HTTP 200 | None | Success | No |
| HTTP 500/503 or 429 | `CatalogPort.Unavailable` | Failure | Yes if enabled |
| `IOException`/DNS/connection fail | `Unavailable` | Failure | Yes if enabled |
| Request timeout | `Unavailable` | Failure | Yes if enabled |
| HTTP 400/401/403/404 | `Rejected` | Ignored | No |
| Interrupted thread | `Cancelled` | Ignored | No |
| Breaker OPEN | `CallNotPermittedException` | Not permitted, skips upstream | Yes if enabled |
| `NullPointerException`/code bug | Unhandled error | No fallback under this policy | No |

A 401/403 must never let fallback grant fake access; validation bugs must not make the breaker think upstream is down. The example uses `recordExceptions(Unavailable.class)` and `ignoreExceptions(Rejected.class, Cancelled.class)`. Real policies may map 404 to `Optional.empty()` instead of an exception; write contracts and tests per endpoint.

**Crucial placement:** fallback must sit **outside the decorator**, so the breaker observes primary call failures rather than fallback successes.

## 5. Application configuration via properties

```properties
app.catalog.breaker-enabled=true
app.catalog.fallback-enabled=true
app.catalog.endpoint=http://127.0.0.1:9999/catalog
app.catalog.connect-timeout-ms=500
app.catalog.request-timeout-ms=300
app.catalog.sliding-window-size=4
app.catalog.minimum-calls=4
app.catalog.failure-rate-threshold=50
app.catalog.open-wait-ms=30000
app.catalog.half-open-calls=2
```

**This `app.catalog.*` namespace is custom to this example**, not the Resilience4j Spring Boot starter namespace. If using the starter with `@CircuitBreaker` annotations, properties look like `resilience4j.circuitbreaker.instances.<name>.*` and require Spring AOP/proxy integration; do not mix them up.

Required configuration matrix:

| `breaker-enabled` | `fallback-enabled` | Primary outcome | Expectation |
| --- | --- | --- | --- |
| true | true | Success | Primary, `degraded=false` |
| true | true | Timeout | Fallback, `degraded=true` |
| true | false | Timeout | `Unavailable` propagates |
| false | true | Timeout | Fallback, breaker records nothing |
| false | false | Timeout | `Unavailable` propagates |
| true | true | 4xx `Rejected` | No fallback |
| true | true | Threshold reached | OPEN, subsequent calls skip gateway |
| true | false | OPEN | `CallNotPermittedException` |
| true | true | HALF_OPEN healthy | CLOSED |
| true | true | HALF_OPEN unhealthy | OPEN |
| any | any | Invalid config | Context startup failure |

**Test default and missing properties too.** Never mutate `System.setProperty(...)` between tests because global state leaks; use `ApplicationContextRunner.withPropertyValues` to isolate each vector in its own context.

## 6. Project structure and Gradle dependencies

```text
src/
├── main/java/example/resilience/
│   ├── ResilienceApplication.java
│   ├── CatalogSettings.java
│   ├── CatalogPort.java
│   ├── HttpCatalogAdapter.java
│   ├── CatalogResult.java
│   ├── CatalogService.java
│   ├── CatalogConfiguration.java
│   ├── CatalogController.java
│   ├── CatalogErrorAdvice.java
│   └── PolicyDecisionDemo.java
├── main/resources/application.properties
└── test/java/example/resilience/
    ├── CatalogServiceTest.java
    ├── CatalogConfigurationTest.java
    ├── HttpCatalogAdapterTest.java
    └── CatalogControllerTest.java
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is the demo Gradle build for Java 17 / Boot 3.5 / Resilience4j 2.3.0. Running Gradle needs an installed wrapper or compatible Gradle binary. No Docker, database, AWS, or cloud credentials are needed. HTTP tests use `com.sun.net.httpserver.HttpServer` from JDK 17's `jdk.httpserver` module bound to an OS-assigned loopback port.

## 7. `CatalogSettings.java`: typed configuration

Create `src/main/java/example/resilience/CatalogSettings.java`:

```java
package example.resilience;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.catalog")
public record CatalogSettings(
        @DefaultValue("true") boolean breakerEnabled,
        @DefaultValue("true") boolean fallbackEnabled,
        @DefaultValue("500") int connectTimeoutMs,
        @DefaultValue("300") int requestTimeoutMs,
        @DefaultValue("4") int slidingWindowSize,
        @DefaultValue("4") int minimumCalls,
        @DefaultValue("50") float failureRateThreshold,
        @DefaultValue("30000") long openWaitMs,
        @DefaultValue("2") int halfOpenCalls,
        @DefaultValue("http://127.0.0.1:9999/catalog")
        String endpoint) {
}
```

Spring Boot's binder supports record constructor binding and `@DefaultValue`. Kebab-case keys bind to accessors such as `requestTimeoutMs()`. `@EnableConfigurationProperties(CatalogSettings.class)` in the configuration class below registers the bean so production code never invokes the constructor manually.

**Validation:** `endpoint` must be a valid HTTP(S) URI; timeouts, window, minimum calls, and half-open calls > 0; `minimumCalls <= slidingWindowSize`; threshold in [1, 100]. Rules are validated inside the configuration factory for clear startup failures. `localhost:9999` is a **demo default that does not point to production**; real deployments must configure environment endpoints.

## 8. `CatalogPort.java`: the network boundary

Create `src/main/java/example/resilience/CatalogPort.java`:

```java
package example.resilience;

public interface CatalogPort {
    String fetch();

    final class Unavailable extends RuntimeException {
        public Unavailable(String message) {
            super(message);
        }

        public Unavailable(String message, Throwable cause) {
            super(message, cause);
        }
    }

    final class Rejected extends RuntimeException {
        public Rejected(String message) {
            super(message);
        }
    }

    final class Cancelled extends RuntimeException {
        public Cancelled(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

The service knows nothing of `HttpClient` or `IOException`; it sees only success or typed exceptions. `Unavailable` (network/timeout/5xx/429) counts as a breaker failure; `Rejected` (4xx other than 429) and `Cancelled` (interrupt) are ignored by the breaker and bypass fallback. This is an illustrative policy, not automatically applicable to every upstream API.

## 9. `HttpCatalogAdapter.java`: JDK `HttpClient` timeouts

Create `src/main/java/example/resilience/HttpCatalogAdapter.java`:

```java
package example.resilience;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class HttpCatalogAdapter implements CatalogPort {
    private final HttpClient http;
    private final CatalogSettings settings;

    public HttpCatalogAdapter(
            HttpClient http, CatalogSettings settings) {
        this.http = http;
        this.settings = settings;
    }

    @Override
    public String fetch() {
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create(settings.endpoint()))
                .timeout(Duration.ofMillis(
                        settings.requestTimeoutMs()))
                .GET()
                .build();

        try {
            HttpResponse<String> response = http.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            int status = response.statusCode();
            if (status == 200) {
                return response.body();
            }
            if (status == 429 || status >= 500) {
                throw new Unavailable("upstream unavailable");
            }
            throw new Rejected("upstream rejected request");
        } catch (HttpTimeoutException error) {
            throw new Unavailable("upstream timed out", error);
        } catch (IOException error) {
            throw new Unavailable(
                    "upstream transport error", error);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new Cancelled(
                    "upstream interrupted", error);
        }
    }
}
```

**Limitations:**

- This is a **blocking** HTTP call suitable for Servlet MVC demos; never invoke it directly on a reactive WebFlux event loop.
- Only HTTP 200 succeeds; 3xx and 4xx (other than 429) become `Rejected`. Production adapters may handle redirects, 304, or 404 distinctly.
- The adapter does not retry on its own. Timeouts are **real request timeouts** enforced by JDK `HttpRequest`; the breaker merely observes outcomes.
- `InterruptedException` preserves the interrupt flag and is never swallowed by fallback.
- Exception messages never expose raw URIs, tokens, or upstream bodies.

## 10. `CatalogResult` and `CatalogService`: fallback outside the decorator

Create `src/main/java/example/resilience/CatalogResult.java`:

```java
package example.resilience;

public record CatalogResult(
        String body, boolean degraded) {
}
```

Create `src/main/java/example/resilience/CatalogService.java`:

```java
package example.resilience;

import java.util.function.Supplier;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;

public class CatalogService {
    private final CatalogPort port;
    private final CircuitBreaker breaker;
    private final CatalogSettings settings;

    public CatalogService(
            CatalogPort port,
            CircuitBreaker breaker,
            CatalogSettings settings) {
        this.port = port;
        this.breaker = breaker;
        this.settings = settings;
    }

    public CatalogResult load() {
        Supplier<String> primary = port::fetch;

        if (settings.breakerEnabled()) {
            primary = CircuitBreaker.decorateSupplier(
                    breaker, primary);
        }

        try {
            return new CatalogResult(primary.get(), false);
        } catch (CallNotPermittedException
                 | CatalogPort.Unavailable error) {
            if (!settings.fallbackEnabled()) {
                throw error;
            }

            return new CatalogResult(
                    "Catalog temporarily unavailable",
                    true);
        }
    }
}
```

The code enforces three exact behaviors:

1. Breaker enabled → wraps `primary`. Breaker disabled → calls `port` directly while adapter request timeouts still apply.
2. `Unavailable` or `CallNotPermittedException` triggers fallback when enabled, and propagates when disabled.
3. `Rejected`, `Cancelled`, and code bugs are uncaught so callers observe errors accurately.

**Never** wrap all of `CatalogService.load` inside the `CircuitBreaker` if fallback must sit outside metrics. If fallback returns inside the measured block, the breaker sees success and fails to OPEN during outages.

## 11. `CatalogConfiguration.java`: bean lifecycle, thresholds, and validation

Create `src/main/java/example/resilience/CatalogConfiguration.java`:

```java
package example.resilience;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogSettings.class)
public class CatalogConfiguration {

    @Bean
    HttpClient catalogHttpClient(CatalogSettings settings) {
        validate(settings);

        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(
                        settings.connectTimeoutMs()))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Bean
    CircuitBreaker catalogBreaker(CatalogSettings settings) {
        validate(settings);

        CircuitBreakerConfig config =
                CircuitBreakerConfig.custom()
                        .slidingWindowType(
                                CircuitBreakerConfig.SlidingWindowType
                                        .COUNT_BASED)
                        .slidingWindowSize(
                                settings.slidingWindowSize())
                        .minimumNumberOfCalls(
                                settings.minimumCalls())
                        .failureRateThreshold(
                                settings.failureRateThreshold())
                        .waitDurationInOpenState(
                                Duration.ofMillis(
                                        settings.openWaitMs()))
                        .permittedNumberOfCallsInHalfOpenState(
                                settings.halfOpenCalls())
                        .recordExceptions(
                                CatalogPort.Unavailable.class)
                        .ignoreExceptions(
                                CatalogPort.Rejected.class,
                                CatalogPort.Cancelled.class)
                        .build();

        return CircuitBreaker.of("catalog", config);
    }

    @Bean
    CatalogPort catalogPort(
            HttpClient catalogHttpClient,
            CatalogSettings settings) {
        return new HttpCatalogAdapter(
                catalogHttpClient, settings);
    }

    @Bean
    CatalogService catalogService(
            CatalogPort catalogPort,
            CircuitBreaker catalogBreaker,
            CatalogSettings settings) {
        return new CatalogService(
                catalogPort, catalogBreaker, settings);
    }

    private static void validate(CatalogSettings s) {
        if (s.connectTimeoutMs() <= 0
                || s.requestTimeoutMs() <= 0
                || s.slidingWindowSize() <= 0
                || s.minimumCalls() <= 0
                || s.minimumCalls() > s.slidingWindowSize()
                || s.failureRateThreshold() < 1
                || s.failureRateThreshold() > 100
                || s.openWaitMs() <= 0
                || s.halfOpenCalls() <= 0) {
            throw new IllegalArgumentException(
                    "invalid catalog resilience configuration");
        }

        final URI uri;
        try {
            uri = URI.create(s.endpoint());
        } catch (IllegalArgumentException error) {
            throw new IllegalArgumentException(
                    "invalid catalog URI", error);
        }

        String scheme = uri.getScheme();
        if (scheme == null || uri.getHost() == null
                || (!scheme.equalsIgnoreCase("http")
                    && !scheme.equalsIgnoreCase("https"))) {
            throw new IllegalArgumentException(
                    "catalog URI must be HTTP(S)");
        }
    }
}
```

**Important:** the breaker bean has **one owner per `ApplicationContext`**, never re-created per request. Re-creating `CircuitBreaker.of(...)` per request discards failure history so the breaker never reaches threshold. `@EnableConfigurationProperties` binds the record and the factory validates before wiring the client.

**Feature flag** `breakerEnabled=false` in code simply skips decoration. It does not transition the breaker into the `DISABLED` state. If dynamic runtime toggling is needed, explicitly design lifecycle, state, and metrics with new tests—never mutate `Environment` after context refresh expecting the bean to update.

## 12. HTTP response contract of the application

Create `src/main/java/example/resilience/CatalogController.java`:

```java
package example.resilience;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {
    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/catalog")
    public ResponseEntity<CatalogResult> catalog() {
        CatalogResult data = service.load();

        return ResponseEntity.status(
                        data.degraded()
                                ? HttpStatus.SERVICE_UNAVAILABLE
                                : HttpStatus.OK)
                .header(
                        "X-Degraded",
                        Boolean.toString(data.degraded()))
                .body(data);
    }
}
```

Create `src/main/java/example/resilience/CatalogErrorAdvice.java`:

```java
package example.resilience;

import java.util.Map;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class CatalogErrorAdvice {

    @ExceptionHandler({
            CatalogPort.Unavailable.class,
            CatalogPort.Cancelled.class,
            CallNotPermittedException.class
    })
    public ResponseEntity<Map<String, String>> unavailable() {
        return ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("error", "catalog unavailable"));
    }

    @ExceptionHandler(CatalogPort.Rejected.class)
    public ResponseEntity<Map<String, String>> rejected() {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "upstream rejected request"));
    }
}
```

**Fallback responses are not HTTP success:** the body is only a status message, so the endpoint returns HTTP 503 + `X-Degraded: true`. With real cached data, an app might contract 200 with a stale marker and explicit TTL; never do that for synthetic text. Advice returns 503 when fallback is disabled, 502 on `Rejected`, and leaks no raw exceptions.

Create `src/main/java/example/resilience/ResilienceApplication.java`:

```java
package example.resilience;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResilienceApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ResilienceApplication.class, args);
    }
}
```

Create `src/main/resources/application.properties` using the properties table from section 5. This web app requires no database or broker. To run the application standalone, configure a reachable upstream URI.

## 13. `CatalogServiceTest.java`: sleep-free JUnit state machine tests

Create `src/test/java/example/resilience/CatalogServiceTest.java`:

```java
package example.resilience;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CatalogServiceTest {

    private static CatalogSettings settings(
            boolean breakerOn, boolean fallbackOn) {
        return new CatalogSettings(
                breakerOn, fallbackOn,
                500, 300, 4, 4, 50f, 30_000L, 2,
                "http://127.0.0.1:9999/catalog");
    }

    private static CircuitBreaker breaker(
            int window, int minCalls, int halfOpenCalls) {
        return CircuitBreaker.of(
                "test-catalog",
                CircuitBreakerConfig.custom()
                        .slidingWindowSize(window)
                        .minimumNumberOfCalls(minCalls)
                        .failureRateThreshold(50f)
                        .waitDurationInOpenState(
                                Duration.ofMinutes(10))
                        .permittedNumberOfCallsInHalfOpenState(
                                halfOpenCalls)
                        .recordExceptions(
                                CatalogPort.Unavailable.class)
                        .ignoreExceptions(
                                CatalogPort.Rejected.class,
                                CatalogPort.Cancelled.class)
                        .build());
    }

    @Test
    void primarySuccess() {
        CatalogService service = new CatalogService(
                () -> "fresh",
                breaker(2, 2, 2),
                settings(true, true));

        assertEquals(
                new CatalogResult("fresh", false),
                service.load());
    }

    @Test
    void enoughFailuresOpenBreakerAndSkipGateway() {
        AtomicInteger calls = new AtomicInteger();
        CatalogPort port = () -> {
            calls.incrementAndGet();
            throw new CatalogPort.Unavailable("offline");
        };

        CircuitBreaker cb = breaker(2, 2, 2);
        CatalogService service = new CatalogService(
                port, cb, settings(true, true));

        assertTrue(service.load().degraded());
        assertTrue(service.load().degraded());
        assertEquals(CircuitBreaker.State.OPEN, cb.getState());
        assertEquals(2, calls.get());

        assertTrue(service.load().degraded());
        assertEquals(2, calls.get());
    }

    @Test
    void minimumCallsPreventPrematureOpen() {
        CatalogPort port = () -> {
            throw new CatalogPort.Unavailable("one");
        };

        CircuitBreaker cb = breaker(4, 4, 2);
        CatalogService service = new CatalogService(
                port, cb, settings(true, true));

        assertTrue(service.load().degraded());
        assertEquals(
                CircuitBreaker.State.CLOSED, cb.getState());
    }

    @Test
    void disabledFallbackPropagatesFailure() {
        CatalogPort port = () -> {
            throw new CatalogPort.Unavailable("down");
        };

        CatalogService service = new CatalogService(
                port, breaker(2, 2, 2),
                settings(true, false));

        assertThrows(CatalogPort.Unavailable.class, service::load);
    }

    @Test
    void disabledBreakerBypassesOpenState() {
        AtomicInteger calls = new AtomicInteger();
        CatalogPort port = () -> {
            calls.incrementAndGet();
            return "primary";
        };

        CircuitBreaker cb = breaker(2, 2, 2);
        cb.transitionToOpenState();

        CatalogService service = new CatalogService(
                port, cb, settings(false, true));

        assertFalse(service.load().degraded());
        assertEquals(1, calls.get());
        assertEquals(CircuitBreaker.State.OPEN, cb.getState());
    }

    @Test
    void rejectedIsNotFallbackOrBreakerFailure() {
        CatalogPort port = () -> {
            throw new CatalogPort.Rejected("invalid");
        };

        CircuitBreaker cb = breaker(2, 2, 2);
        CatalogService service = new CatalogService(
                port, cb, settings(true, true));

        assertThrows(CatalogPort.Rejected.class, service::load);
        assertEquals(CircuitBreaker.State.CLOSED, cb.getState());
        assertEquals(0, cb.getMetrics().getNumberOfFailedCalls());
    }

    @Test
    void successfulHalfOpenProbesCloseCircuit() {
        AtomicInteger calls = new AtomicInteger();
        CatalogPort port = () -> {
            calls.incrementAndGet();
            return "recovered";
        };

        CircuitBreaker cb = breaker(2, 2, 2);
        cb.transitionToOpenState();
        cb.transitionToHalfOpenState();

        CatalogService service = new CatalogService(
                port, cb, settings(true, true));

        assertEquals("recovered", service.load().body());
        assertEquals("recovered", service.load().body());
        assertEquals(2, calls.get());
        assertEquals(CircuitBreaker.State.CLOSED, cb.getState());
    }

    @Test
    void failedHalfOpenProbeReopensCircuit() {
        CatalogPort port = () -> {
            throw new CatalogPort.Unavailable(
                    "still unhealthy");
        };

        CircuitBreaker cb = breaker(2, 2, 1);
        cb.transitionToOpenState();
        cb.transitionToHalfOpenState();

        CatalogService service = new CatalogService(
                port, cb, settings(true, true));

        assertTrue(service.load().degraded());
        assertEquals(CircuitBreaker.State.OPEN, cb.getState());
    }
}
```

**Eight test methods**, with no Spring context or network. They prove the breaker accumulates failures (2/2 opens), OPEN skips the gateway, minimum calls prevent premature trips, fallback toggles cleanly, breaker bypass works, 4xx skips fallback, healthy HALF_OPEN closes, and failing HALF_OPEN reopens.

**Do not confuse manual transitions with real elapsed time:** `transitionToHalfOpenState()` lets you test the state machine without sleeping 10 minutes, yet does not verify `waitDurationInOpenState` timing. To verify breaker clock expiration, inject a fake `Clock`/advance time per the Resilience4j version API rather than sleeping `30_000` ms. By default `automaticTransitionFromOpenToHalfOpenEnabled=false`, so after the wait elapses a permission check is typically needed to transition states.

## 14. `CatalogConfigurationTest.java`: property matrix and startup failures

Create `src/test/java/example/resilience/CatalogConfigurationTest.java`:

```java
package example.resilience;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CatalogConfigurationTest {
    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            CatalogConfiguration.class);

    @Test
    void defaultsAreBoundAndBreakerCreated() {
        runner.run(context -> {
            assertNull(context.getStartupFailure());
            CatalogSettings s =
                    context.getBean(CatalogSettings.class);
            CircuitBreaker cb =
                    context.getBean(CircuitBreaker.class);

            assertTrue(s.breakerEnabled());
            assertTrue(s.fallbackEnabled());
            assertEquals(500, s.connectTimeoutMs());
            assertEquals(300, s.requestTimeoutMs());
            assertEquals(4, s.slidingWindowSize());
            assertEquals(4, s.minimumCalls());
            assertEquals(50f,
                    cb.getCircuitBreakerConfig()
                            .getFailureRateThreshold());
        });
    }

    @Test
    void customValuesConfigureClientAndBreaker() {
        runner.withPropertyValues(
                        "app.catalog.breaker-enabled=false",
                        "app.catalog.fallback-enabled=false",
                        "app.catalog.connect-timeout-ms=900",
                        "app.catalog.request-timeout-ms=250",
                        "app.catalog.sliding-window-size=6",
                        "app.catalog.minimum-calls=3",
                        "app.catalog.failure-rate-threshold=75",
                        "app.catalog.open-wait-ms=1200",
                        "app.catalog.half-open-calls=1")
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    CatalogSettings s =
                            context.getBean(CatalogSettings.class);
                    CircuitBreaker cb =
                            context.getBean(CircuitBreaker.class);

                    assertFalse(s.breakerEnabled());
                    assertFalse(s.fallbackEnabled());
                    assertEquals(900, s.connectTimeoutMs());
                    assertEquals(250, s.requestTimeoutMs());
                    assertEquals(6,
                            cb.getCircuitBreakerConfig()
                                    .getSlidingWindowSize());
                    assertEquals(3,
                            cb.getCircuitBreakerConfig()
                                    .getMinimumNumberOfCalls());
                    assertEquals(75f,
                            cb.getCircuitBreakerConfig()
                                    .getFailureRateThreshold());
                    assertEquals(1200L, s.openWaitMs());
                    assertEquals(1, s.halfOpenCalls());
                });
    }

    @Test
    void flagsHaveFourIndependentCombinations() {
        String[][] matrix = {
            {"true", "true"}, {"true", "false"},
            {"false", "true"}, {"false", "false"}
        };

        for (String[] values : matrix) {
            runner.withPropertyValues(
                            "app.catalog.breaker-enabled="
                                    + values[0],
                            "app.catalog.fallback-enabled="
                                    + values[1])
                    .run(context -> {
                        assertNull(context.getStartupFailure());
                        CatalogSettings s =
                                context.getBean(CatalogSettings.class);

                        assertEquals(
                                Boolean.parseBoolean(values[0]),
                                s.breakerEnabled());
                        assertEquals(
                                Boolean.parseBoolean(values[1]),
                                s.fallbackEnabled());
                    });
        }
    }

    @Test
    void invalidWindowAndThresholdFailStartup() {
        runner.withPropertyValues(
                        "app.catalog.sliding-window-size=2",
                        "app.catalog.minimum-calls=3")
                .run(context ->
                        assertNotNull(context.getStartupFailure()));

        runner.withPropertyValues(
                        "app.catalog.failure-rate-threshold=0")
                .run(context ->
                        assertNotNull(context.getStartupFailure()));
    }

    @Test
    void derivedRunnerDoesNotMutateBaseline() {
        runner.withPropertyValues(
                        "app.catalog.fallback-enabled=false")
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    assertFalse(context.getBean(
                            CatalogSettings.class)
                            .fallbackEnabled());
                });

        runner.run(context -> {
            assertNull(context.getStartupFailure());
            assertTrue(context.getBean(
                    CatalogSettings.class)
                    .fallbackEnabled());
        });
    }
}
```

**Five test methods**: verify defaults, overridden timeouts/thresholds, all four breaker × fallback combinations, two invalid configurations, and context isolation. In the matrix test, each `runner.withPropertyValues(...).run(...)` creates a **fresh context**. No mutable global `System.setProperty` is used.

A note on negative tests: checking only that a bean is missing is insufficient if startup actually failed. For expected-success cases assert `context.getStartupFailure()==null`; for invalid configs assert startup failure is non-null. This tests the config factory, not HTTP transport.

## 15. `HttpCatalogAdapterTest.java`: real HTTP timeouts on loopback

To genuinely test `HttpRequest.timeout(...)`, run a local JDK 17 HTTP server on an ephemeral port rather than mocking `CatalogPort.fetch()` to throw an exception.

Create `src/test/java/example/resilience/HttpCatalogAdapterTest.java`:

```java
package example.resilience;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpCatalogAdapterTest {
    private HttpServer server;
    private ExecutorService serverWorkers;

    private void start(HttpHandler handler) throws IOException {
        server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        serverWorkers = Executors.newSingleThreadExecutor();
        server.setExecutor(serverWorkers);
        server.createContext("/catalog", handler);
        server.start();
    }

    private CatalogPort adapter(int timeoutMs) {
        CatalogSettings s = new CatalogSettings(
                true, true, 500, timeoutMs,
                4, 4, 50f, 30_000L, 2,
                "http://127.0.0.1:"
                        + server.getAddress().getPort()
                        + "/catalog");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(
                        Duration.ofMillis(s.connectTimeoutMs()))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        return new HttpCatalogAdapter(client, s);
    }

    private static HttpHandler reply(
            int code, String body) {
        return exchange -> {
            byte[] bytes = body.getBytes(
                    StandardCharsets.UTF_8);

            try (exchange) {
                exchange.sendResponseHeaders(code, bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        };
    }

    @AfterEach
    void cleanup() {
        if (server != null) {
            server.stop(0);
        }
        if (serverWorkers != null) {
            serverWorkers.shutdownNow();
        }
    }

    @Test
    void status200ReturnsUtf8Body() throws Exception {
        start(reply(200, "Payload 😀"));
        assertEquals("Payload 😀", adapter(2000).fetch());
    }

    @Test
    void status500IsUnavailable() throws Exception {
        start(reply(500, "error"));
        assertThrows(
                CatalogPort.Unavailable.class,
                () -> adapter(2000).fetch());
    }

    @Test
    void status400IsRejected() throws Exception {
        start(reply(400, "bad request"));
        assertThrows(
                CatalogPort.Rejected.class,
                () -> adapter(2000).fetch());
    }

    @Test
    void stalledResponseTriggersRequestTimeout()
            throws Exception {
        CountDownLatch received = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        start(exchange -> {
            received.countDown();

            try (exchange) {
                try {
                    if (!release.await(
                            5, TimeUnit.SECONDS)) {
                        return;
                    }
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    return;
                }

                byte[] bytes = "late".getBytes(
                        StandardCharsets.UTF_8);
                try {
                    exchange.sendResponseHeaders(200, bytes.length);
                    exchange.getResponseBody().write(bytes);
                } catch (IOException ignored) {
                    // Client may have closed the socket on timeout.
                }
            }
        });

        ExecutorService caller =
                Executors.newSingleThreadExecutor();

        try {
            Future<String> result =
                    caller.submit(() -> adapter(1200).fetch());

            assertTrue(received.await(3, TimeUnit.SECONDS));

            ExecutionException failure = assertThrows(
                    ExecutionException.class,
                    () -> result.get(4, TimeUnit.SECONDS));

            assertTrue(failure.getCause()
                    instanceof CatalogPort.Unavailable);
        } finally {
            release.countDown();
            caller.shutdownNow();
        }
    }
}
```

**Four HTTP integration tests:** 200 Unicode, 500, 400, and a stalled response. The final timeout test uses `CountDownLatch` to prove the server received the request, then verifies the JDK client terminates with `Unavailable`; no `Thread.sleep` is used. `Future.get(4s)` protects JUnit from hanging, **distinct** from the HTTP request timeout (1,200 ms). The test server and threads are cleaned up in `finally/@AfterEach`.

**Limitations:** this runs over loopback and does not test remote DNS, TLS/mTLS, proxies, packet loss, load balancers, or cloud latency. On heavily loaded CI runners, timeouts may need wider budgets; never assert exact elapsed milliseconds.

## 16. `CatalogControllerTest.java`: MockMvc HTTP contract

Create `src/test/java/example/resilience/CatalogControllerTest.java`:

```java
package example.resilience;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
class CatalogControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    CatalogService service;

    @Test
    void primary200IsNotDegraded() throws Exception {
        when(service.load()).thenReturn(
                new CatalogResult("fresh", false));

        mvc.perform(get("/catalog"))
                .andExpect(status().isOk())
                .andExpect(
                        header().string("X-Degraded", "false"))
                .andExpect(jsonPath("$.body").value("fresh"))
                .andExpect(
                        jsonPath("$.degraded").value(false));
    }

    @Test
    void fallback503HasDegradedMarker() throws Exception {
        when(service.load()).thenReturn(
                new CatalogResult(
                        "Catalog temporarily unavailable", true));

        mvc.perform(get("/catalog"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(
                        header().string("X-Degraded", "true"))
                .andExpect(
                        jsonPath("$.degraded").value(true));
    }

    @Test
    void rejection502DoesNotLeakPrivateReason()
            throws Exception {
        when(service.load()).thenThrow(
                new CatalogPort.Rejected("secret reason"));

        mvc.perform(get("/catalog"))
                .andExpect(status().isBadGateway())
                .andExpect(
                        jsonPath("$.error").value(
                                "upstream rejected request"));
    }
}
```

**Three MockMvc tests** use `@WebMvcTest` and `@MockitoBean` to mock the **service**: matching the goal of testing only the controller/advice. When verifying the state machine or fallback logic itself, test **real `CatalogService` + Resilience4j** rather than mocking it. These tests do not call upstream or prove timeouts fire.

## 17. Summary of JUnit methods and run commands

| Test class | Methods | Boundary |
| --- | ---: | --- |
| `CatalogServiceTest` | 8 | Real breaker, fake port |
| `CatalogConfigurationTest` | 5 | Context runner + properties |
| `HttpCatalogAdapterTest` | 4 | Real HTTP loopback |
| `CatalogControllerTest` | 3 | MockMvc response contract |
| **Total** | **20** | |

Linux/macOS:

```bash
./gradlew test --tests example.resilience.CatalogServiceTest
./gradlew test --tests example.resilience.CatalogConfigurationTest
./gradlew test --tests example.resilience.HttpCatalogAdapterTest
./gradlew test --tests example.resilience.CatalogControllerTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.resilience.CatalogServiceTest"
.\gradlew.bat test --tests "example.resilience.CatalogConfigurationTest"
.\gradlew.bat test --tests "example.resilience.HttpCatalogAdapterTest"
.\gradlew.bat test --tests "example.resilience.CatalogControllerTest"
```

**The count of 20 methods comes from the source definitions**, not a claim they were executed on the learner's machine. Gradle/JUnit logs have no fixed stdout across versions and runners. Only the Java SE demo below has exact deterministic stdout.

## 18. Standalone Java SE demo without Spring

Create `src/main/java/example/resilience/PolicyDecisionDemo.java`:

```java
package example.resilience;

public class PolicyDecisionDemo {
    enum Outcome {
        OK, TIMEOUT, OPEN, BAD_REQUEST
    }

    static String decide(
            Outcome outcome, boolean fallback) {
        if (outcome == Outcome.OK) {
            return "PRIMARY/200";
        }
        if (outcome == Outcome.BAD_REQUEST) {
            return "ERROR/502";
        }
        return fallback ? "DEGRADED/503" : "ERROR/503";
    }

    public static void main(String[] args) {
        System.out.println("ok=" + decide(Outcome.OK, true));
        System.out.println(
                "timeout=" + decide(Outcome.TIMEOUT, true));
        System.out.println(
                "open=" + decide(Outcome.OPEN, true));
        System.out.println(
                "4xx=" + decide(Outcome.BAD_REQUEST, true));
        System.out.println(
                "fallback-off="
                        + decide(Outcome.TIMEOUT, false));
    }
}
```

Java 17+ commands:

```bash
javac -d out src/main/java/example/resilience/PolicyDecisionDemo.java
java -cp out example.resilience.PolicyDecisionDemo
```

**Exact** stdout:

```text
ok=PRIMARY/200
timeout=DEGRADED/503
open=DEGRADED/503
4xx=ERROR/502
fallback-off=ERROR/503
```

This is a **Java SE policy decision model**, starting no real breaker, HTTP server, or Spring context. Never run this and claim `CircuitBreaker` opens properly; `CatalogService` JUnit tests verify the state machine.

## 19. Why not test HALF_OPEN using `Thread.sleep`?

A test written like:

```java
assertEquals(CircuitBreaker.State.OPEN, cb.getState());
Thread.sleep(30_000);
assertEquals(CircuitBreaker.State.HALF_OPEN, cb.getState());
```

is wrong under Resilience4j defaults: `automaticTransitionFromOpenToHalfOpenEnabled=false` means the breaker may require **a new permission request** after `waitDurationInOpenState` to move to HALF_OPEN. Sleeping and polling state does not confirm the transition.

The right strategy:

1. **Configuration test:** assert `openWaitMs` binds properly and the breaker factory builds the right config.
2. **State test:** invoke `transitionToOpenState()` and `transitionToHalfOpenState()` explicitly; verify probe counts and success/failure transitions.
3. **Clock test when required by business contract:** inject a `Clock`/fake time per the Resilience4j 2.3.x API or write a bounded integration test issuing a permission trigger. Never turn a suite into flaky multi-second sleeps.
4. **Real HTTP timeouts** cannot be replaced by a breaker fake clock; keep transport integration tests.

Thus the example's HALF_OPEN test proves state transitions under JUnit control, **not** exact wall-clock timing to the millisecond.

## 20. Retry, bulkhead, TimeLimiter, and idempotency

**Retry:** retry only transient errors, never every exception. Set max attempts, backoff+jitter, total deadlines, and load budgets; consider `Retry-After` on HTTP 429. For mutating POST/PUT requests, use idempotency keys or recovery flows. Never infinitely retry circuit-open rejections.

**Bulkhead:** caps concurrent calls/threads/permits. A CLOSED breaker still permits high call concurrency, so an HTTP connection pool can saturate before the breaker OPENS.

**TimeLimiter:** bounds `CompletionStage`/async waits; it does not guarantee blocking tasks or remote servers stop. Cancellation/interrupt propagation must be verified per client.

**Order:** `Retry(CircuitBreaker(Gateway))` causes the breaker to record every individual attempt; `CircuitBreaker(Retry(Gateway))` may count only the final outcome of the retry sequence. With annotation-based Resilience4j starters, AOP decorator ordering and proxies alter behavior.

**At-least-once:** in messaging and network retries, a logical event or request can execute repeatedly; consumers/processors must be idempotent. Never claim exactly-once just because a final retry succeeded. For payments, DBs, or S3, rely on stable `eventId`s, inboxes/outboxes, and reconciliation/compensation.

The core codebase **does not enable retry/TimeLimiter/Bulkhead**, so tests must not be interpreted as covering unimplemented features.

## 21. Fallback must never mask business discrepancies

Valid fallbacks include a 503 message, a cache with a strict TTL, or disabling an optional feature. Dangerous fallbacks include:

- Payments returning “success” after timeout while the provider may or may not have charged.
- Authorization defaulting to allow when the identity provider fails to respond.
- Accepting orders using stale prices/inventory without locking or constraint checks.
- Serving cached data belonging to another tenant when upstream returns 401.
- Logging a failed event/payment write while pretending durable persistence succeeded.

If a real cache fallback exists, define TTL/max stale age, tenant/user-scoped cache keys, schema versions, provenance, access permissions, response statuses, `X-Degraded` markers, `staleAgeMillis`, and cache-miss rules. A `CatalogResult(degraded=true)` is only a **degradation signal**, not proof that the payload is valid.

## 22. Spring Boot annotation-based Resilience4j differs from the core API

Projects using the Resilience4j starter may write:

```java
@CircuitBreaker(
        name = "catalog",
        fallbackMethod = "fallbackCatalog")
public String getCatalog() {
    return remoteCatalogClient.fetch();
}
```

This is a **non-standalone snippet**: it needs the starter/annotation dependency, imports, AOP proxy, and a version-compatible fallback method signature. Always test it through the **Spring-managed bean proxy**—calling `new Service()` or self-invoking `this.getCatalog()` bypasses the advice. The breaker name in the annotation must match instance config such as `resilience4j.circuitbreaker.instances.catalog.*`.

In this lesson's code, `CatalogConfiguration` instantiates the breaker and `CatalogService` invokes `decorateSupplier` directly, so **no AOP aspect is assumed**. Never add annotations without testing the Spring proxy.

With WebFlux, `Mono/Flux`, `WebClient`, and Reactor timeouts/cancellation are a separate topic. Never call blocking `HttpClient.send()` on an event-loop thread calling it non-blocking.

## 23. Telemetry, health, and CI

Metrics to separate:

| Signal | What to watch |
| --- | --- |
| Breaker state | CLOSED/OPEN/HALF_OPEN |
| Failure/slow-call rate | Primary dependency health |
| Not-permitted calls | Calls blocked by the breaker |
| HTTP timeouts | Real transport timeouts |
| Fallback count/rate | Degraded user experience |
| Upstream 429/5xx | Rate limits and server outages |
| Retry attempts/backoff | Load amplification |
| HTTP pool/bulkhead saturation | Contended resources |
| p95/p99 latency | End-to-end user impact |
| Cache stale age | Fallback cache freshness |

Adding Spring Boot Actuator/Micrometer + Resilience4j metrics integration exposes metrics, tracing, and health. **This lesson's build file omits those modules**, so never claim `/actuator/metrics` or health indicators are available here.

**Liveness/readiness:** an OPEN breaker for an optional upstream should not fail liveness. Wiring non-critical dependencies into startup/readiness can trigger pod restart loops during outages. Base probe policies on core serviceability, not habit.

**CI:** run fast unit/config/MVC tests on every commit; run loopback HTTP tests in integration jobs if runner resources vary. Never point tests at production URLs, hardcode TCP ports, store credentials, disable timeouts, or skip mandatory tests. On timeout errors, safely log breaker state, upstream status, elapsed time, config version, and thread/connection pool metrics.

## 24. Debugging by symptom

**A. Requests hang while breaker stays CLOSED:** breakers do not enforce timeouts; check connect/request timeouts, pool acquisition, DNS, and TLS.

**B. Breaker stays CLOSED after a failure:** `minimumCalls` and failure-rate threshold require enough samples; inspect window size and exception classification.

**C. Breaker is OPEN yet upstream still gets calls:** calls admitted prior to OPEN may still be running, or another code path bypasses the breaker/flag is off.

**D. Breaker stays OPEN forever:** inspect `openWaitMs`, permission triggers, half-open probe outcomes, and automatic transition settings.

**E. Fallback triggers on upstream 401/403:** catch block is too broad; distinguish `Rejected` and auth errors.

**F. Breaker never sees failures:** fallback runs inside the measured block, or a new breaker is created per request.

**G. Tests pass individually, fail as a full suite:** shared static breakers, context caching, global System properties, or unclosed HTTP servers/executors.

**H. HTTP server timeout test misbehaves:** server may not have received the request or held the handler; check latches and finite `Future.get` bounds.

**I. Spring AOP annotations do not fire:** self-invocation, non-proxied object, missing starter/AOP, or mismatched fallback signature.

**J. Property overrides have no effect:** bean created before config override, wrong namespace, or Spring context caching.

**K. Retry storms in production:** misconfigured max attempts/backoff/deadlines/permissions, or all replicas retrying simultaneously.

**L. Degraded responses return invalid prices:** stale fallback cache lacks TTL/authorization; fail closed instead.

## 25. Common pitfalls

1. Confusing a circuit breaker with a timeout; forgetting to configure HTTP client timeouts.
2. Treating a client timeout as proof the server rolled back.
3. Catching all exceptions and returning 200 fallback, masking bugs or auth errors.
4. Placing fallback inside the breaker-measured block so metrics record only successes.
5. Creating a new breaker per request so the sliding window never fills.
6. Ignoring `minimumCalls`/thresholds and asserting OPEN after one error.
7. Calling `Thread.sleep` to wait for HALF_OPEN without understanding permission transitions.
8. Confusing a `COUNT_BASED` window with seconds.
9. Expecting OPEN to cancel already in-flight calls.
10. Retrying `CallNotPermittedException` repeatedly.
11. Lacking bulkhead/connection pool limits, causing resource exhaustion.
12. Retrying write APIs without idempotency keys, creating duplicate side effects.
13. Throwing a timeout exception from Mockito and calling it an HTTP integration test.
14. Testing only success requests while ignoring 429/5xx/4xx/timeouts.
15. Missing the `breaker-enabled × fallback-enabled` matrix.
16. Silently accepting invalid windows, minimums, or durations in config.
17. Testing annotation-based breakers via direct calls that bypass AOP proxies.
18. Confusing custom `app.catalog.*` properties with Resilience4j starter config.
19. Serving unverified prices, stock, or permissions from fallback.
20. Omitting degraded markers, stale timestamps, or HTTP status policies.
21. Hardcoding loopback ports in tests, colliding in parallel CI.
22. Failing to shut down HTTP servers/executors and release latches on test failure.
23. Asserting exact millisecond timings, causing flakiness.
24. Assuming a succeeding fallback means upstream recovered.
25. Missing metrics for fallbacks, timeouts, open state, and not-permitted calls.

## 26. Final QA checklist

**Architecture and config:** Is upstream behind a dedicated port? Are timeouts set on JDK `HttpClient`? Does the breaker bean outlive a single request? Is the config record bound via `@EnableConfigurationProperties`? Are `minCalls`/window, threshold, and durations validated? Do tests cover defaults and overrides?

**Circuit breaker tests:** Does it require enough calls before OPENING? Does OPEN skip the port? Are HALF_OPEN success/fail probes tested? Are 4xx/cancellations ignored per policy? Does fallback sit outside the breaker decorator? Are tests free of sleeps and uncoupled from wall-clock time?

**HTTP tests:** Is there a real loopback server on an ephemeral port testing real request timeouts? Are Unicode 200, 500, 400, and stalled responses covered? Are timeouts finite with server/executor/latch cleanup? Have you avoided claiming client timeouts equal remote rollbacks?

**Fallback/API tests:** Can breaker and fallback flags toggle independently? Does degraded mode emit 503 + `X-Degraded: true` and JSON body? Are 4xx/auth errors never masked? Is risky stale data avoided? Does typed error advice hide secrets? Are MockMvc tests scoped accurately without claiming full E2E?

**Operations:** Do retries include backoff/deadlines/idempotency? Are bulkheads and pool limits present? Are p95/p99, breaker state/timeout/fallback metrics tracked? Do health/readiness probes avoid restart loops? Does CI stay isolated from production upstreams with zero state leakage?

**Conclusion:** **Timeouts** cap waiting duration, **circuit breakers** protect upstreams by halting **new** calls when error metrics degrade, and **fallbacks** provide conditional degraded business responses. Use JUnit for time-independent state machine tests, `ApplicationContextRunner` for configuration matrices, loopback HTTP for real timeouts, and MockMvc to guard the HTTP contract. Claim only what each boundary actually tests; never infer consistency, exactly-once semantics, or security from a green unit test.

## 27. References

- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): states, sliding windows, failure rates, decorators, and permissions.
- [Resilience4j CircuitBreakerConfig source](https://github.com/resilience4j/resilience4j/blob/master/resilience4j-circuitbreaker/src/main/java/io/github/resilience4j/circuitbreaker/CircuitBreakerConfig.java): builder, failure classification, time settings.
- [Resilience4j 2.3.0 artifact](https://mvnrepository.com/artifact/io.github.resilience4j/resilience4j-circuitbreaker/2.3.0): pinned version used.
- [Spring Boot 3.5 — External Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): `@ConfigurationProperties` and `@DefaultValue`.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `ApplicationContextRunner`, MockMvc, test slices.
- [Java SE 17 HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `connectTimeout` and synchronous `send`.
- [Java SE 17 HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request timeout.
- [Java SE 17 HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback test server.
- [Spring Framework MockitoBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): test bean overrides.
