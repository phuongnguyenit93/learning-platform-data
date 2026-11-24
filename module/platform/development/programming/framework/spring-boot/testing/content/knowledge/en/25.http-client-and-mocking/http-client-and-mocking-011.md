# Limits of Java-Layer Mocks Compared to HTTP Stub Servers

## 1. The problem: mocks return the right result while the real HTTP client still breaks

Imagine a Spring Boot application calling an external catalog service to check stock before completing a sale. A Mockito unit test can be completely green:

```java
when(catalogGateway.fetch("SKU-01"))
        .thenReturn(new ProductView(
                "SKU-01", "Camera", 5));

assertTrue(inventoryService.isInStock("SKU-01"));
```

That test proves `InventoryService` uses the return value from `CatalogGateway` as expected. Yet it **sends zero HTTP requests**: it verifies no URL, query parameter, encoding, HTTP method, `Accept`/`Authorization` header, JSON decoding, HTTP 404/500 status, timeout, TLS, or request/response framing.

In production, a client can fail in ways a Mockito mock on a Java interface never observes:

- Calling `/v1/product` instead of `/v1/products`.
- Sending `GET` when the API contract requires `POST`.
- Dropping the `sku` query parameter, or mis-encoding strings containing spaces or special characters.
- Forgetting tokens/headers, sending the wrong `Content-Type`, or misunderstanding `Accept`.
- Misnaming/mistyping JSON fields, silently defaulting primitives to 0.
- Receiving HTTP 404 and returning an empty object instead of a domain exception.
- Retrying a non-idempotent request and creating duplicate records.
- Setting a timeout only in unit test assumptions without ever connecting over a socket.
- Mishandling 429/503, ignoring `Retry-After`, or retrying infinitely.

To verify **the HTTP client layer that actually builds requests**, use an **HTTP stub server** like WireMock or MockWebServer: it opens a local HTTP port, accepts requests through the same HTTP client stack the app runs, matches method/path/query/headers/body, and returns a test-defined response.

**However, an HTTP stub server is still not the real service.** WireMock returns JSON and statuses authored by the test; it does not prove the external provider actually implements that schema, auth/TLS, pagination, or business behavior. This lesson separates **three tiers of evidence**: Java mocks → HTTP stub servers → integration/contract tests against real services.

## 2. Learning objectives

After this lesson, you will be able to:

1. Distinguish Mockito mocks on Java interfaces, `MockRestServiceServer` at the request-factory/client layer, and WireMock/MockWebServer with **real HTTP sockets**.
2. Pinpoint exactly what `when(...).thenReturn(...)` can and cannot prove.
3. Design a clean `InventoryService → CatalogGateway → HttpCatalogGateway → HTTP` boundary.
4. Write JUnit 5/Mockito unit tests for business rules without a Spring context, server, or network.
5. Write JUnit 5/WireMock tests with real `RestClient`, random ports, stub mappings, and request verification.
6. Verify method, URL path, query parameters, percent-encoding, `Accept`, custom headers, and JSON response mapping.
7. Distinguish HTTP 404, 429, 500, 204, invalid JSON, and I/O timeouts.
8. Understand that `RestClient.retrieve()` throws exceptions for 4xx/5xx by default, yet provides no business-specific retry/fallback automatically.
9. Use `@SpringBootTest`/`@DynamicPropertySource` to inject a mock server base URL into Spring Boot beans.
10. Know how `@RestClientTest` + `MockRestServiceServer` differs from WireMock in network scope.
11. Explain contract tests, provider verification, consumer-driven contracts, and the danger of **stubs matching wrong assumptions**.
12. Build isolated tests: reset stubs/request journals, random ports, bounded timeouts, synthetic data, and zero accidental internet requests.
13. Choose proper ways to simulate HTTP/transport failures and avoid tests flaking due to arbitrary sleeps/retries.
14. Design a test pyramid giving fast feedback while protecting high-risk integrations.

## 3. Comparing mocking layers

| Test approach | What is replaced? | TCP/HTTP socket? | Real request serialization + response deserialization? | Level of evidence |
| --- | --- | --- | --- | --- |
| Mockito mock of `CatalogGateway` | App-defined Java interface | No | No | Business logic given fake returns/exceptions |
| Mockito mock of `RestClient` or builder | HTTP client's Java API | No | Usually no | Client control flow, yet very easy to mis-mock call chains |
| `@RestClientTest` + `MockRestServiceServer` | Request factory/transport inside Spring client | Opens no server socket | Can verify URI/method/headers/body and message converters | Spring HTTP request construction/decoding with fake responses, no network I/O |
| In-JVM WireMock/MockWebServer | Remote HTTP server | **Yes**, loopback TCP | **Yes**, via real HTTP client stack | Request/response protocol, client codecs, headers/status/transport locally |
| WireMock in a separate process/container | Remote HTTP server | **Yes**, over network/container routing | Yes | Closer to deployment host/port topology; still stub behavior |
| Test against real provider sandbox | External service API | Yes | Yes | Real provider contract inside a managed sandbox |
| Test against prod-like service and test data | Real bounded infrastructure | Yes | Yes | Behavior of a specific deployment; harder to isolate |

**Never use "HTTP mock" as a blanket label for every tool.** `MockRestServiceServer` has "server" in its name, yet intercepts requests inside the HTTP client abstraction; it **never** opens a TCP listener like WireMock. Both are valuable, but they catch different classes of bugs.

### 3.1. Always answer "which unit is real?"

In a Mockito test:

```text
Real InventoryService
        |
        v
CatalogGateway (Mockito mock)
        X
HttpCatalogGateway / RestClient / network / JSON
```

In a WireMock test:

```text
Real HttpCatalogGateway
        |
        v
Real RestClient + HTTP request factory
        |
        v
localhost:<dynamic-port> over HTTP socket
        |
        v
WireMock fake HTTP server
        |
        v
Test-configured response
```

In a provider sandbox test:

```text
Real HttpCatalogGateway
        |
        v
HTTP + DNS + TLS / configured network
        |
        v
Real provider sandbox
        |
        v
Provider's behavior in sandbox
```

Key point: every test has a **system boundary under verification**. Never claim a MockMvc/WireMock test proved financial transactions or live external services work when only a stub was present.

## 4. Java-layer mocks: strong benefits with a hard ceiling

Mockito controls responses and exceptions with high precision:

```java
when(catalogGateway.fetch("SKU-01"))
        .thenReturn(new ProductView(
                "SKU-01", "Camera", 5));

when(catalogGateway.fetch("MISSING"))
        .thenThrow(new CatalogNotFoundException(
                "MISSING", null));
```

Strengths:

- No network, no Spring context, fast feedback.
- Easy to exercise business rule branches: stock > 0, missing product, failed rules.
- Easy to trigger rare or hard-to-reproduce faults: thrown dependencies, null returns, boundary states.
- `verify(...)` proves which collaborator method ran with which arguments.
- Unit tests stay deterministic absent uncontrolled shared mutable state or clocks.

Still, Mockito only "knows" the methods you mock. If the real HTTP implementation accidentally calls `/v2/items`, a Mockito mock at `CatalogGateway` **never sees it**. If the provider returns `"stock":"5"` as a String while the client DTO expects an int, the mock still hands back int 5 with zero JSON parsing. Whenever service tests never instantiate `HttpCatalogGateway`, zero serialization or deserialization runs.

### 4.1. Is mocking deep down into RestClient any better?

You could mock `RestClient`, `RequestHeadersUriSpec`, `ResponseSpec`, and chained calls. However:

- Tests couple tightly to implementation and call-chain details.
- Mockito can return valid values even when URI, headers, or message converters are misconfigured.
- Generic interfaces across fluent APIs make stubbing brittle and noisy.
- Never exercises HTTP request factory behavior, URI encoding, or status parsing on real requests.
- The deeper you mock, the higher the risk you are testing **your own mock wiring** instead of the HTTP protocol.

Hence it is usually better to **mock the domain interface** in service unit tests and test the client implementation separately against an HTTP stub server.

### 4.2. Interaction verification does not replace state verification

`verify(gateway).fetch("SKU-01")` proves a method call occurred. It does not prove an external server received a valid GET. Conversely, WireMock's `verify(getRequestedFor(...))` proves an HTTP request reached the local server matching method/path/headers, yet does not prove the real external provider answers like the stub.

## 5. What can an HTTP stub server like WireMock do?

WireMock can:

