# Simulating Slow, Failing, Disconnected, or Invalid-Payload Dependencies

## 1. Lesson scope and why fault injection is needed

In Spring Boot, a use case frequently calls external systems: REST APIs, databases, caches, payment gateways, identity providers, message brokers, or object storage. A test suite that only simulates `200 OK` and clean data misses failure modes production must handle:

- **Latency:** the partner accepts the connection yet delays headers or body excessively.
- **HTTP errors:** `400`, `401`, `404`, `409`, `429`, `500`, `502`, `503`, `504` with distinct semantics.
- **Connection drops:** connection refused, connect timeout, socket reset, premature EOF, DNS/TLS failures.
- **Bad payloads:** empty body, malformed JSON, mismatched `Content-Type`, missing or wrong-typed fields.
- **Invalid business data:** negative inventory, response ID differing from requested ID, stale timestamps.
- **Broken recovery:** unbounded retries, missing timeouts, fallbacks returning fabricated data, bypassed circuit breakers, POST retries creating duplicates.
- **Poor observability:** every failure swallowed into a generic `RuntimeException` with no status, cause, or indication of which downstream failed.

This lesson belongs to **Contracts and Resilience**, topic **“Simulating slow, failing, disconnected, or invalid-payload dependencies”**. Example stack: **Java 17+**, **Spring Boot 3.3.5**, **Spring Framework 6.1**, and **MockWebServer 4.12.0**. In the runnable project, we build a `CatalogGateway` using blocking `RestClient` and simulate an HTTP partner using a `localhost` server on an ephemeral port. These tests do not call the internet or production partners.

### Skills to master

1. Pick the right mock layer: Mockito, `MockRestServiceServer`, MockWebServer/WireMock, Testcontainers, or provider sandboxes.
2. Distinguish HTTP errors **that return a status** from network failures **without an HTTP response**.
3. Configure connect and read timeouts on a real HTTP request factory.
4. Simulate 404/429/400/503 statuses, delayed headers, closed ports, and mid-body disconnects.
5. Parse JSON into DTOs, check syntax and semantics, and fail closed on invalid payloads.
6. Map framework exceptions into domain exceptions for services/controllers.
7. Assert request path/method/headers and exact request count.
8. Keep each test isolated with bounded waits and cleanup.
9. Evaluate retry/idempotency/circuit-breaker/fallback rules by operation type.
10. Separate what test code proves from what is only verified after an actual Gradle execution.

## 2. Four boundaries you must not mix

```text
Caller / service invokes CatalogGateway.find(sku)
             |
       [A] Input validation
             | invalid sku -> reject, zero HTTP calls
             v
       [B] HTTP client/transport
             | connect, send, await headers, stream body
             v
       [C] Remote HTTP protocol & JSON
             | status, headers, content type, schema
             v
       [D] Domain mapping
             | ItemMissing / RateLimited
             | RemoteUnavailable / BadRemotePayload
             v
       Caller policy: response, fallback, retry, alert
```

Stubbing `CatalogGateway.find` with Mockito **does not** test serialization, URLs, transport timeouts, or HTTP statuses. Using `MockRestServiceServer` to inject responses in memory **does not** exercise the request factory's DNS/TCP/TLS stack. Using local `MockWebServer` exercises real HTTP sockets, yet still does not prove the real provider shares the same contract or that production certs/proxies work.

A well-designed test explicitly identifies **which layer is the subject under test** and **what serves as the controlled test double**.

## 3. Fault matrix and expected outcomes

| Simulated fault | Failure source | Example Gateway expectation |
| --- | --- | --- |
| 200 valid JSON | HTTP body | `InventoryItem` with matching SKU and count |
| 404 | HTTP client error | `ItemMissing` |
| 429 + Retry-After | HTTP rate limit | `RateLimited` preserving hint |
| 400 | HTTP rejected request | `RemoteRejected` |
| 502/503 | HTTP server error | `RemoteUnavailable` |
| 204 empty body | Contract expects object | `BadRemotePayload` |
| 200 malformed JSON | JSON decoder | `BadRemotePayload` |
| 200 `available=-4` | Domain invariant | `BadRemotePayload` |
| 200 wrong SKU in response | Cross-request invariant | `BadRemotePayload` |
| 200 `text/plain` for DTO | Message converter | `BadRemotePayload` |
| Header delay exceeding read timeout | I/O | `RemoteUnavailable` |
| Closed port, unable to connect | TCP | `RemoteUnavailable` |
| Disconnect mid-response | Transport/parser | Must never return a valid `InventoryItem` |
| Invalid caller SKU | Pre-I/O | `IllegalArgumentException`; 0 HTTP requests |
| HTTP 503 with no retry configured | Gateway policy | Exactly one request |

**This is an illustrative policy choice**, not a universal rule for every system. Another API may treat 404 as `Optional.empty()`, defer jobs on HTTP 429, or fall back on 502. Decisions must follow the real service contract.

## 4. Choosing the right mock tool

| Tool | Real TCP? | Best for | Blind spots |
| --- | --- | --- | --- |
| Mockito mock of Gateway/repository | No | Service logic, branch/retry policy | HTTP mapping and transport never run |
| `MockRestServiceServer` | No | REST URL, method, headers, JSON/status | Does not exercise client socket I/O |
| **OkHttp MockWebServer** | **Yes**, loopback | Delays, socket drops, 429/503, bodies, request capture | Does not reflect TLS, internet DNS, or real provider |
| WireMock | Yes | Scenario state, templating, fault simulation | Heavier than a simple MockWebServer |
| Testcontainers PostgreSQL/Kafka/Redis | Yes | Real driver/protocol/schema/commits | Requires container lifecycle and resources |
| Provider sandbox | Yes | Real provider compatibility | Secrets, rate limits, mutable data |

Spring Framework recommends mock web servers such as OkHttp MockWebServer or WireMock when testing real HTTP clients, because different HTTP client implementations behave differently at the network boundary. `MockRestServiceServer` remains ideal for fast, small, socket-free contract assertions.

### @RestClientTest and MockRestServiceServer

Illustrative snippet:

```java
server.expect(requestTo(
        "https://api.example.invalid/v1/inventory/SKU-1"))
    .andExpect(method(HttpMethod.GET))
    .andRespond(withServerError());
```

