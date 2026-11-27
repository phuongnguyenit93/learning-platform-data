# Integration Testing with Mock HTTP and an Isolated Registry

## Objectives

A unit test can verify a fallback function or exception classification in isolation, but it does not prove that the entire Spring flow works properly. An integration test must initialize the application context, create a Circuit Breaker through the real factory, send HTTP requests to a mocked upstream, and observe both state and actual request counts. The Resilience4j registry should be created specifically for the test context so that state from one test does not leak into another.

After this lesson, you will be able to:

- Use WireMock to simulate successful responses, HTTP errors, and dependency latency.
- Initialize a Spring Boot test context with a real `CircuitBreakerFactory`.
- Create an isolated `CircuitBreakerRegistry` inside the test context and inspect instance state.
- Verify fallbacks, upstream request counts, and `CLOSED`-to-`OPEN` state transitions.
- Keep tests stable using dynamic ports, small threshold configurations, and resource cleanup.
- Distinguish Circuit Breaker testing from timeout, retry, and Bulkhead testing.

## Why Integration Testing Is Necessary

A unit test invoking a fallback directly can prove that the fallback returns the expected string or DTO. However, it cannot verify:

- Whether Spring creates the right `CircuitBreakerFactory` and binds the instance configuration properly.
- Whether the HTTP client actually sends requests to the upstream.
- Whether exceptions thrown by the HTTP client are recorded by the Circuit Breaker.
- Whether the supplier is blocked before creating additional HTTP requests when the circuit is `OPEN`.
- Whether the fallback is invoked and returns a response matching the contract.
- Whether the registry observed by the test is the same registry used by the integration.

Integration testing uses a mock HTTP server to control upstream outcomes. Tests do not need to start a real `catalog-service` or depend on external networks. At the same time, an isolated registry in the Spring context ties the Circuit Breaker's lifecycle to the test, making it easy to observe and preventing unintended sharing.

## Test Dependencies

The example uses Spring Cloud CircuitBreaker with Resilience4j, Spring Boot Test, and Spring Cloud Contract WireMock. Spring Boot, Spring Cloud, and Resilience4j versions should be managed by your project's compatible BOM.

Maven example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-contract-wiremock</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

If the project uses Gradle, declare the equivalent artifacts under `testImplementation`. Do not manually mix in a WireMock or Resilience4j major version different from what the Spring Cloud BOM manages; inspect the dependency tree of your exact release train before upgrading versions.

## Creating a Gateway That Uses the Real Factory

The gateway must create the Circuit Breaker with a stable ID and place the entire HTTP call inside the `run` supplier:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogGateway {
    private final RestClient restClient;
    private final CircuitBreaker circuitBreaker;

    public CatalogGateway(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl,
            CircuitBreakerFactory<?, ?> factory) {
        this.restClient = builder.baseUrl(baseUrl).build();
        this.circuitBreaker = factory.create("catalog");
    }

    public String findById(String id) {
        return circuitBreaker.run(
                () -> restClient.get()
                        .uri("/products/{id}", id)
                        .retrieve()
                        .body(String.class),
                error -> "catalog-fallback");
    }
}
```

`RestClient.Builder` is provided by Spring Boot when the application has the corresponding HTTP client configuration. The `catalog` ID must match the instance in the Resilience4j configuration. In this example, `retrieve()` throws an exception on HTTP 5xx responses according to RestClient's default error handling; the exception is passed to the Circuit Breaker and fallback.

To keep tests focused on the Circuit Breaker, do not place the HTTP request outside the supplier. If the HTTP call runs before `run` and only its result is passed into the Circuit Breaker, an `OPEN` circuit cannot prevent the request.

## Starting WireMock on a Dynamic Port

The test needs a mock HTTP server. Use a dynamic port to avoid conflicts when running in parallel or when a developer machine already has a process occupying a default port.

```java
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

import com.github.tomakehurst.wiremock.WireMockServer;

class WireMockSupport {
    static final WireMockServer UPSTREAM = startServer();