- Listen for HTTP/HTTPS on a configured or dynamically allocated port.
- Match method, URL path, query params, headers, cookies, and request bodies.
- Return HTTP statuses, headers, and JSON/text/binary responses.
- Record a request journal so tests verify call counts and request details.
- Configure priorities, stateful scenarios, response templating, or proxy/recording where appropriate.
- Simulate response delays, malformed responses, connection resets, and various network fault modes.
- Reset stubs/requests so tests stay isolated from each other.

Still, WireMock **does not automatically know the provider's real API contract**. A stub returning 200 when a test expects 200 can disagree with the real system if the provider newly requires `X-Request-Version` or changed its response schema.

### 5.1. Stubs and assertions are not the same thing

A stub:

```java
server.stubFor(
        get(urlPathEqualTo("/v1/products"))
                .withQueryParam("sku", equalTo("SKU-01"))
                .willReturn(okJson(
                        """
                        {"sku":"SKU-01","name":"Camera","stock":5}
                        """)));
```

states that **if** the server receives a GET matching that path/query, it returns this JSON.

An assertion:

```java
assertEquals(5, result.stock());

server.verify(
        1,
        getRequestedFor(urlPathEqualTo("/v1/products"))
                .withQueryParam("sku", equalTo("SKU-01")));
```

states that the client parsed the data properly **and** an HTTP GET matching those conditions actually hit the server. Stubbing alone without calling the client and verifying proves nothing.

### 5.2. Request journals must be reset

WireMock retains recorded requests and stubs (per configuration) between test methods when a server is shared. Every test should clean up:

```java
server.resetAll();
```

when the server belongs solely to that test class. Resetting clears old mappings and requests; in a shared environment with concurrent tests, calling `resetAll` indiscriminately wipes other tests' stubs. Prefer one server per class/suite, or strict namespacing and lifecycle control.

### 5.3. Random ports matter

`new WireMockServer(options().dynamicPort())` avoids hardcoding `8080` or `9090`, which frequently collide on developer machines and CI runners. After `server.start()`, read `server.baseUrl()` to build the REST client.

Never call `server.baseUrl()` to configure an app before the server has started. Never leave `http://localhost:8080` as a fallback in tests when the server starts on a random port.

## 6. HTTP client mechanics in Spring Boot 3.3

Spring Framework 6.1 introduces `RestClient`, a fluent synchronous HTTP client:

```java
ProductView product = restClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/v1/products")
                .queryParam("sku", "SKU-01")
                .build())
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(ProductView.class);
```

Here:

1. Java constructs a URI from path and query parameter.
2. `RestClient` picks an HTTP request factory per config/classpath and dispatches the HTTP request.
3. `Accept: application/json` is sent if configured.
4. The server returns status, headers, and JSON body.
5. A message converter (typically Jackson) converts JSON into the Java record.
6. On HTTP 4xx/5xx, `retrieve()` throws a `RestClientException` subclass by default instead of building a `ProductView`.
7. `body(ProductView.class)` may return `null` on empty bodies; the client must decide how to handle that per contract.

**Spring Boot can auto-configure a `RestClient.Builder`**. When using the injected builder, verify context wiring separately with `@SpringBootTest` or `@RestClientTest`; calling `RestClient.builder()` manually in plain Java tests skips customizations attached to Boot's auto-configured builder.

### 6.1. Helpful exception types

| Scenario | Common exception / behavior |
| --- | --- |
| 404 | `HttpClientErrorException.NotFound` |
| 400 | `HttpClientErrorException.BadRequest` |
| 429 | `HttpClientErrorException.TooManyRequests` |
| 500 | `HttpServerErrorException.InternalServerError` |
| Other 4xx/5xx | `RestClientResponseException` or subclass |
| Connection failure / read timeout | `ResourceAccessException` (typically with nested I/O exception) |
| Unconvertible JSON | `RestClientException` / matching message conversion exception |
| 204 No Content | Body can be `null` |
| 302 redirect | Depends on underlying HTTP client/redirect policy; never assume every client follows it |
| Retry | **Not a built-in business-level retry**; requires explicit policy configuration |

Exact exception classes depend on Spring Framework, request factory, and custom status handlers. Tests should assert types specific enough for the contract without locking onto internal HTTP client message strings.

### 6.2. RestClient vs. WebClient vs. RestTemplate

- `RestClient`: Spring Framework's newer synchronous client, fitting Java 17/Boot 3.3 examples.
- `RestTemplate`: older synchronous API, still used in many existing systems.
- `WebClient`: reactive/non-blocking, built on Reactor `Mono`/`Flux` and event loops.
- OpenFeign / HTTP interface clients: carry their own decoders, error decoders, and retry settings per stack.

HTTP stub server principles apply across all of them, yet bean wiring, timeouts, request factories, exceptions, and assertions must match **the actual client used in production**—never run `RestClient` experiments and claim you verified `WebClient`.

## 7. Runnable project: Java 17 + Spring Boot 3.3.0 + Mockito + WireMock 3

The sample project has **three groups**:

1. **Java-level unit tests:** `InventoryServiceMockTest` mocks `CatalogGateway` with Mockito. No Spring context or HTTP.
2. **WireMock HTTP integration tests:** `HttpCatalogGatewayWireMockTest` runs a dynamic-port WireMock server and sends real requests via `RestClient`.
3. **Spring wiring test:** `CatalogWiringSpringTest` uses `@SpringBootTest` with `@DynamicPropertySource` providing the server URL, then asserts `InventoryService` gets a response through the Boot-wired `CatalogGateway` bean.

Illustrative versions: Java 17, Spring Boot **3.3.0**, WireMock **3.9.1**. Do not treat these versions as the latest production baseline; they keep APIs and imports consistent. In real projects, upgrade versions per your BOM and security policy.

### 7.1. Directory tree

```text
http-stub-boundary/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/httpclient/
    │   ├── DemoApplication.java
    │   ├── ProductView.java
    │   ├── CatalogGateway.java
    │   ├── CatalogNotFoundException.java
    │   ├── HttpCatalogGateway.java
    │   ├── CatalogClientConfiguration.java
    │   └── InventoryService.java
    └── test/java/example/httpclient/
        ├── InventoryServiceMockTest.java
        ├── HttpCatalogGatewayWireMockTest.java
        └── CatalogWiringSpringTest.java
```

No Maven/Gradle Wrapper binaries are shown in the tree; generate/commit a wrapper with a compatible Gradle version. The suite needs no Docker, database, or internet access once dependencies sit in the Gradle cache.

### 7.2. `settings.gradle`

```groovy
rootProject.name = 'http-stub-boundary'
```

### 7.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.wiremock:wiremock-standalone:3.9.1'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` provides Spring MVC, `RestClient`, and Jackson HTTP message converters. `spring-boot-starter-test` provides JUnit Jupiter, Mockito, and Spring Test. `wiremock-standalone` is the shaded standalone WireMock 3 artifact minimizing transitive Jetty/Jackson clashes on the test classpath; it is not a Docker server.

**Why WireMock 3.9.1?** `org.wiremock:wiremock-standalone:3.9.1` is published on Maven Central and aligns with the documented APIs here; pinning it ensures a runnable example without claiming 3.9.1 is the latest security baseline.

## 8. Java source: domain interface separated from the HTTP protocol

### 8.1. `DemoApplication.java`

**`src/main/java/example/httpclient/DemoApplication.java`:**

```java
package example.httpclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

This app defines an outbound HTTP client bean; it **does not** launch a mock server on `bootRun`. To run the full app outside tests, supply `catalog.base-url` pointing to an intentional provider or sandbox. Never embed a default production URL in source.

### 8.2. `ProductView.java`

**`src/main/java/example/httpclient/ProductView.java`:**

```java
package example.httpclient;

public record ProductView(
        String sku,
        String name,
        int stock) {}
```

Java 17 record representing downstream API data. Spring Boot's Jackson deserializes JSON keys `sku`, `name`, and `stock` into it. This is a **client DTO**, not a JPA entity or complete domain validation type.

Because `stock` is a primitive `int`, JSON omitting that field may map silently to `0` under lenient Jackson settings. Hence a decoded 200 response **does not automatically prove a complete provider schema**; enforce contracts/Bean Validation or strict mapper settings when missing fields are critical errors.

### 8.3. `CatalogGateway.java`

**`src/main/java/example/httpclient/CatalogGateway.java`:**

```java
package example.httpclient;