This snippet requires a `@RestClientTest` slice, a `MockRestServiceServer server`, a client under test, and static imports. It is **not** part of the main runnable project. When `RestClient.Builder` is used in a slice, expected URIs are full URLs; `RestTemplateBuilder.rootUri` matchers have different semantics. If production config overrides `ClientHttpRequestFactory` after mock binding, the client can escape the mock server; verify the builder and request factory are wired properly.

**Do not put `Thread.sleep` inside a mock response creator to claim you tested a TCP client's read timeout.** For transport faults, use a real local mock HTTP server.

## 5. Connect timeouts, read timeouts, and request deadlines

- **Connect timeout** bounds the TCP handshake duration. On a closed localhost port, the OS typically returns “connection refused” immediately; that is **not** proof that connect timeout expired.
- **Read timeout** bounds waiting for socket data. A server accepting a request yet delaying headers is a classic trigger.
- **Total deadline** covers connect + request + body + retries/backoffs; configuring only connect/read timeouts does not enforce a total deadline automatically.
- **Gateway/proxy timeouts** can produce HTTP 504, distinct from Java `SocketTimeoutException`.
- **Body read timeouts** depend on the request factory and how responses are streamed.

In Spring Framework 6.1, `SimpleClientHttpRequestFactory` supports:

```java
SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();

factory.setConnectTimeout(Duration.ofSeconds(2));
factory.setReadTimeout(Duration.ofMillis(900));
```

These values are **test settings**, not production SLO recommendations. For URLConnection, a zero timeout can mean **infinite**; never pass zero to simulate a zero deadline.

### Avoid asserting exact elapsed milliseconds

If a test uses a stopwatch expecting failure at `900 ms ± 10 ms`, CI can flake due to CPU load, GC, or OS scheduling. Instead, configure the server to delay headers **3 seconds** against a **900 ms** read timeout and assert the failure category. This uses a “wide margin” rather than acting as a performance benchmark.

## 6. Project structure: Java 17+ / Spring Boot 3.3.5

```text
catalog-fault-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/faults/
│   ├── FaultLabApplication.java
│   ├── InventoryItem.java
│   ├── CatalogGateway.java
│   ├── RemoteCatalogProperties.java
│   └── RemoteCatalogConfiguration.java
└── src/test/java/com/example/faults/
    └── CatalogGatewayNetworkTest.java
```

The project includes a `@SpringBootApplication` class and production configuration, while the test suite constructs the Gateway via **the exact factory method used in production** and calls a real `MockWebServer` on localhost. Tests skip `@SpringBootTest` because they focus on HTTP adapter fault injection rather than component scanning or web server startup.

MockWebServer 4.12.0 uses package `okhttp3.mockwebserver`. MockWebServer 5.x APIs may differ.

## 7. Gradle scripts

### settings.gradle

```groovy
rootProject.name = 'catalog-fault-lab'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-web` provides Spring Web/`RestClient` and Jackson. `spring-boot-starter-test` provides JUnit Jupiter/AssertJ/Spring Test. `mockwebserver:4.12.0` stays strictly on the test classpath and must never enter production runtime.

If `gradlew`/`gradlew.bat` are absent, use a compatible pre-installed Gradle or generate the Wrapper first; do not treat “missing `gradlew` script” as a bug in the tests.

## 8. Boot application root

`src/main/java/com/example/faults/FaultLabApplication.java`:

```java
package com.example.faults;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FaultLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(FaultLabApplication.class, args);
    }
}
```

`@SpringBootApplication` scans `RemoteCatalogConfiguration` during normal application startup. Because the demo defines no endpoints of its own, running `bootRun` outside tests requires supplying `remote.catalog.base-url` and the two timeout properties. In local tests, the base URL comes from `server.url("/")` without production data or internet calls.

## 9. InventoryItem: enforcing semantic contracts with a record

`src/main/java/com/example/faults/InventoryItem.java`:

```java
package com.example.faults;

public record InventoryItem(
        String sku,
        int available,
        String warehouse
) {
    public InventoryItem {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }
        if (available < 0) {
            throw new IllegalArgumentException(
                    "available must be non-negative");
        }
        if (warehouse == null || warehouse.isBlank()) {
            throw new IllegalArgumentException(
                    "warehouse must not be blank");
        }
    }
}
```

JSON can be syntactically valid yet carry invalid data:

```json
{
  "sku": "SKU-1",
  "available": -4,
  "warehouse": "HCM"
}
```

The canonical constructor rejects negative quantities when Jackson instantiates the record. Tests verify this rejection instead of blindly trusting HTTP `200`.

**Limitation:** if primitive `int available` is omitted from JSON, Jackson under default settings may assign `0`, so the canonical constructor alone cannot distinguish “missing field” from “field equals 0”. If the contract requires presence, use nullable wrappers, Jackson required creator property validation, or JSON Schema validation matching your real config.

Likewise, whether unknown JSON fields are ignored or rejected depends on `ObjectMapper` settings; do not infer a blanket policy from the record example alone.

## 10. CatalogGateway: translating framework errors into domain errors

`src/main/java/com/example/faults/CatalogGateway.java`:

```java
package com.example.faults;

import java.net.URI;
import java.time.Duration;
import java.util.Objects;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

public final class CatalogGateway {

    private final RestClient client;

    public CatalogGateway(RestClient client) {
        this.client = Objects.requireNonNull(client);
    }

    public static CatalogGateway forEndpoint(
            RestClient.Builder builder,
            URI baseUrl,
            Duration connectTimeout,
            Duration readTimeout) {

        Objects.requireNonNull(builder);
        Objects.requireNonNull(baseUrl);
        Objects.requireNonNull(connectTimeout);
        Objects.requireNonNull(readTimeout);

        if (connectTimeout.isZero()
                || connectTimeout.isNegative()
                || readTimeout.isZero()
                || readTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "timeouts must be positive");
        }

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();

        factory.setConnectTimeout(connectTimeout);
        factory.setReadTimeout(readTimeout);

        RestClient restClient = builder
                .baseUrl(baseUrl.toString())
                .requestFactory(factory)
                .build();

        return new CatalogGateway(restClient);
    }

    public InventoryItem find(String sku) {
        if (sku == null
                || !sku.matches("[A-Z0-9-]{2,32}")) {
            throw new IllegalArgumentException("invalid sku");
        }

        try {
            InventoryItem item = client.get()
                    .uri("/v1/inventory/{sku}", sku)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(InventoryItem.class);

            if (item == null) {
                throw new BadRemotePayload(
                        "partner returned empty body");
            }

            if (!sku.equals(item.sku())) {
                throw new BadRemotePayload(
                        "partner returned mismatched sku");
            }

            return item;

        } catch (HttpClientErrorException.NotFound e) {
            throw new ItemMissing(sku, e);

        } catch (HttpClientErrorException.TooManyRequests e) {
            HttpHeaders headers = e.getResponseHeaders();
            String retryAfter = headers == null
                    ? null
                    : headers.getFirst(HttpHeaders.RETRY_AFTER);
            throw new RateLimited(retryAfter, e);

        } catch (HttpServerErrorException e) {
            throw new RemoteUnavailable(
                    "partner HTTP " + e.getStatusCode().value(),
                    e);

        } catch (RestClientResponseException e) {
            throw new RemoteRejected(
                    "partner HTTP " + e.getStatusCode().value(),
                    e);

        } catch (ResourceAccessException e) {
            throw new RemoteUnavailable(
                    "partner transport failure", e);

        } catch (RestClientException e) {
            throw new BadRemotePayload(
                    "partner response cannot be decoded", e);
        }
    }

    public abstract static class PartnerFailure
            extends RuntimeException {
        protected PartnerFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class ItemMissing extends PartnerFailure {
        private ItemMissing(String sku, Throwable cause) {
            super("item not found: " + sku, cause);
        }
    }

    public static final class RateLimited extends PartnerFailure {
        private final String retryAfter;

        private RateLimited(String retryAfter, Throwable cause) {
            super("partner rate limited request", cause);
            this.retryAfter = retryAfter;
        }

        public String retryAfter() {
            return retryAfter;
        }
    }

    public static final class RemoteRejected extends PartnerFailure {
        private RemoteRejected(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class RemoteUnavailable extends PartnerFailure {
        private RemoteUnavailable(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class BadRemotePayload extends PartnerFailure {
        private BadRemotePayload(String message) {
            super(message, null);
        }

        private BadRemotePayload(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

### Catch order must be exact

- `HttpClientErrorException.NotFound` → `ItemMissing`.
- `HttpClientErrorException.TooManyRequests` → `RateLimited`, retaining `Retry-After`.
- `HttpServerErrorException` for 5xx statuses → `RemoteUnavailable`.
- `RestClientResponseException` for remaining HTTP status errors → `RemoteRejected`.
- `ResourceAccessException` for I/O/transport → `RemoteUnavailable`.
- Other `RestClientException`, usually message conversion failures → `BadRemotePayload`.

Placing `RestClientResponseException` before its subclasses shadows the 404/429/5xx branches. Catching every `RuntimeException` and returning `InventoryItem(sku,0,"UNKNOWN")` conflates “out of stock” with “partner unable to respond”—a dangerous business bug.

### Domain exceptions thrown after decoding

`BadRemotePayload` thrown for null bodies or SKU mismatches occurs inside `try` yet is not a `RestClientException`, so it propagates to the caller as its exact domain type. Jackson errors during JSON parsing or record construction are typically wrapped by the HTTP message converter and mapped to `BadRemotePayload`.

### No retries inside this Gateway

`find` executes **a single HTTP call**. There is no `@Retryable`, circuit breaker, or resilience decorator. Those policies belong to a separate layer with dedicated tests. Enqueuing two responses on `MockWebServer` **does not make `RestClient` retry**.

### Never leak tokens or raw upstream responses

Domain error messages mention only category/status, never exposing Authorization headers, raw user data, or upstream response bodies. Causes can stay in controlled internal logs; outward APIs should map to stable error codes without stack traces.

## 11. Production-style configuration and properties

`src/main/java/com/example/faults/RemoteCatalogProperties.java`:

```java
package com.example.faults;

import java.net.URI;
import java.time.Duration;
import java.util.Objects;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "remote.catalog")
public record RemoteCatalogProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout
) {
    public RemoteCatalogProperties {
        Objects.requireNonNull(baseUrl, "baseUrl");
        Objects.requireNonNull(connectTimeout, "connectTimeout");
        Objects.requireNonNull(readTimeout, "readTimeout");
        if (!"http".equalsIgnoreCase(baseUrl.getScheme())
                && !"https".equalsIgnoreCase(baseUrl.getScheme())) {
            throw new IllegalArgumentException(
                    "base-url must be http or https");
        }
        if (connectTimeout.isZero() || connectTimeout.isNegative()
                || readTimeout.isZero() || readTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "timeouts must be positive");
        }
    }
}
```

`src/main/java/com/example/faults/RemoteCatalogConfiguration.java`:

```java
package com.example.faults;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RemoteCatalogProperties.class)
public class RemoteCatalogConfiguration {

    @Bean
    CatalogGateway catalogGateway(
            RestClient.Builder builder,
            RemoteCatalogProperties properties) {
        return CatalogGateway.forEndpoint(
                builder,
                properties.baseUrl(),
                properties.connectTimeout(),
                properties.readTimeout());
    }
}
```

An **illustrative configuration snippet for an application using this module** (no need to save inside the test project) could be:

```yaml
remote:
  catalog:
    base-url: https://catalog.example.invalid
    connect-timeout: 2s
    read-timeout: 900ms