    private static WireMockServer startServer() {
        WireMockServer server = new WireMockServer(wireMockConfig().dynamicPort());
        server.start();
        return server;
    }
}
```

`UPSTREAM.baseUrl()` returns the address with the actual port after the server starts. Use `@DynamicPropertySource` to inject that address into the Spring context:

```java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.base-url", WireMockSupport.UPSTREAM::baseUrl);
}
```

In a real test class, you can declare the server as a static field and stop it in `@AfterAll`. It is important that the server starts before Spring reads the dynamic property and stops once the test context no longer uses it.

## Isolating CircuitBreakerRegistry for the Test Context

Resilience4j stores Circuit Breaker instances in `CircuitBreakerRegistry`. If multiple tests share a long-lived registry, one test may leave an instance in `OPEN`; the next test will keep receiving `CallNotPermittedException` even before sending enough failing requests.

You can provide an isolated registry in the test context:

```java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
class IsolatedCircuitBreakerConfiguration {
    @Bean
    @Primary
    CircuitBreakerRegistry testCircuitBreakerRegistry() {
        CircuitBreakerConfig testDefaults = CircuitBreakerConfig.custom()
                .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(4)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .build();
        return CircuitBreakerRegistry.of(testDefaults);
    }
}
```

Import this configuration into your test with `@Import(IsolatedCircuitBreakerConfiguration.class)`. When the Resilience4j integration obtains its registry as a Spring bean, this `@Primary` bean is used and the registry lifecycle belongs to the test context. If your integration version or project configuration creates a registry via another mechanism, verify that the real factory uses this test bean; do not simply autowire a different registry and assume it holds the instance created by the factory.

In the test, you can inject `CircuitBreakerRegistry` and read the `catalog` instance with `registry.find("catalog")`. This is also a way to verify that the instance used by the factory was registered in the test registry.

`CircuitBreakerRegistry.of(testDefaults)` creates a registry independent of the global default registry and sets small baseline thresholds for tests. `@TestPropertySource` simultaneously declares the instance configuration that the Spring Cloud CircuitBreaker integration can bind depending on the version in use. Keep both sets of values consistent; if your project's integration configures instances directly through the factory, confirm that the factory uses the test registry and desired `catalog` config rather than relying solely on autowiring the registry.

## Configuring Small Thresholds for Tests

Production typically needs a sliding window and wait duration large enough to avoid overreacting to a few sporadic requests. Integration tests should use a small window to transition state deterministically with few requests:

```java
@SpringBootTest
@Import(IsolatedCircuitBreakerConfiguration.class)
@TestPropertySource(properties = {
        "resilience4j.circuitbreaker.instances.catalog.sliding-window-type=COUNT_BASED",
        "resilience4j.circuitbreaker.instances.catalog.sliding-window-size=4",
        "resilience4j.circuitbreaker.instances.catalog.minimum-number-of-calls=4",
        "resilience4j.circuitbreaker.instances.catalog.failure-rate-threshold=50",
        "resilience4j.circuitbreaker.instances.catalog.wait-duration-in-open-state=30s"
})
class CatalogGatewayIntegrationTest {
    // Test implementation follows.
}
```

With four samples and a 50% failure threshold, three consecutive error responses after one success are enough to move the Circuit Breaker to `OPEN`. A 30-second `OPEN` wait duration gives the test plenty of time to verify that the next call is rejected without automatically transitioning to `HALF_OPEN` between assertions. This is a test configuration; do not copy these values verbatim into production.

## Complete Integration Test

The example below tests one successful request, three HTTP 500 errors, the `OPEN` state, and a fifth request rejected before reaching WireMock:

```java
import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.getRequestedFor;
import static com.github.tomakehurst.wiremock.client.WireMock.okJson;
import static com.github.tomakehurst.wiremock.client.WireMock.urlPathEqualTo;
import static org.assertj.core.api.Assertions.assertThat;

import com.github.tomakehurst.wiremock.WireMockServer;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestPropertySource;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(IsolatedCircuitBreakerConfiguration.class)
@TestPropertySource(properties = {
        "resilience4j.circuitbreaker.instances.catalog.sliding-window-type=COUNT_BASED",
        "resilience4j.circuitbreaker.instances.catalog.sliding-window-size=4",
        "resilience4j.circuitbreaker.instances.catalog.minimum-number-of-calls=4",
        "resilience4j.circuitbreaker.instances.catalog.failure-rate-threshold=50",
        "resilience4j.circuitbreaker.instances.catalog.wait-duration-in-open-state=30s"
})
class CatalogGatewayIntegrationTest {
    private static final WireMockServer UPSTREAM = WireMockSupport.UPSTREAM;

    @Autowired
    private CatalogGateway gateway;