public interface CatalogGateway {
    ProductView fetch(String sku);
}
```

This interface is the application-owned boundary. The service knows nothing about URLs, HTTP methods, or Jackson; it only knows `fetch` returns `ProductView` on success and throws a domain exception when missing.

Mockito unit tests mock this interface; WireMock tests **never mock** it and instead exercise the real `HttpCatalogGateway` implementation.

### 8.4. `CatalogNotFoundException.java`

**`src/main/java/example/httpclient/CatalogNotFoundException.java`:**

```java
package example.httpclient;

public final class CatalogNotFoundException
        extends RuntimeException {
    public CatalogNotFoundException(
            String sku, Throwable cause) {
        super("Catalog item not found: " + sku, cause);
    }
}
```

This class translates HTTP 404 into a domain concept. Never lump all 4xx codes into not-found: 401, 403, and 429 carry distinct meanings requiring separate policies.

### 8.5. `HttpCatalogGateway.java` — real client implementation

**`src/main/java/example/httpclient/HttpCatalogGateway.java`:**

```java
package example.httpclient;

import org.springframework.http.MediaType;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

public final class HttpCatalogGateway
        implements CatalogGateway {
    private final RestClient client;

    public HttpCatalogGateway(RestClient client) {
        this.client = client;
    }

    @Override
    public ProductView fetch(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }

        try {
            ProductView result = client.get()
                    .uri(uriBuilder -> uriBuilder
                            .path("/v1/products")
                            .queryParam("sku", sku)
                            .build())
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(ProductView.class);

            if (result == null) {
                throw new IllegalStateException(
                        "Remote catalog returned no body");
            }

            return result;
        }
        catch (HttpClientErrorException.NotFound ex) {
            throw new CatalogNotFoundException(sku, ex);
        }
    }
}
```

Here is everything Java-layer mocks skip while WireMock HTTP tests exercise:

- HTTP `GET`.
- Path `/v1/products`.
- Query parameter `sku` from user input (encoded via `UriBuilder`).
- `Accept: application/json`.
- `retrieve()` HTTP status handling.
- Jackson message conversion JSON → Java record.
- Mapping 404 to `CatalogNotFoundException`.
- Turning 204/null body into `IllegalStateException`.
- Propagating 500/429 as Spring `RestClient` exceptions (the lesson adds no retry/fallback yet).

**Avoid `new URL(baseUrl + "/...?" + sku)`** because raw string concatenation invites escaping bugs, double slashes, and query injection. `UriBuilder` handles paths and queries safely.

### 8.6. `InventoryService.java`

**`src/main/java/example/httpclient/InventoryService.java`:**

```java
package example.httpclient;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final CatalogGateway gateway;

    public InventoryService(CatalogGateway gateway) {
        this.gateway = gateway;
    }

    public boolean isInStock(String sku) {
        return gateway.fetch(sku).stock() > 0;
    }
}
```

The business rule is intentionally small: positive stock means available. This class knows nothing about HTTP. Thus **its best unit tests need no WireMock**; Mockito suffices to test in-stock vs. out-of-stock branches.

If the service later adds thresholds, stock reservation, fallbacks, or event publishing, unit tests can cover all that Java logic without dragging the HTTP stack into every case.

### 8.7. `CatalogClientConfiguration.java`

**`src/main/java/example/httpclient/CatalogClientConfiguration.java`:**

```java
package example.httpclient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    CatalogGateway catalogGateway(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {
        RestClient client = builder
                .baseUrl(baseUrl)
                .build();

        return new HttpCatalogGateway(client);
    }
}
```

Property `catalog.base-url` **must be supplied** when starting the full context. In `CatalogWiringSpringTest`, it comes from `@DynamicPropertySource` pointing to the running WireMock server.

Spring Boot 3.3 auto-configures `RestClient.Builder`. Injecting the builder lets configuration inherit Boot-managed customizers, converters, and observability hooks. Tests calling `RestClient.builder()` directly **miss verifying that wiring**—which is why a dedicated Spring context test exists.

## 9. Mockito unit tests: proving business logic without HTTP

**`src/test/java/example/httpclient/InventoryServiceMockTest.java`:**

```java
package example.httpclient;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class InventoryServiceMockTest {
    @Mock
    CatalogGateway gateway;

    @InjectMocks
    InventoryService service;

    @Test
    void availableWhenRemoteStockIsPositive() {
        when(gateway.fetch("SKU-01")).thenReturn(
                new ProductView(
                        "SKU-01", "Camera", 5));

        assertTrue(service.isInStock("SKU-01"));

        verify(gateway).fetch("SKU-01");
    }

    @Test
    void unavailableWhenStockIsZero() {
        when(gateway.fetch("SKU-02")).thenReturn(
                new ProductView(
                        "SKU-02", "Lens", 0));

        assertFalse(service.isInStock("SKU-02"));

        verify(gateway).fetch("SKU-02");
    }

    @Test
    void propagatesDomainNotFoundFailure() {
        when(gateway.fetch("MISSING")).thenThrow(
                new CatalogNotFoundException(
                        "MISSING", null));

        assertThrows(
                CatalogNotFoundException.class,
                () -> service.isInStock("MISSING"));
    }
}
```

These three tests instantiate no `RestClient`, load no Spring context, and open no network. **They remain highly valuable**:

- The `stock > 0` rule works.
- The service passes `sku` through to the gateway.
- The service does not swallow a gateway-normalized domain failure.

Yet they **cannot assert** that `HttpCatalogGateway` hits the right URL/headers, decodes JSON/HTTP statuses properly, or communicates over TCP.

### 9.1. Why skip @SpringBootTest for these three tests?

It is unnecessary. `MockitoExtension` injects the mock into `InventoryService`'s constructor right in JUnit. Loading a full Spring context slows tests down and pulls in unrelated config without adding evidence for this business rule.

### 9.2. @Mock, @MockBean, @MockitoBean, and versions

- Mockito's `@Mock` creates a plain Java mock outside any Spring context.
- In Spring Boot 3.3, `@MockBean` replaces/adds a mock bean inside `ApplicationContext` for Spring tests; it still **swaps a Java bean** without opening HTTP networking.
- Starting in Boot 3.4, `@MockBean` is deprecated in favor of Spring Framework's `@MockitoBean`; handle imports/version migrations accordingly.
- `@MockitoBean` is still a bean-level mock; changing annotations **does not turn** a test into HTTP transport integration.

Never assume "`@SpringBootTest` + `@MockBean` on the HTTP gateway" tests the HTTP client. Once the gateway bean is mocked, execution stops **before** `RestClient`.

## 10. WireMock HTTP tests: running the real client over sockets

**`src/test/java/example/httpclient/HttpCatalogGatewayWireMockTest.java`:**

```java
package example.httpclient;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpCatalogGatewayWireMockTest {
    private static WireMockServer server;

    private HttpCatalogGateway gateway;

    @BeforeAll
    static void startServer() {
        server = new WireMockServer(
                options().dynamicPort());
        server.start();
    }

    @AfterAll
    static void stopServer() {
        if (server != null) {
            server.stop();
        }
    }

    @BeforeEach
    void resetAndCreateClient() {
        server.resetAll();

        gateway = new HttpCatalogGateway(
                RestClient.builder()
                        .baseUrl(server.baseUrl())
                        .build());
    }

    @Test
    void sendsRealGetWithQueryAndAcceptAndReadsJson() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("SKU-01"))
                        .withHeader(
                                "Accept",
                                containing("application/json"))
                        .willReturn(okJson(
                                """
                                {
                                  "sku":"SKU-01",
                                  "name":"Camera",
                                  "stock":5
                                }
                                """)));

        ProductView actual = gateway.fetch("SKU-01");

        assertEquals("SKU-01", actual.sku());
        assertEquals("Camera", actual.name());
        assertEquals(5, actual.stock());

        server.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("SKU-01"))
                        .withHeader(
                                "Accept",
                                containing("application/json")));
    }

    @Test
    void uriBuilderEncodesSpacesInQueryParameter() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("USB C"))
                        .willReturn(okJson(
                                """
                                {
                                  "sku":"USB C",
                                  "name":"Adapter",
                                  "stock":2
                                }
                                """)));

        ProductView product = gateway.fetch("USB C");

        assertEquals("USB C", product.sku());

        server.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("USB C")));
    }

    @Test
    void mapsHttp404IntoDomainNotFoundException() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("MISSING"))
                        .willReturn(aResponse()
                                .withStatus(404)
                                .withBody(
                                        "{\"error\":\"not found\"}")));

        CatalogNotFoundException thrown =
                assertThrows(
                        CatalogNotFoundException.class,
                        () -> gateway.fetch("MISSING"));

        assertTrue(
                thrown.getMessage().contains("MISSING"));

        server.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("MISSING")));
    }

    @Test
    void keepsHttp500AsServerFailure() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("BROKEN"))
                        .willReturn(aResponse()
                                .withStatus(500)
                                .withHeader(
                                        "Content-Type",
                                        "application/json")
                                .withBody(
                                        "{\"error\":\"temporary\"}")));

        assertThrows(
                HttpServerErrorException.class,
                () -> gateway.fetch("BROKEN"));
    }

    @Test
    void http429IsNotAutomaticallyRetried() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("LIMITED"))
                        .willReturn(aResponse()
                                .withStatus(429)
                                .withHeader("Retry-After", "3")));

        HttpClientErrorException.TooManyRequests ex =
                assertThrows(
                        HttpClientErrorException
                                .TooManyRequests.class,
                        () -> gateway.fetch("LIMITED"));

        assertEquals(429, ex.getStatusCode().value());
        assertEquals(
                "3",
                ex.getResponseHeaders()
                        .getFirst("Retry-After"));

        server.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("LIMITED")));
    }

    @Test
    void malformedJsonCannotBecomeProductView() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("INVALID"))
                        .willReturn(aResponse()
                                .withStatus(200)
                                .withHeader(
                                        "Content-Type",
                                        "application/json")
                                .withBody(
                                        "{\"sku\":\"INVALID\",")));

        assertThrows(
                RestClientException.class,
                () -> gateway.fetch("INVALID"));
    }

    @Test
    void noContentIsNotTreatedAsAnAvailableItem() {
        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("EMPTY"))
                        .willReturn(aResponse()
                                .withStatus(204)));

        IllegalStateException ex = assertThrows(
                IllegalStateException.class,
                () -> gateway.fetch("EMPTY"));

        assertTrue(
                ex.getMessage().contains("no body"));
    }

    @Test
    void rejectsBlankSkuBeforeAnyNetworkRequest() {
        assertThrows(
                IllegalArgumentException.class,
                () -> gateway.fetch("  "));

        server.verify(
                0,
                getRequestedFor(
                        urlPathEqualTo("/v1/products")));
    }

    @Test
    void sendsExplicitClientHeaderWhenConfigured() {
        HttpCatalogGateway withHeader =
                new HttpCatalogGateway(
                        RestClient.builder()
                                .baseUrl(server.baseUrl())
                                .defaultHeader(
                                        "X-Catalog-Key",
                                        "demo-test-key")
                                .build());

        server.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("SKU-KEY"))
                        .withHeader(
                                "X-Catalog-Key",
                                equalTo("demo-test-key"))
                        .willReturn(okJson(
                                """
                                {
                                  "sku":"SKU-KEY",
                                  "name":"Cable",
                                  "stock":7
                                }
                                """)));

        assertEquals(
                7,
                withHeader.fetch("SKU-KEY").stock());

        server.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withHeader(
                                "X-Catalog-Key",
                                equalTo("demo-test-key")));
    }
}
```

**There are 9 test methods** in the WireMock class above. The HTTP server starts once for the class, resets mappings and request journal before each method, and stops at the end.

### 10.1. What the 200 test proves

`sendsRealGetWithQueryAndAcceptAndReadsJson`:

1. `RestClient` fires a real HTTP GET rather than calling Mockito.
2. WireMock receives `/v1/products`.
3. Query parameter `sku=SKU-01` is transmitted.
4. `Accept` header contains `application/json`.
5. Server returns JSON with `sku`/`name`/`stock` keys.
6. Spring's HTTP message converter deserializes JSON into the Java record.
7. Test asserts record values and request count equal to 1.

**This is loopback HTTP transport/codec evidence**, not proof that the real external catalog provider returns that JSON.

### 10.2. What does the encoding test prove?

`uriBuilderEncodesSpacesInQueryParameter` passes `"USB C"`. The HTTP request URI must be encoded properly so the server parses the query parameter back into that value. The WireMock test matches the decoded query param `USB C`, catching bugs caused by raw URI string concatenation containing unencoded spaces.

To verify byte-level percent-encoding such as `%20` vs. `+`, inspect the recorded raw URL and assert per contract. Avoid enforcing one encoding style purely out of personal preference: servers normally decode both to the same logical query value per query-parser rules. When `+`, `%`, `&`, Unicode, or path-segment slashes matter, add explicit boundary tests.

### 10.3. What the 404 test proves about client error handling

Spring's `retrieve()` throws `HttpClientErrorException.NotFound` on 404 by default. `HttpCatalogGateway` catches it and translates it into `CatalogNotFoundException`.

In the Mockito service test, `CatalogNotFoundException` was **manually constructed and thrown by the mock**; only the WireMock test proves the **HTTP 404 → Spring exception → domain exception** translation actually executes.

### 10.4. 429 and Retry-After do not mean retries happened

In `http429IsNotAutomaticallyRetried`, the fake server returns HTTP 429 with `Retry-After: 3`. The test asserts the exception carries status 429 and that header, with request count equal to **1**.

Because the client has no retry policy wired, tests **must not** conclude "`RestClient` will retry after 3 seconds." When using Spring Retry, Resilience4j, or custom interceptors, write dedicated tests for attempt counts, bounded backoff, and exhaustion behavior. Above all, never auto-retry non-idempotent payment/create POSTs without an idempotency key and clear provider contract.

### 10.5. 204 and malformed JSON

- `204 No Content` normally has no body. The sample client throws `IllegalStateException` instead of fabricating a `ProductView` with `stock=0`.
- HTTP 200 + malformed JSON must fail decoding rather than becoming a valid product.

Syntactically valid JSON **missing a field** might not fail under lenient Jackson defaults. Add validation/strict schema mapping where appropriate; never equate "deserializes without throwing" with "provider contract intact."

### 10.6. Header tests are not complete security tests

`X-Catalog-Key: demo-test-key` is a synthetic value. WireMock proves the header arrived at the local server; it does not prove the real provider accepts the token, validates signatures, refreshes expired tokens, or protects headers over TLS on the internet.

Never log production tokens or embed real secrets in fake HTTP tests.

## 11. Spring Boot wiring test: real config pointing to the fake HTTP server

Next, verify Spring Boot actually injects `catalog.base-url` into the `CatalogGateway` bean.

**`src/test/java/example/httpclient/CatalogWiringSpringTest.java`:**

```java
package example.httpclient;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CatalogWiringSpringTest {
    private static final WireMockServer SERVER =
            new WireMockServer(
                    options().dynamicPort());

    // Start before Spring evaluates DynamicPropertySource.
    static {
        SERVER.start();
    }

    @DynamicPropertySource
    static void catalogProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
                "catalog.base-url",
                SERVER::baseUrl);
    }

    @Autowired
    InventoryService inventoryService;

    @BeforeEach
    void resetStubState() {
        SERVER.resetAll();
    }

    @AfterAll
    static void shutDown() {
        SERVER.stop();
    }

    @Test
    void actualSpringBeanUsesHttpServerUrl() {
        SERVER.stubFor(
                get(urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("WIRE-01"))
                        .willReturn(okJson(
                                """
                                {
                                  "sku":"WIRE-01",
                                  "name":"Keyboard",
                                  "stock":3
                                }
                                """)));

        assertTrue(
                inventoryService.isInStock("WIRE-01"));

        SERVER.verify(
                1,
                getRequestedFor(
                        urlPathEqualTo("/v1/products"))
                        .withQueryParam(
                                "sku", equalTo("WIRE-01")));
    }
}
```

The sample intentionally starts WireMock in a **static initializer** before the Spring context evaluates dynamic properties. That ensures `SERVER::baseUrl` yields a valid URL when `CatalogClientConfiguration` builds the bean. After the test class finishes, `@AfterAll` stops the server.

**Context cache warning:** Spring TestContext caches the `ApplicationContext` after the class ends while WireMock here has stopped. If another class reuses that context/cache key holding a client bound to the old server, tests fail. The demo keeps **a single Spring wiring class** for illustration; large suites should tie the server lifecycle to the Spring context or isolate contexts deliberately rather than sharing servers haphazardly.

### 11.1. How this differs from the WireMock test without Spring context

- `HttpCatalogGatewayWireMockTest` manually calls `RestClient.builder()` and the constructor. It tests HTTP client behavior narrowly and quickly.
- `CatalogWiringSpringTest` boots the Spring Boot context, injects the auto-configured `RestClient.Builder`, reads `catalog.base-url`, creates the `CatalogGateway` bean, injects `InventoryService`, and calls the fake server.
- No Spring MVC inbound server starts (`webEnvironment=NONE`); only **outbound HTTP** goes to WireMock—matching the exact scope under test.

### 11.2. When do you need a full application HTTP test?

To test both inbound API controllers and outbound HTTP clients together, use `@SpringBootTest(webEnvironment=RANDOM_PORT)`, send an HTTP request to the controller with a real HTTP client, and verify WireMock received the outbound call. That is more involved and requires keeping two ports distinct:

1. Spring Boot's inbound server port.
2. WireMock's outbound fake server port.

Never refer to those as "one HTTP server," and never use Spring Boot's `@LocalServerPort` in place of WireMock's port.

## 12. Run commands and test counts

From a directory with a Gradle Wrapper compatible with Boot 3.3 / JDK 17 (e.g., Gradle 8.7):

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.httpclient.InventoryServiceMockTest
./gradlew test --tests example.httpclient.HttpCatalogGatewayWireMockTest
./gradlew test --tests example.httpclient.CatalogWiringSpringTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.httpclient.HttpCatalogGatewayWireMockTest
```