```

The `example.invalid` domain is intentionally not a production endpoint. In real environments, URLs come from environment/secret configuration with proper TLS/credentials. In JUnit tests, the endpoint comes from `MockWebServer.url("/")`, so it **does not** depend on this YAML file.

### RestClient.Builder and the request factory

Spring Boot provides a managed `RestClient.Builder`. The configuration invokes the same `CatalogGateway.forEndpoint(...)` static factory used in tests. The example explicitly sets `SimpleClientHttpRequestFactory` to prevent classpath changes from silently swapping request factories. If production switches to Apache HttpClient, JDK HttpClient, or Reactor Netty, write transport tests against **the exact production factory** rather than assuming identical timeout/disconnect semantics.

### Why not use @RestClientTest for timeout tests?

`@RestClientTest` + `MockRestServiceServer` normally binds a mock `ClientHttpRequestFactory` onto the builder. Since our production factory explicitly instantiates `SimpleClientHttpRequestFactory`, an improperly configured slice test can **bypass the mock binding** and actually try calling the external URL. The lesson uses `MockWebServer` on localhost to exercise the real HTTP request factory. When writing standalone slice tests, import config and bind mocks carefully per your framework version.

## 12. CatalogGatewayNetworkTest.java: the fault-injection suite

`src/test/java/com/example/faults/CatalogGatewayNetworkTest.java`:

```java
package com.example.faults;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import okhttp3.mockwebserver.SocketPolicy;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CatalogGatewayNetworkTest {

    private MockWebServer server;
    private CatalogGateway gateway;

    @BeforeEach
    void startServer() throws IOException {
        server = new MockWebServer();
        server.start();
        gateway = CatalogGateway.forEndpoint(
                RestClient.builder(),
                server.url("/").uri(),
                Duration.ofSeconds(2),
                Duration.ofMillis(900));
    }

    @AfterEach
    void shutdownServer() throws IOException {
        if (server != null) {
            server.shutdown();
        }
    }

    private MockResponse json(int status, String body) {
        return new MockResponse()
                .setResponseCode(status)
                .setHeader("Content-Type", "application/json")
                .setBody(body);
    }

    private String item(String sku, int available) {
        return """
                {
                  "sku": "%s",
                  "available": %d,
                  "warehouse": "HCM"
                }
                """.formatted(sku, available);
    }

    @Test
    void validResponseReturnsItemAndUsesExpectedRequest()
            throws Exception {
        server.enqueue(json(200, item("SKU-1", 12)));

        InventoryItem actual = gateway.find("SKU-1");

        assertEquals(
                new InventoryItem("SKU-1", 12, "HCM"), actual);

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/v1/inventory/SKU-1", request.getPath());
        assertEquals("application/json",
                request.getHeader("Accept"));
        assertEquals(1, server.getRequestCount());
    }

    @Test
    void notFoundHasItsOwnDomainError() {
        server.enqueue(json(404,
                "{\"error\":\"missing\"}"));

        CatalogGateway.ItemMissing error = assertThrows(
                CatalogGateway.ItemMissing.class,
                () -> gateway.find("SKU-2"));

        assertTrue(error.getMessage().contains("SKU-2"));
        assertEquals(1, server.getRequestCount());
    }

    @Test
    void rateLimitRetainsRetryAfterHint() {
        server.enqueue(
                json(429, "{\"error\":\"too_many\"}")
                        .setHeader("Retry-After", "120"));

        CatalogGateway.RateLimited error = assertThrows(
                CatalogGateway.RateLimited.class,
                () -> gateway.find("SKU-3"));

        assertEquals("120", error.retryAfter());
        assertEquals(1, server.getRequestCount());
    }

    @Test
    void serviceUnavailableIsNotReportedAsMissing() {
        server.enqueue(json(503,
                "{\"error\":\"unavailable\"}"));

        CatalogGateway.RemoteUnavailable error = assertThrows(
                CatalogGateway.RemoteUnavailable.class,
                () -> gateway.find("SKU-4"));

        assertTrue(error.getMessage().contains("503"));
    }

    @Test
    void badGateway502MapsToUnavailable() {
        server.enqueue(json(502, "{\"error\":\"bad_gateway\"}"));

        assertThrows(
                CatalogGateway.RemoteUnavailable.class,
                () -> gateway.find("SKU-5"));
    }

    @Test
    void client400IsNotTransientOutage() {
        server.enqueue(json(400,
                "{\"error\":\"invalid_input\"}"));

        CatalogGateway.RemoteRejected error = assertThrows(
                CatalogGateway.RemoteRejected.class,
                () -> gateway.find("SKU-6"));

        assertTrue(error.getMessage().contains("400"));
    }

    @Test
    void malformedJsonIsBadRemotePayload() {
        server.enqueue(json(200, "{\"sku\":"));

        CatalogGateway.BadRemotePayload error = assertThrows(
                CatalogGateway.BadRemotePayload.class,
                () -> gateway.find("SKU-7"));

        assertNotNull(error.getCause());
    }

    @Test
    void negativeAvailableQuantityIsRejected() {
        server.enqueue(json(200, item("SKU-8", -4)));

        assertThrows(
                CatalogGateway.BadRemotePayload.class,
                () -> gateway.find("SKU-8"));
    }

    @Test
    void wrongSkuInValidJsonIsRejected() {
        server.enqueue(json(200, item("DIFFERENT", 10)));

        CatalogGateway.BadRemotePayload error = assertThrows(
                CatalogGateway.BadRemotePayload.class,
                () -> gateway.find("SKU-9"));

        assertTrue(error.getMessage().contains("mismatched"));
    }

    @Test
    void empty204BodyIsRejected() {
        server.enqueue(new MockResponse().setResponseCode(204));

        assertThrows(
                CatalogGateway.BadRemotePayload.class,
                () -> gateway.find("SKU-10"));
    }

    @Test
    void wrongContentTypeCannotSilentlyMapToDto() {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "text/plain")
                .setBody(item("SKU-11", 7)));

        assertThrows(
                CatalogGateway.BadRemotePayload.class,
                () -> gateway.find("SKU-11"));
    }

    @Test
    void smallHeaderDelayFitsReadBudget() {
        server.enqueue(
                json(200, item("SKU-12", 5))
                        .setHeadersDelay(
                                100, TimeUnit.MILLISECONDS));

        assertEquals(
                new InventoryItem("SKU-12", 5, "HCM"),
                gateway.find("SKU-12"));
    }

    @Test
    void excessiveHeaderDelayBecomesUnavailable() {
        server.enqueue(
                json(200, item("SKU-13", 2))
                        .setHeadersDelay(3, TimeUnit.SECONDS));

        CatalogGateway.RemoteUnavailable error = assertThrows(
                CatalogGateway.RemoteUnavailable.class,
                () -> gateway.find("SKU-13"));

        assertNotNull(error.getCause());
        assertEquals(1, server.getRequestCount());
    }

    @Test
    void closedPortBecomesConnectionFailure()
            throws Exception {
        server.shutdown();
        server = null;

        CatalogGateway.RemoteUnavailable error = assertThrows(
                CatalogGateway.RemoteUnavailable.class,
                () -> gateway.find("SKU-14"));

        assertNotNull(error.getCause());
    }

    @Test
    void disconnectDuringBodyNeverProducesValidItem() {
        server.enqueue(
                json(200, item("SKU-15", 7))
                        .setSocketPolicy(
                            SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY));

        // I/O error or truncated JSON error depending on HTTP client.
        CatalogGateway.PartnerFailure error = assertThrows(
                CatalogGateway.PartnerFailure.class,
                () -> gateway.find("SKU-15"));

        assertTrue(
                error instanceof CatalogGateway.RemoteUnavailable
                || error instanceof CatalogGateway.BadRemotePayload);
    }

    @Test
    void invalidInputFailsBeforeAnyHttpRequest() {
        assertThrows(
                IllegalArgumentException.class,
                () -> gateway.find("../etc/passwd"));

        assertEquals(0, server.getRequestCount());
    }

    @Test
    void gatewayDoesNotRetry503ByItself() {
        server.enqueue(json(503,
                "{\"error\":\"temporary\"}"));
        server.enqueue(json(200, item("SKU-16", 100)));

        assertThrows(
                CatalogGateway.RemoteUnavailable.class,
                () -> gateway.find("SKU-16"));

        assertEquals(1, server.getRequestCount());
    }
}
```

**The test class contains 17 `@Test` methods**, excluding `@BeforeEach` and `@AfterEach`. SKU names and response fixtures are synthetic data, not real accounts or product codes.

### Per-test server instead of a shared queue

Each test starts its own `MockWebServer` in `@BeforeEach` on an OS-assigned port via `server.start()`. `@AfterEach` shuts the server down so sockets/threads do not leak. Sharing one static server across tests lets queued responses and delayed requests bleed across tests and cause flakiness; avoid that unless lifecycle and isolation are strictly managed.

In the closed-port test, we shut down the server and set `server=null` so cleanup does not call shutdown twice. `CatalogGateway` still holds the loopback URI; the subsequent call gets a transport failure without touching DNS or the internet.

### Bounded request capture

`takeRequest(2, TimeUnit.SECONDS)` bounds how long the test waits for the mock to record a request. `getRequestCount()` enforces “no unexpected retries” and “validate before I/O”. In suites with real client retries, request counts may exceed one; know whether that comes from automatic transport retries or a resilience decorator.

### Delays and socket policies

- `setHeadersDelay(100, MILLISECONDS)`: fits inside the 900 ms budget, expects success.
- `setHeadersDelay(3, SECONDS)`: exceeds read timeout, expects `RemoteUnavailable`.
- `DISCONNECT_DURING_RESPONSE_BODY`: drops the connection mid-body. URLConnection may throw an I/O error or Jackson may hit truncated JSON; the test asserts failing closed rather than pinning a fragile low-level exception class.
- `server.shutdown()` before the call: simulates a closed local port (connection refused) deterministically.

**Never call `Thread.sleep` in the test body.** `MockWebServer` controls server-side delays; the client timeout controls the failure boundary.

## 13. Explaining key branches individually

### 13.1. 404, 429, and 503 are three different things

HTTP 404 means the resource does not exist per contract; 429 means rate-limited; 503 means the service is unavailable. Mapping all three to `RemoteUnavailable` and retrying them identically can trigger load storms, degrade UX, and hide business conditions.

`RateLimited` retains `Retry-After` **as a String**. HTTP `Retry-After` can be a delay in seconds or an HTTP date; never parse it blindly with `Integer.parseInt`, never trust an absurd hint, and never sleep indefinitely. Production retry policies must clamp to the SLO/deadline and add jitter.

### 13.2. HTTP 400 has a response, whereas socket errors have no status

`RestClient.retrieve()` converts 4xx/5xx statuses into HTTP exceptions by default. `HttpClientErrorException` carries status, headers, and body. `ResourceAccessException` wraps I/O failures such as connect/read timeouts. Never inspect `getStatusCode()` on a `ResourceAccessException` because no reliable HTTP status arrived from the server.

### 13.3. 200 does not guarantee a valid DTO

Three layers apply:

1. **Content-type/codec**: can the decoder read the body?
2. **Structure/semantics**: does the DTO have required fields and valid quantities?
3. **Consistency**: does the response match the requested `sku`?

`BadRemotePayload` protects against null bodies, broken JSON, and semantic mismatches. Larger systems may split out `UpstreamSchemaViolation` and `UpstreamDataIntegrityViolation`, but never return a fabricated object when data is unknown.

### 13.4. An error body is not a success body

When the server returns 503 with a JSON error envelope, `retrieve()` throws the status exception before attempting to decode into `InventoryItem`. Tests should not assert JSON parse failures on error bodies; validating upstream error schemas is a separate contract if the app consumes provider error codes.

### 13.5. Slow responses and dropped connections must stay distinguishable

Delayed headers trigger read timeouts; closed ports trigger connection refusal; mid-response socket drops cause EOF/reset or JSON parse errors. All three may map to `RemoteUnavailable` or `BadRemotePayload` depending on policy, while metrics/logs should preserve the underlying cause category. Meanwhile, HTTP 504 from a gateway is an **HTTP status response**, not a low-level client timeout.

### 13.6. Never verify signatures/TLS/proxies using localhost HTTP

`MockWebServer` over `http://localhost` does not test TLS truststores, proxy credentials, DNS caching, WAFs, or real providers. When TLS testing is needed, use a local HTTPS test server with a test certificate authority; never disable certificate validation in production just to turn a suite green.