    @Autowired
    private CircuitBreakerRegistry registry;

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry properties) {
        properties.add("catalog.base-url", UPSTREAM::baseUrl);
    }

    @BeforeEach
    void resetUpstream() {
        UPSTREAM.resetAll();
    }

    @AfterAll
    static void stopUpstream() {
        UPSTREAM.stop();
    }

    @Test
    void opensCircuitAfterFailuresAndRejectsNextRequest() {
        UPSTREAM.stubFor(get(urlPathEqualTo("/products/ok"))
                .willReturn(okJson("{\"id\":\"ok\"}")));
        UPSTREAM.stubFor(get(urlPathEqualTo("/products/42"))
                .willReturn(aResponse().withStatus(500)));

        assertThat(gateway.findById("ok")).contains("ok");
        assertThat(gateway.findById("42")).isEqualTo("catalog-fallback");
        assertThat(gateway.findById("42")).isEqualTo("catalog-fallback");
        assertThat(gateway.findById("42")).isEqualTo("catalog-fallback");

        CircuitBreaker breaker = registry.find("catalog").orElseThrow();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        // This call is rejected by the Circuit Breaker; upstream does not receive a fifth request.
        assertThat(gateway.findById("42")).isEqualTo("catalog-fallback");

        UPSTREAM.verify(1, getRequestedFor(urlPathEqualTo("/products/ok")));
        UPSTREAM.verify(3, getRequestedFor(urlPathEqualTo("/products/42")));
    }
}
```

The example uses `WireMockSupport` to keep server initialization separate. In a real project, you can place helpers and test configurations in dedicated test files for reuse.

This test proves multiple layers working together:

1. Spring instantiates `CatalogGateway` and injects `CircuitBreakerFactory`.
2. The gateway sends HTTP requests to WireMock instead of a real `catalog-service`.
3. One successful request and three HTTP 500 requests are recorded by the Circuit Breaker.
4. After four samples, the failure rate is 75%, exceeding the 50% threshold, so the circuit transitions to `OPEN`.
5. The next request receives the fallback due to Circuit Breaker rejection; WireMock receives only three error requests and one successful request.

If the test observes that the fifth request still reaches the upstream, check which registry the factory uses, the instance name, the bound configuration, and where the HTTP call is placed inside the supplier.

## Scenario-by-Scenario Mock HTTP Testing

WireMock can simulate various responses to test different situations:

| Scenario | HTTP stub | What to verify |
|---|---|---|
| Healthy upstream | 200 with valid JSON. | Gateway returns real data; Circuit Breaker records success. |
| Upstream server error | 500 or 503. | Client throws exception; Circuit Breaker records failure and fallback is invoked. |
| Slow upstream | Delay greater than configured timeout. | TimeLimiter or HTTP client timeout terminates the call per policy. |
| Unreachable upstream | Stop server or use a port with no listener. | Connection error is classified and handled as expected. |
| Circuit `OPEN` | No new stub needed. | Supplier does not run; WireMock request count does not increase. |
| Recovery | Return 200 after `OPEN` duration. | `HALF_OPEN` probes succeed and circuit can return to `CLOSED`. |

WireMock example for a slow response:

```java
UPSTREAM.stubFor(get(urlPathEqualTo("/products/slow"))
        .willReturn(aResponse()
                .withStatus(200)
                .withFixedDelay(1_500)
                .withBody("{\"id\":\"slow\"}")
                .withHeader("Content-Type", "application/json")));