Expected:

| Class | Method count | Spring context? | HTTP network? |
| --- | ---: | --- | --- |
| `InventoryServiceMockTest` | 3 | No | No |
| `HttpCatalogGatewayWireMockTest` | 9 | No | Yes, localhost |
| `CatalogWiringSpringTest` | 1 | Yes | Yes, localhost |
| **Total** | **13** | Per class | Per class |

With compatible dependencies and environment, all 13 test methods are **expected to pass**; Gradle typically reports `BUILD SUCCESSFUL`. These numbers are **expected**, not a claim that Gradle was executed while writing this guide. The example has no fixed business stdout. Each test class can run standalone with no Docker.

### 12.1. Can you run `bootRun`?

The main application requires `catalog.base-url`. If you have a provider sandbox or a WireMock server listening at a controlled address, pass:

```bash
./gradlew bootRun --args='--catalog.base-url=http://127.0.0.1:8089'
```

This is a configuration example command; it **does not automatically start WireMock on port 8089**. Without an external server or property, context startup fails or HTTP calls cannot connect. The runnable scope of this lesson is `./gradlew test`, where tests start the fake server and inject the URL automatically.

### 12.2. Never print request/response secrets

In CI, HTTP client logs may contain `Authorization` headers, API keys, cookies, PII, or user payloads. Use synthetic data and scrub secrets before logging—especially on test failures when WireMock dumps unmatched requests.