## 14. MockRestServiceServer: fast, yet fundamentally different

An illustrative REST-client slice:

```java
@RestClientTest(SomeInventoryClient.class)
class InventoryClientSliceTest {
    @Autowired SomeInventoryClient client;
    @Autowired MockRestServiceServer mockServer;

    @Test
    void mapsHttp503() {
        mockServer.expect(requestTo(
                "https://partner.example.invalid/v1/inventory/SKU-1"))
                .andRespond(withServerError());

        assertThrows(
                SomeUnavailableException.class,
                () -> client.find("SKU-1"));
        mockServer.verify();
    }
}
```

**This is an architectural snippet, not part of the runnable project**: `SomeInventoryClient` and `SomeUnavailableException` are placeholders for another app. To run it for real, define the component, import production client configuration, wire bean dependencies, and add static imports. With `RestClient.Builder`, matchers expect **full URLs**; `RestTemplateBuilder.rootUri` behaves differently in expectations.

`MockRestServiceServer` excels at asserting URL, method, headers, body, and status, yet opens no sockets and cannot verify an HTTP client's real timeout behavior. When tests require disconnects, EOFs, or proxies, use MockWebServer, WireMock, or a network fault tool.

## 15. Remember server failures can produce nondeterministic low-level exceptions

With `DISCONNECT_DURING_RESPONSE_BODY`:

- Some HTTP clients check `Content-Length`/stream EOF and throw I/O exceptions.
- Some clients hand the truncated body to the JSON parser, producing a decode error.
- Some clients automatically retry safe GETs before surfacing an error, depending on internal retry settings.

Therefore, **domain-level** unit/integration tests should enforce “never return a successful item on truncated responses”. If a system must strictly separate `RemoteUnavailable` from `BadRemotePayload`, pin the HTTP client implementation/version/config and add a dedicated **transport adapter test** verifying classification, rather than assuming identical low-level exceptions across all HTTP clients.

Never automatically retry a payment/reservation POST after premature EOF: the server may have committed the side effect before the response dropped. Use idempotency keys, status inquiries/reconciliation, or an outbox.

## 16. Timeout budgets and retry policies

An operation with a 2-second deadline cannot allow 3 retries × 2-second read timeouts + backoff and still finish within 2 seconds.

| Policy | Considerations |
| --- | --- |
| Idempotent GET hitting 503 | Small retry count with backoff/jitter within remaining deadline |
| GET hitting 429 | Honor `Retry-After` if budget allows |
| GET hitting 404 | Usually do not retry |
| GET hitting invalid JSON schema | Usually do not retry; alert on contract |
| POST without idempotency key | Never blindly retry under network uncertainty |
| Circuit breaker OPEN | Fail fast, send zero requests |
| Cached inventory fallback | Enforce clear TTL, tenant scope, and freshness |
| Long-running batch job | Retry/reconcile by job/item identity |

A clean design can use Resilience4j `Retry`, `CircuitBreaker`, `TimeLimiter`, or `Bulkhead`; these libraries **are not included in the sample project**. If added, test separately:
- attempt counts;
- total duration/budget;
- exception predicates;
- circuit state transitions;
- bulkhead saturation;
- idempotency and absence of duplicate side effects.

**Never call `MockWebServer.enqueue(503)` + `enqueue(200)` “a retry test”** when the code does not retry. `gatewayDoesNotRetry503ByItself` verifies `requestCount == 1` even with a second response queued.

## 17. JSON edge cases to add

| Payload | Question |
| --- | --- |
| Malformed JSON | Does the converter reject it? |
| JSON object missing `sku` | Does the constructor/validation block it? |
| `available=-1` | Does the domain invariant reject it? |
| `available=null` | Does Jackson's primitive config silently default to 0? |
| `available="not-a-number"` | Does the decoder reject the type mismatch? |
| `warehouse=""` | Does the domain invariant block it? |
| SKU different from request | Does the cross-request check reject it? |
| Extra field | Are backward-compatible extensions allowed? |
| Response is array instead of object | Does the converter reject the wrong shape? |
| Huge/deeply nested JSON | Are size/nesting limits enforced against memory pressure? |
| Stale timestamp | Does cache/freshness policy validate it? |
| Currency or price precision | Are `BigDecimal`/minor units handled properly? |

**Do not rely on serializing and deserializing your own DTO to prove a provider contract**: both sides of the test can share the same mistaken field name. Use literal JSON fixtures sourced from versioned schemas/provider contracts, including negative cases.

## 18. Fault injection for non-HTTP dependencies

### Database

If the dependency is PostgreSQL, simulate:
- constraint violations with real schemas/fixtures;
- deadlocks using barrier-synchronized concurrency;
- DB disconnects via dedicated Testcontainers/Toxiproxy;
- query timeouts via appropriate driver/server timeouts;
- transaction rollbacks via business DB assertions.

Do not use `MockWebServer` to test JDBC. `DataAccessException` and driver exception hierarchies differ from `RestClient` exceptions. Never shut down a shared teammate or CI database.

### Kafka/RabbitMQ

A Kafka producer ACK does not prove the consumer processed the event; RabbitMQ publisher confirms differ from consumer ACKs. Simulate broker disconnects, nacks, deserialization failures, retries/rebalances, or DLQs using dedicated test brokers/containers. With non-durable publishing, messages can be lost; protect business contracts with idempotency and durable outboxes.

### Redis/cache

Distinguish a **cache miss** from Redis unavailability. Test fail-open vs. fail-closed per business rules. Toxiproxy can inject latency/disconnects into connections to a dedicated Redis container. Never return a fake default cache value pretending it is a valid miss when data accuracy matters.

### Reactive/WebClient

`WebClient` throws `WebClientResponseException` for HTTP status errors and `WebClientRequestException` for transport errors—do not mechanically reuse `RestClientException` mappings. For Reactor `timeout`/retry/backoff, `StepVerifier.withVirtualTime` tests operator timing; virtual time **does not replace** real TCP socket timeouts in Netty. MockWebServer/WireMock remain valuable for network tests.

## 19. Observability for downstream failures

A production Gateway should emit metrics, logs, and traces with **bounded labels**:

- logical dependency name: `catalog`;
- operation: `getInventory`;
- outcome: `success`, `not_found`, `throttled`, `http_5xx`, `timeout`, `connection_error`, `bad_payload`;
- HTTP status when a response exists;
- attempt count/retry reason;
- duration and circuit breaker state;
- safe trace/correlation ID.

**Never attach SKUs, order IDs, full URLs, or query tokens as metric tags** because of high cardinality and PII leak risk. If `ObservationRegistry` or `MeterRegistry` is wired, tests can inject a test registry and assert metrics after controlled faults. The current codebase does not instrument metrics, so never claim these tests verify telemetry.

## 20. Responses returned to callers do not always mirror downstream statuses

| Gateway domain failure | Possible inbound API policy | Caution |
| --- | --- | --- |
| `ItemMissing` | 404 | Only when domain-appropriate |
| `RateLimited` | 429/503 | Upstream quota may differ from user quota |
| `RemoteUnavailable` | 503 | Never leak internals |
| `RemoteRejected` | 502 or config error | Upstream 401 does not mean the caller is unauthenticated |
| `BadRemotePayload` | 502 | Never return `stock=0` |
| Invalid input | 400 | Validate before HTTP |

A `@RestControllerAdvice` can map domain exceptions to `ProblemDetail`/structured error codes with correlation IDs. Test controller mappings separately with `MockMvc`. Never echo raw upstream bodies, headers, or tokens back to end users.