```

If the HTTP client timeout is 500 ms, the request may fail before WireMock returns the response. Do not rely on `TimeLimiter` alone: test both HTTP-client-layer timeouts and request cancellation capability. When a timeout occurs, the mock server may still finish writing the response even after the client disconnected.

## Isolating the Registry Across Multiple Tests

Three principles prevent tests from depending on execution order:

- Create a fresh `CircuitBreakerRegistry` inside the test application context instead of using a single static registry shared across the entire suite.
- Use `@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)` when you need to close the context after the class and ensure beans/registries are recreated on subsequent runs.
- If testing multiple states within the same context, use distinct IDs per scenario or explicitly reset state using the appropriate API; do not rely on implicit test ordering.

Example:

```java
import org.springframework.test.annotation.DirtiesContext;

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class CatalogGatewayIntegrationTest {
    // Test context and registry are closed after the class.
}
```

If using `@TestInstance(PER_CLASS)` or keeping a static WireMock server, still manage the server lifecycle separately. Closing the Spring context does not automatically stop a manually created `WireMockServer` unless a cleanup mechanism is registered.

Do not create a new registry inside every assertion or on every gateway call. The goal is to isolate the registry per test context, whereas calls within the same scenario must pass through the same instance so it can accumulate samples and transition state.

## Testing HALF_OPEN Without Long Sleeps

After the Circuit Breaker is `OPEN`, once `waitDurationInOpenState` elapses, the circuit can transition to `HALF_OPEN`. Tests should manage wait times to avoid slow and flaky runs:

- Use a short `waitDurationInOpenState` in the test profile, yet long enough for `OPEN` assertions to complete.
- Use Awaitility or bounded polling to wait for state conditions instead of long fixed `Thread.sleep` calls.
- Set `permittedNumberOfCallsInHalfOpenState` small to verify probe counts.
- Once the circuit transitions to `HALF_OPEN`, stub several successful responses and verify the circuit returns to `CLOSED` when enough outcomes arrive.
- Create another scenario with failing probes to confirm the circuit returns to `OPEN`.

Do not use `waitDurationInOpenState: 0` if your goal is to observe a stable `OPEN` state: the circuit may transition too quickly as soon as a new request arrives. For tests requiring strict time control, use a clock supported by your Resilience4j version or test state transitions separately at the registry level; do not assume every integration lets you inject a clock through the factory.

## Verifying Fallbacks and the Response Contract

Fallbacks must be verified as part of the API contract, not merely by checking that some arbitrary value was returned:

- For cached data, verify metadata fields indicate stale or degraded data.
- For an unavailable dependency, verify the appropriate status and error code.
- For business errors such as 404, verify they are not turned into infrastructure fallbacks if policy does not treat them as Circuit Breaker errors.
- For write operations, verify timeouts do not produce fake success results and retries use an idempotency key if supported.
- Verify the fallback does not call the failing upstream again.

If the gateway returns a DTO, deserialize the response and assert key fields instead of comparing an entire JSON string. If the gateway returns an HTTP status, use `WebTestClient` or `MockMvc` appropriate for the application type to verify status, headers, and body at the controller boundary.

## Limitations of Isolated Registry and Mock HTTP Tests

An isolated registry proves the state machine within one JVM and one Spring context. It does not simulate state synchronization across multiple pods; Resilience4j Circuit Breakers generally keep state locally per application instance.

WireMock simulates the HTTP protocol and configured responses. It does not fully simulate TLS, DNS, load balancers, network partitions, connection reuse, file descriptor limits, or real upstream load. Load tests and staging environments are still necessary to validate pool sizing, percentile latency, and recovery behavior.

A mock HTTP server returning 500 helps test client exception classification. If the application uses reactive `WebClient`, write tests following the reactive pipeline and verify subscriptions; do not use a synchronous test to infer full reactive semantics.

## Common Mistakes

- **Mocking `CircuitBreakerFactory` instead of using the real factory:** the test stops verifying integration, registry, and instance configuration.
- **Using a shared static registry across all tests:** an `OPEN` state from an earlier test can cause later tests to fail.
- **Autowiring a different registry from the factory's registry:** assertions observe state that does not reflect actual calls.
- **Using a fixed port:** tests can collide with other processes or parallel runs.
- **Forgetting to reset WireMock:** mappings and request journals from previous tests can affect assertions.
- **Not placing the HTTP call inside the supplier:** the Circuit Breaker cannot block requests when `OPEN`.
- **Asserting only the fallback:** you do not know whether the upstream was called again; verify request counts.
- **Using overly large production thresholds:** tests require too many requests or run too long before changing state.
- **Using long fixed sleeps:** makes tests slow and flaky on CI.
- **Forgetting to stop WireMock:** server ports and threads may remain alive after tests.
- **Assuming WireMock tests prove production networking:** staging and load tests are still needed for real connection/pool issues.

## Complete Practice Exercise

Create a test class with a Spring Boot context, real `CircuitBreakerFactory`, isolated registry, and a dynamic-port WireMock server. Run these scenarios in sequence:

1. Successful request: verify the real response body is returned and the registry records success.
2. HTTP 500 request: verify fallback, failure count, and upstream request count.
3. Consecutive errors: verify the Circuit Breaker transitions to `OPEN` once `minimumNumberOfCalls` and failure threshold are reached.
4. Request while `OPEN`: verify fallback is invoked while WireMock receives no additional requests.
5. Slow upstream: verify HTTP client or TimeLimiter timeout terminates the call per configuration.
6. Upstream recovery: verify `HALF_OPEN` probes are bounded and the circuit returns to `CLOSED` once enough successful outcomes arrive.
7. Re-run the class or test suite in a different order: verify a fresh registry is created and does not depend on state from the previous run.

Record the Circuit Breaker state, actual call count to WireMock, fallback count, processing time, and exception types. A good integration test must prove both application behavior and that the dependency receives no further calls once the Circuit Breaker has opened.