## 13. `@RestClientTest` + `MockRestServiceServer`: a client-layer solution

Spring Boot 3.3 offers `@RestClientTest` to test REST clients as a **test slice**. It auto-configures JSON codecs, `RestClient.Builder`, and `MockRestServiceServer`:

```java
@RestClientTest(CatalogHttpClientComponent.class)
class CatalogClientSliceTest {
    @Autowired
    MockRestServiceServer server;
    // ...
}
```

This is a **structural illustration, not runnable in the sample project** because no `CatalogHttpClientComponent` class exists. It serves for comparison only—you do not need to create it in the lab.

`MockRestServiceServer` lets you define HTTP expectations and synthetic responses **without opening HTTP sockets**:

```java
RestClient.Builder builder = RestClient.builder();

MockRestServiceServer fake =
        MockRestServiceServer.bindTo(builder).build();

RestClient client = builder
        .baseUrl("https://catalog.example.invalid")
        .build();

fake.expect(requestTo(
        "https://catalog.example.invalid/v1/products?sku=SKU-01"))
    .andExpect(method(HttpMethod.GET))
    .andRespond(withSuccess(
        """
        {"sku":"SKU-01","name":"Camera","stock":5}
        """,
        MediaType.APPLICATION_JSON));

ProductView actual = client.get()
        .uri("/v1/products?sku=SKU-01")
        .retrieve()
        .body(ProductView.class);

assertEquals(5, actual.stock());
fake.verify();
```

This snippet **requires imports and a test method context**; it is not a complete file. Helpers come from `org.springframework.test.web.client.MockRestServiceServer`, `MockRestRequestMatchers.*`, and `MockRestResponseCreators.*`; `HttpMethod`/`MediaType` come from Spring HTTP.

**Key takeaway:** the request factory is replaced by a client-layer fake, so you verify URI/method/headers/body/codecs when using Spring `RestClient`, while **not** testing connection refused, TLS handshakes, OS socket behavior, or a real TCP peer.

### 13.1. When to choose MockRestServiceServer?

- You need to verify `RestClient` serialization/message converters, URI, method, and response mapping.
- Low-level network characteristics are not under test.
- You want a fast Spring test slice with minimal infrastructure.
- You do not need to share the fake server with a client running in another process.
- You want concise expectation-based tests right inside JUnit.

### 13.2. When to choose WireMock/MockWebServer?

- You want **real HTTP requests over sockets**.
- You want a server-side request journal independent of the HTTP client abstraction.
- You want to test Java `HttpClient`, OkHttp, Apache `HttpClient`, Feign, `RestTemplate`, `WebClient`, or multiple distinct clients.
- You need to simulate response delays, connection faults, redirects, content encoding, or transport-level HTTP status behavior.
- You want an app under test in another container/process to connect to the fake server over configured networking.
- You want consumer-driven contract stubs or mock HTTP services for end-to-end-style suites.

**Never assume** WireMock tests are universally superior to `MockRestServiceServer` tests. The right choice is the shallowest layer that still catches bugs at the boundary under test.

## 14. True limits of HTTP stub servers

### 14.1. Stubs only reflect the test author's assumptions

If the consumer assumes the provider returns:

```json
{"sku":"SKU-01","name":"Camera","stock":5}
```

while the live API now returns:

```json
{"product_id":"SKU-01","display_name":"Camera","inventory":{"available":5}}
```

WireMock stays green serving the first response. The test protects the **assumed contract**, not whether the provider still honors it.

Solutions:

- Maintain versioned API contracts (OpenAPI/JSON Schema/Pact).
- Use **provider verification** checking that the real provider satisfies consumer expectations.
- When a sandbox API exists, run periodic smoke/contract tests against it.
- Update consumer tests/stubs and provider verifiers together under review when schemas change.
- Never record live production traffic containing PII/secrets and commit it directly as fixtures.

### 14.2. TLS/PKI is not fully tested by localhost HTTP

Default HTTP loopback WireMock does not prove:

- TLS certificate trust chains or hostname validation.
- mTLS client certificates.
- TLS protocol/cipher compatibility.
- Corporate proxy/network policies.
- Production DNS/load-balancer behavior.

WireMock can enable HTTPS to test parts of client TLS configuration, though local/self-signed certificates differ from production CA chains and rotation. Test those requirements in an environment matching them.

### 14.3. Authentication is just a header unless the fake server validates it

WireMock matching `Authorization: Bearer test-token` or `X-Api-Key` proves the request carries that header. It does not confirm the real server validates OAuth scopes, JWT signatures, expiration, mTLS identities, or IAM policies.

When auth is a primary risk, test token acquisition/refresh and provider auth behavior separately—never treat "stub returned 200 when header existed" as security proof.

### 14.4. Provider business side effects are not executed

A fake payment API returning:

```json
{"transactionStatus":"AUTHORIZED"}
```

does not prove funds were held or reconciliation works. Likewise, a fake email provider returning 202 does not prove emails were delivered, and a fake Kafka REST proxy returning success does not prove consumers received messages.

Never label a test "end-to-end" when an upstream provider is stubbed at a critical boundary. Call it **consumer integration against an HTTP stub**.

### 14.5. HTTP/2, connection pooling, redirects, streaming

A local fake server often speaks HTTP/1.1, while production uses HTTP/2, reverse proxies, compression, streaming responses, or connection pooling.

- If clients depend on HTTP/2 multiplexing, test against a server/harness that genuinely supports it.
- Redirect behavior depends on the request factory; never assume every client follows 302.
- Chunked responses, slow streaming, and large bodies often need specialized tests.
- Request-count assertions under retries/concurrency must separate logical actions from physical HTTP attempts.
- WireMock's request journal may omit low-level connection negotiation details.

## 15. Status codes belong to the contract, not just bodies