## 21. Never conflate business errors with network errors

If a partner returns 404 for a nonexistent SKU, that is not necessarily service degradation. If a partner returns HTTP 200 with a negative number, that is a **contract violation** even though the network is healthy. If a partner returns 503, your API may fail fast or serve explicitly labeled stale cache depending on UX; never interpret 503 as “out of stock”.

In payment/order workflows, a network timeout represents an **unknown outcome**: the server may have committed the transaction before the response dropped. Policies must use idempotency keys, payment status inquiries, or reconciliation—never blindly retry and cause double charges.

## 22. How to write non-flaky timeout tests

1. Run mock servers on loopback with OS-assigned ports, never internet hosts.
2. Set mock delays **well beyond** client timeouts (here 3s vs. 900ms).
3. Never use `Thread.sleep` in the test thread.
4. Never assert exact OS/JDK elapsed milliseconds.
5. Shut down servers in `@AfterEach` even when assertions fail.
6. If server startup fails due to CI policy, separate environment failures from domain failures.
7. Never leave `NO_RESPONSE` infinite when read timeout is unset.
8. When tests run in parallel, give each test its own response queue/server.
9. Avoid shared mutable static request counters.
10. Never alter system-wide proxy/firewall/DNS settings for a small test.
11. To test true connect timeouts, use a controlled network blackhole/SYN drop; closed ports only verify **connection refused**.
12. For body/chunk timeouts, use `setBodyDelay`/`throttleBody` against a real request factory.
13. Always bound total request deadlines and retry budgets in production code.

### SocketPolicy failures are not all alike

MockWebServer provides `DISCONNECT_AT_START`, `DISCONNECT_DURING_RESPONSE_BODY`, and `NO_RESPONSE`. Some HTTP clients auto-retry safe methods or wrap EOFs into decoder errors. Decide whether a test protects **network classification** or **fail-closed outcomes**, avoiding coupling all transport implementations to a single `IOException` subclass.

## 23. Provider contract verification must exist outside consumer mocks

MockWebServer serves whatever bytes the test author writes; if the author misunderstands the provider API, tests still pass. For real contracts:

- Use OpenAPI, JSON Schema, AsyncAPI, or Pact where appropriate.
- Verify provider responses, headers, and error semantics in provider CI or a sandbox.
- Pin API versions and test backward compatibility.
- Keep production secrets and PII out of fixtures.
- Test unknown fields and new enum values under an explicit policy.
- Include incident tests for key rotation and auth failures when using OAuth/TLS.
- Verify server-side schemas and consumer mappings at distinct layers.

Fault-injection tests answer: “When a dependency misbehaves or fails to respond, does **our application** react safely and per policy?” They do not prove the partner actually emits the schema we mocked.

## 24. Debugging failures in order

1. Confirm the test actually targets `server.url("/")` from `MockWebServer`.
2. Verify `RestClient.Builder` and `SimpleClientHttpRequestFactory` are configured/initialized properly.
3. Ensure `server.enqueue(...)` happens before `gateway.find(...)`.
4. Inspect actual request path/method/`Accept` via `RecordedRequest`.
5. Distinguish HTTP status errors from `ResourceAccessException`.
6. Verify the catch order for 404/429/5xx.
7. On JSON errors, inspect media types, converters, and record constructors.
8. On negative quantities or mismatched IDs, ensure domain invariants are not bypassed.
9. On delayed responses, confirm whether the delay is on headers or body.
10. On closed ports, confirm `server.shutdown()` completed before the gateway call.
11. On mid-body disconnects, inspect the cause chain and fail-closed behavior.
12. On unexpected retries, check underlying HTTP client internal retries and resilience decorators.
13. If tests fail only in CI, check resource/socket limits and test parallelism.
14. If production behaves differently from local tests, compare HTTP clients, proxies, TLS, and contract versions.
15. Read the real JUnit report rather than tweaking expected assertions to “go green” before understanding the failure.

## 25. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Timeout test returns 200 | Delay too small or wrong phase | Make `setHeadersDelay` exceed read timeout with wide margin |
| Test hangs forever | `NO_RESPONSE` without timeout | Bounded deadline and cleanup |
| `MockRestServiceServer` fails to reproduce TCP reset | No real socket | Use MockWebServer/WireMock |
| Mockito test passes yet production has no timeouts | Mocked wrong layer | Test real request factory |
| Closed port treated as 503 | No HTTP response exists | Map `ResourceAccessException` separately |
| 404 retried repeatedly | Overly broad retry predicate | Classify statuses |
| 429 ignores `Retry-After` | Hint not retained/parsed | Test hint and clamp budget |
| Stock “0” when partner is down | Dangerous fallback | Unknown/unavailable domain state |
| Invalid JSON passes tests | Checked only HTTP status | Decode and validate domain invariants |
| Negative DTO quantity accepted | Missing invariant | Record constructor/validation |
| Mismatched SKU in payload | No consistency check | Assert requested SKU |
| Disconnect throws two error types across HTTP clients | Different I/O vs. parse boundary | Fail-closed + dedicated transport test |
| Tests fail to start on CI | Socket blocked or deps offline | Diagnose environment |
| Tests pass individually yet fail as a suite | Shared mock server/response queue | Per-test setup/teardown |
| POST retry creates duplicates | No idempotency | Keys, dedup, status reconciliation |
| Logs leak `Authorization` header | Raw request logging | Redact/truncate structured logs |
| Circuit breaker flaky | Wall-clock sleeps | Controllable clock/state tests |
| Asserting exact OS exception message | OS/JDK differences | Assert domain type/cause class |

## 26. Project test matrix

| Test method | What it protects |
| --- | --- |
| `validResponseReturnsItemAndUsesExpectedRequest` | 200, DTO, GET path, Accept |
| `notFoundHasItsOwnDomainError` | 404 → `ItemMissing` |
| `rateLimitRetainsRetryAfterHint` | 429, `Retry-After` |
| `serviceUnavailableIsNotReportedAsMissing` | 503 → `Unavailable` |
| `badGateway502MapsToUnavailable` | 502 → `Unavailable` |
| `client400IsNotTransientOutage` | 400 → `RemoteRejected` |
| `malformedJsonIsBadRemotePayload` | Malformed JSON syntax |
| `negativeAvailableQuantityIsRejected` | Quantity semantics |
| `wrongSkuInValidJsonIsRejected` | Cross-response ID |
| `empty204BodyIsRejected` | Missing body |
| `wrongContentTypeCannotSilentlyMapToDto` | MIME mismatch |
| `smallHeaderDelayFitsReadBudget` | Moderate delay |
| `excessiveHeaderDelayBecomesUnavailable` | Read timeout |
| `closedPortBecomesConnectionFailure` | Connection refused |
| `disconnectDuringBodyNeverProducesValidItem` | Premature EOF fails closed |
| `invalidInputFailsBeforeAnyHttpRequest` | Validate before HTTP |
| `gatewayDoesNotRetry503ByItself` | No implicit application retry |