| Response | Common meaning | What the client must decide |
| --- | --- | --- |
| 200 OK | Successful response with body | Parse DTO, validate required fields |
| 201 Created | New resource | Read `Location`/body, idempotency on retry |
| 202 Accepted | Asynchronous processing | Poll/callback; do not treat as finished |
| 204 No Content | Empty response body | Never force DTO deserialization |
| 301/302/307/308 | Redirect | Redirect policy, auth header leakage, method preservation |
| 400 Bad Request | Input violates contract | Never retry unconditionally |
| 401 Unauthorized | Unauthenticated | Refresh token / block loops per policy |
| 403 Forbidden | Insufficient permissions | Never treat as NotFound |
| 404 Not Found | Missing resource or wrong endpoint | Correct domain mapping, detect stub mismatches |
| 409 Conflict | State conflict | Business compensation/idempotency |
| 422 Unprocessable Entity | Validation/domain failure | Return meaningful error |
| 429 Too Many Requests | Rate limit | `Retry-After`, backoff, bounded retry |
| 500 Internal Server Error | Server failure | Retry per idempotency/circuit-breaker policy |
| 502/503/504 | Gateway/upstream unavailable | Controlled timeout/backoff/fallback |

**Do not stub only happy-path 200.** HTTP clients commonly fail in non-ideal states. Test status mapping across every branch the application owns.

## 16. Negative HTTP tests must separate client errors from stub errors

A classic trap: WireMock **finds no matching mapping** and returns HTTP 404 on its own. The client test receives 404, translates it into `CatalogNotFoundException`, and the author thinks they tested "provider returned not found."

In our lab's 404 test, we **explicitly stub `sku=MISSING` to return 404** and verify the exact request. If a mapping is wrong (e.g., wrong query param), WireMock also returns an unmatched 404—so asserting only the exception passes falsely.

To prevent false positives:

1. Verify the request method/path/query/headers that reached the server.
2. Confirm the intended stub matched rather than checking only the final status.
3. Add unique response header/body markers per scenario if needed.
4. Inspect unmatched request journals/near misses when tests fail.
5. Reset stubs and request journals between methods.
6. Avoid global catch-all stubs returning 200 for every URL in the suite.
7. Use exact URL path matchers instead of overly broad regexes.

For critical cases, attach a header like `X-Scenario: not-found` to the stub and assert response details before domain exception mapping (provided client design exposes headers/causes appropriately).

### 16.1. Stub priority and overlapping mappings

Multiple WireMock stubs may match one request; priority or registration order can pick an unintended response. Using `urlMatching(".*")` as a "default 200" masks mistyped paths. Write specific stubs and reset before every test to avoid inheriting ambiguous mappings.

### 16.2. Never test "400" by hitting an unstubbed URL

When testing HTTP 400, register a stub **returning 400** for that exact request and assert error mapping. An unmatched request produces 404 instead and tests the wrong path.

## 17. Timeouts, connection resets, delays, and fault injection

Mockito can be configured as:

```java
when(gateway.fetch("SKU-SLOW"))
        .thenThrow(new RuntimeException("timeout"));
```

Yet that is **not** a real socket timeout: it tests neither whether the request factory sets a read timeout nor whether the client aborts the connection.

WireMock can simulate:

```java
server.stubFor(
    get(urlPathEqualTo("/v1/products"))
        .withQueryParam("sku", equalTo("SLOW"))
        .willReturn(aResponse()
            .withStatus(200)
            .withFixedDelay(1500)
            .withHeader("Content-Type", "application/json")
            .withBody(
                "{\"sku\":\"SLOW\",\"name\":\"Demo\",\"stock\":1}")));
```

This is an **illustrative code snippet**, not among the 13 runnable test methods. To test timeouts, the client must configure an explicit timeout **shorter** than the delay (e.g., 300 ms); when the request factory triggers a read timeout, Spring normally wraps it in `ResourceAccessException`.

In Spring, the request factory is decisive. Conceptual `SimpleClientHttpRequestFactory` example:

```java
SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();

factory.setConnectTimeout(300);
factory.setReadTimeout(300);

RestClient client = RestClient.builder()
        .requestFactory(factory)
        .baseUrl(server.baseUrl())
        .build();
```

This snippet requires importing `org.springframework.http.client.SimpleClientHttpRequestFactory`; it depends on client/OS socket behavior rather than guaranteeing tests finish in exactly 300 ms. The main lab omits timing-sensitive tests to keep CI free of flakiness.

### 17.1. Writing less-flaky timeout tests

- Configure real connect/read timeouts on the production HTTP client or test variant.
- Use delayed responses/fault injection properly instead of arbitrary `Thread.sleep`.
- Use bounded timeouts and assert **exception types and request counts**, never exact millisecond durations.
- Leave a wide margin between the client read timeout and stub delay.
- Keep tests independent of shared thread-pool state.
- Clean up server/client resources after tests to avoid leaked threads or connections.
- When testing retry/backoff, use fake clocks/schedulers or Resilience4j test utilities if supported.
- Never add infinite retries to "fix" timing tests.

### 17.2. Connect timeouts differ from read timeouts

- **Connect timeout:** failed to establish a TCP connection to the endpoint within the limit.
- **Read timeout:** connected successfully, then waited too long for response data.
- **Server returning HTTP 504:** this is an **HTTP response**, not a client socket read timeout.
- **Connection refused/reset:** transport failure, usually carrying no HTTP status code.

A Java mock throwing `RuntimeException("timeout")` cannot distinguish these four cases. An HTTP stub server helps verify part of transport, while real DNS/TLS/network-chaos still require dedicated infrastructure.

## 18. Authentication, cookies, content types, and compression

An outbound HTTP request carries many contracts beyond its JSON body:

- `Authorization` bearer/API key, scopes, refresh/expiry.
- `Accept` declaring acceptable response formats.
- `Content-Type` declaring sent body format, especially for POST/PUT.
- `User-Agent`, `X-Correlation-ID`, trace headers, idempotency keys.
- Cookies/sessions/CSRF (especially for APIs using browser-like auth).
- Gzip/deflate `Content-Encoding` and `Accept-Encoding`.
- Caching headers `ETag`, `If-None-Match`, `Cache-Control`.
- `Location` header and URI encoding/redirects.
- HTTP request/body size limits.

WireMock matches headers and bodies to catch request-construction bugs. Yet the stub server **never** tests the provider's real security checks; when critical, add provider verification or sandbox tests.

### 18.1. Never mix up Accept and Content-Type

On a bodyless GET, the client sends `Accept: application/json` when expecting JSON back. `Content-Type` describes the **request body**, so GET normally needs no `Content-Type`. On POST JSON, verify both serialization and `Content-Type: application/json` alongside payload/schema checks.

### 18.2. Query param encoding and injection

Using `UriBuilder` avoids raw string concatenation:

```java
client.get()
    .uri(b -> b.path("/v1/products")
        .queryParam("sku", "USB C")
        .build())
```

When inputs contain `?`, `&`, `+`, `%`, and Unicode, proper encoding/interpretation depends on `UriBuilder`'s default encoding mode. Test boundary inputs per contract rather than only `"Hello World"`.

## 19. Socketless MockRestServiceServer: strengths and limits

Some claim **WireMock is always better** than `MockRestServiceServer`. That is untrue:

- For a `RestClient` using standard message converters and `UriBuilder`, `MockRestServiceServer` already catches wrong methods, paths, headers, and JSON mapping.
- It starts fast, uses zero ports/sockets, and isolates cleanly.
- It does not fully test transport behavior: TCP connects, socket closes, TLS, HTTP versions, connection pooling, or wire-level chunking.
- If the app uses a different Java HTTP client (e.g., Java 17 `HttpClient` directly), `MockRestServiceServer` cannot intercept it automatically; socket-based WireMock has broader reach.
- If a Spring Boot client bean installs a custom `ClientHttpRequestFactory`, `MockRestServiceServer` swaps the request factory for a mock and inadvertently **skips testing that custom factory**.

Choose the right tier:

```text
Need to test pure service logic?
    -> Mockito mock on Java gateway.

Need to test Spring RestClient request/JSON/status
without sockets?
    -> @RestClientTest + MockRestServiceServer.

Need to test real HTTP client over localhost TCP,
status/headers/transport behavior?
    -> WireMock or MockWebServer.

Need to prove the provider still honors the contract?
    -> Consumer/provider contract verification or sandbox.

Need to prove production TLS/ingress/auth/HA?
    -> Staging/deployment tests with matching infrastructure.
```

## 20. Never mock RestClient and call it HTTP integration

An anti-pattern is mocking the entire fluent chain:

```java
// Illustrates the anti-pattern only: real code with generic
// fluent interfaces needs even messier mocking/stubbing.
when(responseSpec.body(ProductView.class))
        .thenReturn(new ProductView(
                "SKU-01", "Camera", 5));
```

This snippet is not standalone since `responseSpec` and the `RestClient` chain are undeclared. What it shows is: mocking the body converter to return your desired object exercises zero HTTP bytes, zero JSON parsing, and zero real status handling.

To test service logic, mock `CatalogGateway`. To test client serialization/transport, use `MockRestServiceServer` or WireMock rather than piling up chained mocks that merely imitate HTTP.

## 21. Contract drift and consumer-driven contract testing

Any system integrating an external API has a **consumer** and a **provider**:

- The consumer relies on specific endpoints, request fields, headers, and response schemas.
- The provider implements the service API and evolves independently.
- WireMock stubs express **the consumer's expectations**.
- A contract verifier like Pact or Spring Cloud Contract tests whether the real provider actually meets those expectations, depending on tooling and workflow.

Without provider verification, both sides can stay green in their own test suites and still fail together upon deployment.

### 21.1. A sound contract workflow

1. The consumer defines key interactions: method/path/query/header/body/status/schema.
2. Consumer tests exercise the real client implementation against an HTTP stub.
3. Contract artifacts are versioned and published when using a contract framework.
4. Provider CI verifies contracts against provider code or a canonical sandbox.
5. Promote/merge deployments only with passing compatibility proof.
6. Whenever the provider alters a contract, review and update consumer tests/stubs alongside the provider verifier.

**Note:** hand-written `stubFor(...).willReturn(...)` calls **do not magically become provider-verified Pact contracts**. Separate contract tooling/processes are needed.

### 21.2. Catching stub drift with OpenAPI/schemas

If an API publishes an OpenAPI spec, validate synthetic WireMock responses and request definitions against that schema. Still, schema validation does not prove provider latency, auth behavior, or business side effects. Keep data contracts, protocol behavior, and runtime reliability distinct.

### 21.3. Contract vs. E2E

Testing a consumer against WireMock is a **consumer integration test**. Testing a consumer against a real provider sandbox proves partial provider compatibility. A production-like E2E test involves all relevant real components within scope; never label every HTTP test "E2E."

## 22. Stateful scenarios: when stubs must reflect request sequences

A fake server can vary responses by state:

1. First GET returns 503.
2. Second GET returns 200.
3. Client retries successfully per policy.
4. WireMock verifies **2 attempts**.

WireMock supports stateful scenarios transitioning from `STARTED` to subsequent states. However, our runnable sample defines no retry—so there is no reason to construct a scenario pretending the client retries.

When implementing retries:

- Define retry policy by status/exception and idempotency.
- Match requests strictly by path/query/body.
- Reset scenario state before each test method.
- Assert attempt counts, outcomes, and bounded backoff.
- Never write tests depending on method execution order.
- For async clients, use bounded awaits/polling instead of infinite sleeps.

### 22.1. Idempotency on POST

A create/payment POST may succeed on the server while the response drops in transit. A client retrying without an idempotency key can trigger the side effect twice. HTTP stubs can simulate "connection dropped after accept" to a degree, yet **only the real provider** proves business idempotency works.

Testing retries must evaluate HTTP method, idempotency keys, duplicate detection, and side effects together.

## 23. Record/playback and the risk of bad fixtures

WireMock supports proxying/recording live traffic to generate stub mappings. While handy for exploring an API, it carries risks:

- Recorded responses capture PII, API keys, cookies, and tokens.
- Dynamic IDs and timestamps make tests brittle.
- Provider contracts evolve after the snapshot.
- Recorded traffic rarely covers 429/500/timeouts.
- Sampled traffic misses edge cases.
- Recording production traffic may violate policy unless authorized.

Safe workflow: record from a valid sandbox, scrub sensitive fields, make fixtures deterministic, review contracts, and verify continuously against the provider. Never commit raw HTTP captures containing secrets.

## 24. When to run the stub server in a separate container?

In-JVM WireMock handles most HTTP client contract tests. A separate process/container fake server helps when:

- The app under test itself runs inside Docker/Kubernetes.
- The consumer is non-Java or lives in another process.
- You need to test DNS/service discovery and container network routing.
- CI runs sidecars or Docker Compose.
- Multiple client tech stacks share one fake server.

In those setups, the fake server URL is not `localhost` inside the app container; use network aliases/host mappings properly. The port WireMock binds inside the container differs from the host-mapped port—never hardcode the wrong one.

**Even inside Docker, it remains a fake HTTP service**—it does not become a real provider. Testcontainers can manage a WireMock container, yet the goal is still testing consumer protocol behavior against a stub.

## 25. Test isolation: preventing port, state, and parallel flakiness

A test suite can fail due to the fake server setup itself:

- Fixed port 8080 colliding with a local dev server.
- Leftover stubs from an earlier test matching the wrong scenario.
- Recorded request counts never reset.
- Parallel tests calling `resetAll()` on a shared `WireMockServer`.
- Server stopping before an async client finishes its request.
- Spring TestContext cache pointing to a stopped fake server.
- Shared static `RestClient` holding another server's base URL.
- Request/response timeouts set too tight for CI CPU load.
- Overly broad URL matchers returning 200 for wrong endpoints.
- Uncontrolled hardcoded IDs/clocks/random values.

Remediation checklist:

1. Use random ports and fetch the base URL after `server.start()`.
2. Give each test class its own server or clean lifecycle isolation.
3. Reset stubs, requests, and scenarios before every method.
4. Never enable parallel execution over shared mutable server state without synchronization/isolation.
5. Keep fixtures short, synthetic, and cover both positive and negative examples.
6. Match request method, path, query, and headers per the real contract.
7. For async/retry flows, await with bounded timeouts.
8. Shut down server/client resources cleanly.
9. Never embed production-specific URLs in WireMock stubs.
10. When using Spring context caching, synchronize fake server and context lifetimes.

## 26. Common errors and how to diagnose them

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Mockito green, HTTP test fails with 404 | Wrong URL/path/query or unmatched stub | Verify recorded HTTP request and stub |
| `Connection refused` | WireMock not started, wrong base URL/port | Start before client; use dynamic port |
| `RestClientResponseException` 4xx | Provider/stub rejected request | Inspect status/headers and request |
| `HttpClientErrorException.NotFound` | Real stubbed 404 vs. unmatched WireMock stub | Check request journal to tell them apart |
| 200 yet JSON decoding fails | Wrong body/`Content-Type`/DTO mapping | Assert response schema and converters |
| 204 causes client NPE | Client assumed body always exists | Handle null/empty responses explicitly |
| 429 does not retry | No retry policy configured | Define explicit retry policy and check idempotency |
| Flaky delay test | Timeout and delay too close | Use bounded timeouts and separate fault tests |
| Auth header test passes, sandbox returns 401 | Fake only checks header presence | Run dedicated provider auth tests |
| `NoSuchBeanDefinitionException RestClient.Builder` | Boot auto-config not loaded/scanned as expected | Check app context, Boot version, slice config |
| `Could not resolve placeholder catalog.base-url` | Property missing or server not started in time | `@DynamicPropertySource` at the right phase |
| Passes alone, fails in suite | Shared WireMock state or context cache | Fix reset/lifecycle/isolation |
| WireMock running yet zero requests arrive | App targets wrong host URL or gateway is mocked | Inspect bean wiring and request journal |
| Passes with non-compliant body | Fixture lacks strict validation | Add schema/DTO contract tests |
| `SSLHandshakeException` on real provider | TLS/CA/hostname mismatch | Test TLS in matching environment; plain HTTP fakes miss it |
| Wrong proxy/redirect behavior | Test request factory differs from production | Use production-like client config and transport tests |
| Consumer stubs pass, provider changed schema | Contract drift | Provider verification/contract pipeline |

### 26.1. Reading errors by layer

**Java mock errors:** Mockito stubbing/matching exceptions unrelated to networking.

**HTTP construction errors:** WireMock fails to match requests or verify flags wrong method/path/query/headers. Inspect the request journal and near misses.

**Transport errors:** connection refused, TLS handshake, read timeouts. Usually carry I/O causes.

**HTTP response errors:** 401/404/429/500 with status codes and headers.