**Total: 17 `@Test` methods** counted from source. Expected 200/error outcomes in the table are expected assertions, **not executed passing test runs**.

## 27. Running the project

If the project includes the Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.faults.CatalogGatewayNetworkTest'
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If using a pre-installed compatible Gradle:

```bash
gradle test
```

JUnit/Gradle reports appear under:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

These tests do not call `System.out.println` and emit no fixed business stdout. Never fabricate “17 PASSED” output without running them. Check actual passed/failed/skipped counts in the reports during practice.

## 28. Practice exercises

1. Run a passing test and inspect request URI/headers with `RecordedRequest`.
2. Switch a 200 response to 404 and confirm `ItemMissing` is never retried.
3. Return 429 with an HTTP-date `Retry-After`; implement a safe clamped parser.
4. Simulate 503 then 200; add a 2-attempt retry policy for GET and assert `requestCount`.
5. Add an idempotency key to a mock POST and test uncertainty after disconnect.
6. Vary read timeout and mock header delays without asserting exact elapsed ms.
7. Use `setBodyDelay` instead of `setHeadersDelay` to test body reads.
8. Use `NO_RESPONSE` with a bounded timeout to exercise read deadlines.
9. Try `DISCONNECT_DURING_RESPONSE_BODY` with Apache HttpClient and compare causes.
10. Supply JSON missing `sku` and verify domain validation.
11. Supply JSON missing primitive `available` and strengthen DTO required-field policy.
12. Add an extra JSON field and decide between forward-compatible or strict handling.
13. Use WireMock scenarios to simulate 503 outages recovering to 200.
14. Write a standalone `@RestClientTest` asserting only URL/method/status and compare against having no TCP.
15. Add `@RestControllerAdvice` returning `ProblemDetail` for gateway failures.
16. Use `SimpleMeterRegistry` to record bounded downstream outcome labels.
17. Add a cached fallback with a freshness TTL; test stale data rejection.
18. Test database outages with dedicated Testcontainers/Toxiproxy without stopping shared DBs.
19. Build a `WebClient` version using `WebClientRequestException` and `StepVerifier`.
20. Run the full suite, inspect Gradle reports, and triage any flakiness by root cause.

## 29. Pre-merge QA checklist

- [ ] Selected the right mock boundary and documented what the test cannot prove?
- [ ] Included success + request method/path/header assertions?
- [ ] Included HTTP 404, 429, 400, and 5xx tests?
- [ ] Blocked empty bodies, malformed JSON, semantically invalid data, and ID mismatches?
- [ ] Tested `Content-Type` mismatches?
- [ ] Tested timeouts via delayed headers/bodies on a real local HTTP server?
- [ ] Tested closed-server connection failures and mid-response drops?
- [ ] Bounded client timeouts with zero infinite sleeps?
- [ ] Distinguished connect timeouts, read timeouts, and total deadlines?
- [ ] Mapped domain error types without leaking raw responses or secrets?
- [ ] Verified no out-of-policy retries occur?
- [ ] Defined an idempotency strategy for non-idempotent operations?
- [ ] Verified fallbacks never turn unknown data into valid values?
- [ ] Isolated mock servers/response queues per test?
- [ ] Confirmed tests never hit production endpoints or the internet?
- [ ] Avoided asserting exact low-level `IOException` text or wall-clock latency?
- [ ] Added state/attempt/deadline tests if using circuit breakers/retries?
- [ ] Tested against a real metrics registry if metrics are required?
- [ ] Maintained separate provider contract verification where needed?
- [ ] Ensured CI tests never share a DB/broker to inject outages?
- [ ] Read actual test reports before declaring PASS?

## 30. Official documentation

- [Spring Framework — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): `MockRestServiceServer` and mock web servers over real networks.
- [Spring Framework 6.1 — SimpleClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html): connect/read timeouts with `Duration`.
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): requests, responses, and status exception handling.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@RestClientTest`, `RestClient.Builder`, and `MockRestServiceServer`.
- [OkHttp MockWebServer](https://square.github.io/okhttp/4.x/mockwebserver/): request capture, `MockResponse`, delays, and `SocketPolicy`.
- [MockWebServer 4.12.0 artifact](https://central.sonatype.com/artifact/com.squareup.okhttp3/mockwebserver/4.12.0): dependency coordinates.
- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110): HTTP statuses, idempotency, `Retry-After`.
- [HTTP 429 — RFC 6585](https://www.rfc-editor.org/rfc/rfc6585): Too Many Requests.
- [JSON — RFC 8259](https://www.rfc-editor.org/rfc/rfc8259): JSON syntax.
- [Resilience4j](https://resilience4j.readme.io/docs): retry, circuit breaker, bulkhead.
- [Testcontainers Toxiproxy](https://java.testcontainers.org/modules/toxiproxy/): network faults inside dedicated containers.
- [JUnit Jupiter](https://junit.org/junit5/docs/current/user-guide/): lifecycle and assertions.

## 31. Conclusion

**Fault-injection testing must verify failure contracts, not merely throw arbitrary exceptions.** With Java 17+/Spring Boot 3.3.5, `MockRestServiceServer` fits fast REST-client slices checking HTTP contracts, while `MockWebServer` fits observing real localhost network I/O: slow servers, connection refused, truncated responses, or empty bodies.

The `CatalogGateway` pattern cleanly separates 404, 429, 400, 5xx, transport failures, and invalid JSON into meaningful domain errors. The test suite verifies status mapping, timeouts, fail-closed socket drops, semantic validation, and absence of unintended retries. Before going to production, add bounded retry budgets, idempotency, controlled circuit breakers/fallbacks, observability, and provider contract verification tailored to real requirements. **Never infer a passing Gradle run from the test method count in documentation; run the suite and inspect the real reports.**