**Codec errors:** JSON body/`Content-Type` incompatible with DTO/message converter.

**Provider contract errors:** consumer assumptions unverified by the live provider despite green WireMock tests.

Trace the exact layer before altering assertions. Never "fix" a WireMock 404 by adding a catch-all 200 stub when the goal is verifying an exact URL.

## 27. Hands-on exercises

### Exercise 1 — Intentionally break the path

Change `HttpCatalogGateway` from `/v1/products` to `/v1/product` in a scratch branch. Mockito service tests stay green because the gateway is mocked. The WireMock 200 test must fail (unmatched stub). Revert.

**Lesson:** Java-layer mocks cannot observe URI paths.

### Exercise 2 — Remove the Accept header

Remove `.accept(MediaType.APPLICATION_JSON)` in the client. The WireMock test asserting `withHeader("Accept", containing("application/json"))` must fail or fail verification. Revert.

### Exercise 3 — Query parameters with spaces

Run `uriBuilderEncodesSpacesInQueryParameter`, then try inputs containing `+`, `&`, and Unicode. Observe how WireMock parses values. Never fix assertions by concatenating raw URL strings.

### Exercise 4 — Explicit 404 vs. unmatched stub 404

Deliberately stub the wrong query key, e.g., `product` instead of `sku`. Compare WireMock's unmatched 404 with an intentionally stubbed 404. Design response markers/unmatched-request checks to tell them apart.

### Exercise 5 — 429 and retries

Add a bounded retry policy on a separate branch: retry 429/503 for idempotent GETs, honor `Retry-After` per contract, and cap attempts and duration. Use WireMock to verify counts without asserting exact milliseconds or retrying infinitely.

### Exercise 6 — 204 No Content

Switch 204 to 200 with an empty body. Does `body(ProductView.class)` return null or throw depending on the message converter? Test real behavior instead of assuming one rule across all HTTP clients.

### Exercise 7 — JSON schema drift

Change stub JSON from `"stock":5` to `"available_qty":5`. Because `ProductView.stock` is a primitive, see whether the test silently reads `0`. Propose strict DTO validation/`@JsonProperty` or an API contract verifier.

### Exercise 8 — Spring Boot bean wiring

Remove `@DynamicPropertySource` from `CatalogWiringSpringTest`. Context startup must fail for missing `catalog.base-url` (or hit the wrong endpoint if a default exists). Fix using the fake server's property—never hardcode a production URL.

### Exercise 9 — REST client slice

Create a `@RestClientTest` with `MockRestServiceServer` for the same `HttpCatalogGateway` and test GET/JSON. Compare it with WireMock on speed, scope, and ability to simulate socket read timeouts.

### Exercise 10 — WebClient vs. RestClient

Swap the implementation to `WebClient` in a scratch branch and use `StepVerifier` (or `block` strictly inside tests outside the event loop). Use the same WireMock server to verify HTTP requests. Never claim a Mockito mock returning `Mono.just(...)` tested Reactor Netty transport.

### Exercise 11 — POST idempotency

Design an order-creation endpoint with `Idempotency-Key`, using WireMock to simulate 503/timeouts and retries. Explain why only the real provider proves duplicate prevention; the fake only proves the client sends the key and retries properly.

### Exercise 12 — Contract verification

Capture request/response examples from WireMock tests into a versioned contract artifact. Run provider verification against a sandbox API or real provider code. Summarize what the stub verified vs. what the provider verified.

## 28. Review checklist before marking QA PASS

- [ ] Clear whether each test mocks a **Java method**, an **HTTP request factory**, or an **HTTP server**.
- [ ] Mockito tests assert only business logic using fake outputs.
- [ ] Client implementations have dedicated tests for URL/method/query/headers/body/status.
- [ ] When network behavior matters, use WireMock/MockWebServer over real sockets.
- [ ] Explicitly recognizes `MockRestServiceServer` opens no TCP listener.
- [ ] Uses HTTP client configuration close to production for critical tests.
- [ ] Fake servers bind random ports; clients read base URLs after `start()`.
- [ ] Resets WireMock stubs, request journals, and scenarios per test lifecycle.
- [ ] Never replaces the client/gateway with `@MockBean`/`@MockitoBean` inside outbound HTTP tests.
- [ ] Assertions verify both response mapping **and** request expectations.
- [ ] Tests cover the happy path plus key 404/429/500 statuses.
- [ ] Includes 204/malformed JSON tests where contracts require them.
- [ ] Query/path encoding tested with special-character inputs.
- [ ] Never treats an unmatched stub 404 as provider not-found without checking the request journal.
- [ ] When retries exist, asserts attempts, idempotency, and bounded timeouts.
- [ ] Timeout tests distinguish transport failures from HTTP error responses.
- [ ] Never treats fake header matching as provider authentication validation.
- [ ] Never treats valid stub JSON as proof of the live provider's schema.
- [ ] Maintains contract/provider verification when external services evolve independently.
- [ ] Never calls consumer fake-server tests "E2E with the real provider."
- [ ] Never logs tokens/cookies/PII or records production traffic into un-scrubbed fixtures.
- [ ] Aligns context caching and fake-server lifecycles in large suites.
- [ ] Zero dependence on fixed ports, test order, wall-clock timing, or shared mutable stubs.
- [ ] Recognizes uncovered limits: TLS, DNS, HTTP/2, proxies, and managed infrastructure.
- [ ] Accurately reports tests executed vs. skipped and which components were mocked.

## 29. Final selection rule

```text
What do you need to prove?
      |
      +-- Domain rule when collaborator returns X / throws Y?
      |     -> Mockito at the CatalogGateway interface.
      |
      +-- RestClient builds the right URI/headers/JSON/status?
      |     -> @RestClientTest + MockRestServiceServer,
      |        no server socket needed.
      |
      +-- Real HTTP client over TCP, request journal,
      |   response delays/faults?
      |     -> WireMock or MockWebServer.
      |
      +-- Spring Boot config wires client to the right
      |   fake provider via properties/DI?
      |     -> @SpringBootTest + @DynamicPropertySource
      |        + WireMock (clear lifecycle).
      |
      +-- Live provider still satisfies schema/status?
      |     -> Consumer-driven contracts + provider verification,
      |        or managed sandbox tests.
      |
      +-- TLS/auth/ingress/failover/real business side effects?
            -> Staging/deployment/integration with matching
               infrastructure and real services.
```

**Core message:** Java-layer mocks are excellent for isolating and testing business decisions, yet **they never execute HTTP client implementations**. HTTP stub servers verify that the client sends requests over network sockets and handles statuses, headers, URIs, and JSON/transport under controlled conditions. Because fake servers still return test-defined answers, however, they **cannot prove the live provider's contract**. A strong strategy pairs fast unit tests, HTTP-stub client tests, provider contract verification, and targeted infrastructure/deployment tests aligned with risk—rather than treating every "mock" as equal evidence.

## 30. Official references and further reading

- Spring Framework — Testing client applications, comparing HTTP mock servers with `MockRestServiceServer`: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html
- Spring Framework 6.1 — `RestClient` and HTTP response handling: https://docs.spring.io/spring-framework/reference/6.1/integration/rest-clients.html
- Spring Boot 3.3 — Testing applications, `@RestClientTest`, and `MockRestServiceServer`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Auto-configured REST clients: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- Spring Framework — `@DynamicPropertySource`: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- WireMock — Download and installation: https://wiremock.org/docs/download-and-installation/
- WireMock — Stubbing: https://wiremock.org/docs/stubbing/
- WireMock — Request matching: https://wiremock.org/docs/request-matching/
- WireMock — Verifying requests: https://wiremock.org/docs/verifying/
- WireMock — Java configuration/random ports: https://wiremock.org/docs/configuration/
- WireMock — JUnit Jupiter extension: https://wiremock.org/docs/junit-jupiter/
- WireMock — Simulating faults: https://wiremock.org/docs/simulating-faults/
- WireMock — Stateful scenarios: https://wiremock.org/docs/stateful-behaviour/
- Maven Central — `org.wiremock:wiremock-standalone:3.9.1`: https://central.sonatype.com/artifact/org.wiremock/wiremock-standalone/3.9.1
- Mockito — Documentation: https://site.mockito.org/
- Spring Cloud Contract — Consumer-driven contracts: https://docs.spring.io/spring-cloud-contract/reference/
- Pact — Consumer driven contract testing: https://docs.pact.io/
- JUnit Jupiter — User guide: https://docs.junit.org/current/user-guide/
