# HTTP Stub Servers for WebClient and Transport-Verified HTTP Clients

## Lesson objectives

When a Spring Boot application calls a partner's REST API using `WebClient`, there are at least two distinct questions to answer:

1. **Is the client's logic right?** For instance: which exception a `404` status maps to, how JSON data decodes into a DTO, and whether retries happen.
2. **Is the real HTTP request right?** For instance: does the client send the right `GET/POST`, path, query parameters, headers, JSON body, content type, authorization, TLS, timeouts, and encoding over an actual HTTP connection?

Mocking a Java interface or `ExchangeFunction` can return arbitrary `ClientResponse` objects **without ever creating a TCP connection, serializing a real HTTP request, or exercising the HTTP codecs/runtime configured for production**. When the contract must cover **transport**, an **HTTP stub server** listening on loopback with a dynamic port—such as **WireMock** or **OkHttp MockWebServer**—is the better fit.

This lesson is part of the **HTTP Client and Mocking** group in the **Spring Boot – testing** module, focusing on **HTTP stub servers for WebClient and transport-verified clients**. The focus is testing outbound HTTP clients, not server-side controller/inbound endpoints.

After this lesson, you will be able to:

- Distinguish collaborator mocks, fake `ExchangeFunction`, HTTP stub servers, and real sandbox APIs.
- Use WireMock 3 to run an HTTP server on a **random port** to avoid CI conflicts.
- Use real `WebClient` and `ClientHttpConnector` to issue genuine HTTP requests to the stub.
- Verify HTTP method, path, URI encoding, query parameters, headers, media types, and JSON serialization/deserialization.
- Stub and verify `2xx`, `404`, `503`, `204 No Content`, slow responses, and the difference between **HTTP errors** and **transport errors**.
- Use Reactor's `StepVerifier` to test asynchronous `Mono`s without arbitrary `Thread.sleep` calls.
- Choose between a **plain JUnit integration test** and a **`@SpringBootTest`** when verifying the application's `WebClient.Builder` configuration.
- Configure dynamic base URLs, manage lifecycle/reset, prevent request journal leakage, and avoid hitting real APIs.
- Read WireMock "unmatched request" errors to catch request encoding or header mismatches.
- Understand stub server limitations around DNS, TLS truststores, HTTP/2, reverse proxies, connection pooling, backpressure, and production network faults.
- Run the complete example using **Java 17, Spring Boot 3.3.5, Gradle, WebFlux/WebClient, WireMock 3.9.2, JUnit Jupiter, and Reactor Test**.

**Rule:** If the bug you need to catch can only happen when **HTTP bytes cross a socket** (URI encoding, actual request headers, client runtime timeouts, connection resets, etc.), do not rely solely on a mock returning `Mono.just(...)`. Let the real client call a stub HTTP server and verify both the **outbound request** and the **inbound response**.

## 1. What is an HTTP stub server?

An HTTP stub server is a **test-controlled HTTP service** listening on a local address/port that returns responses based on declared matching rules. With WireMock, a test can:

1. Register a request matcher: `GET /api/v1/products/BK-001?include=stock`.
2. Define a response: status `200`, header `Content-Type: application/json`, JSON body.
3. Execute real client code, e.g., `partnerGateway.getProduct("BK-001")`.
4. Inspect the request journal: how many times did the server receive a request with the expected method, URL, headers, and body?
5. Register different faults—such as `503`, `404`, delays, or connection faults—and verify how the client responds.

Architecture:

~~~text
JUnit Jupiter test
   |
   |   calls SUT (PartnerGateway)
   v
Spring WebClient
   |
   |  ClientHttpConnector / Reactor Netty
   |  HTTP on localhost + dynamic port
   v
WireMock HTTP stub server
   |
   +-- match GET/POST/path/query/header/body
   +-- response 200/204/404/503 + JSON
   +-- optional delay/connection fault
   +-- record request journal for verification
   |
   v
WebClient response decoding/status mapping
   |
   v
Mono<Product> / Mono<ReserveReceipt> / error
   |
   v
StepVerifier + WireMock.verify(...)
~~~

Key takeaway: **a stub server is not the production server**. Tests need no internet access or real credentials. At the same time, it lets the **exact same client runtime** execute requests over HTTP instead of handing Java objects straight back to the service.

### What is genuinely tested?

- `WebClient` sends requests through a real HTTP connector.
- `UriBuilder` constructs proper paths/queries and encodes supplied values.
- Final headers actually put on the wire (per WireMock's journal).
- Jackson or HTTP message codecs convert Java records to JSON and back.
- Status code handling via `retrieve()`/`onStatus`.
- Response timeouts, cancellation, and HTTP-level errors in a controlled local environment.

### What is not guaranteed?

- That the external server actually runs the latest business protocol/schema.
- DNS, TLS certificates, CDNs, gateways, load balancers, proxies, or production authentication.
- Internet latency, packet loss, or flaky connections across a real WAN.
- HTTP/2 negotiation or TLS handshakes if the stub only serves **unencrypted HTTP/1.1**.
- Cross-team contract compatibility unless stub mappings stay synced with OpenAPI/Pact/provider tests.
- Retry/backoff/connection pool behavior under heavy load unless dedicated tests exercise them.

A stub server is **an intermediate testing layer** between pure unit tests and end-to-end tests against external systems.

## 2. When to mock WebClient vs. when a real server is needed?

| Goal | Suitable test approach | Defect-detection power |
| --- | --- | --- |
| Pure Java mapping, formatting a message | Plain unit test without Spring | Java logic |
| Service with collaborator `PartnerGateway` | Mockito mock of interface/collaborator | Service branching logic |
| Only simulating `ClientResponse` | Fake `ExchangeFunction` | Reactor handling and client logic, no sockets |
| Need exact URL, headers, HTTP method, JSON bytes | **WireMock/MockWebServer + real WebClient** | HTTP request/response on local transport path |
| Need to know how Spring Boot configures `WebClient.Builder` | `@SpringBootTest` + HTTP stub | Wiring, properties, codecs, filters/customizers |
| Need real outbound TLS/mTLS verification | HTTPS stub + test-only trust/key material | TLS handshake/certificate/client config |
| Need to verify provider contract | Consumer-driven contract test or provider sandbox | Compatibility with the real API |
| Need full end-to-end flow from UI to third party | End-to-end test with dedicated infrastructure | Connected systems; higher cost/flakiness |

**Anti-pattern 1:** Mocking `PartnerGateway` and claiming you proved `WebClient sends the right Authorization header`. When the service executes no real HTTP code, that claim has zero evidence.

**Anti-pattern 2:** Unit tests directly mocking the `webClient.get().uri(...).retrieve().bodyToMono(...)` call chain. Chain mocks break easily on refactors and can pass even when real URI encoding or headers are wrong.

**Anti-pattern 3:** Using `@WebFluxTest` to test an outbound client without actually exercising the client/network path. `@WebFluxTest` focuses on **WebFlux controllers**; `WebTestClient` typically tests **inbound web handlers**. It does not replace an HTTP stub server for a `WebClient` calling an external partner.

## 3. Two popular HTTP test doubles

### 3.1. WireMock

WireMock offers:

- An in-process or standalone HTTP server.
- Request matching by method/path/query/headers/cookies/body.
- Response stubbing for JSON, statuses, headers, fixed delays, and faults.
- A request journal and `verify` for invocation counts.
- Stateful scenarios, record/playback, and proxying.
- A JUnit Jupiter extension or manual `WireMockServer` start/stop.

This lesson chooses **WireMock 3.9.2** for the runnable example because its Java API is stable and provides clear request matching and verification. No Docker is required to run WireMock as an in-process Java server.

### 3.2. OkHttp MockWebServer

`MockWebServer` accepts real HTTP requests, lets you **enqueue** `MockResponse` objects, and inspect `RecordedRequest`. It is concise for linear tests (one request → one response) or socket policies. When matching many complex endpoints/headers, the WireMock DSL is often more convenient.

Architectural sketch (not a runnable class):

~~~java
MockWebServer server = new MockWebServer();
server.start();

server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setBody("{\"ok\":true}")
        .addHeader("Content-Type", "application/json"));

WebClient client = WebClient.builder()
        .baseUrl(server.url("/").toString())
        .build();

// ... call client, inspect RecordedRequest ...

server.shutdown();
~~~

This is a snippet requiring the `okhttp3.mockwebserver` dependency/imports and subscription code. Even with MockWebServer, still inspect the actual request rather than verifying only Java DTOs.

### Why do dynamic ports matter?

Configuring WireMock on fixed port `8080` easily collides with a running app or another CI job. Use:

~~~java
new WireMockServer(wireMockConfig().dynamicPort());
~~~

After `server.start()`, call `server.baseUrl()` to obtain the real URL. If using the JUnit extension, use `wireMockExtension.port()` or runtime info. **Never point the client at `http://localhost:8080`** when the server selected a dynamic port.

## 4. WebClient and runtime transport

`WebClient` belongs to Spring WebFlux. When `spring-boot-starter-webflux` is present, Spring Boot typically auto-configures a `WebClient.Builder` customized with HTTP codecs, observability, SSL bundles, or the client connector suited to the classpath.

Application component example:

~~~java
@Service
class PartnerService {
    private final WebClient webClient;

    PartnerService(WebClient.Builder builder,
                   @Value("${partner.base-url}") String baseUrl) {
        this.webClient = builder.baseUrl(baseUrl).build();
    }
}
~~~

This is an architectural snippet; the full project is in section 6. The builder typically uses Reactor Netty when the WebFlux starter brings Reactor Netty onto the classpath. **Never assume every `WebClient` uses Reactor Netty**: an application may pick JDK HTTP, Jetty, or a custom `ClientHttpConnector`. Final proof must come from your actual classpath/configuration and matching transport tests.

### Configure via Builder or `WebClient.create`?

- **Inject Spring Boot's `WebClient.Builder`**: preserves production wiring such as filters/customizers, codecs, and Boot-configured HTTP connectors.
- **`WebClient.builder()` in plain JUnit**: sufficient to test request/response logic and default classpath HTTP transport, though it does not verify app-specific Boot customizations.
- **`WebClient.create(baseUrl)`**: simple, yet omits `WebClientCustomizer` beans that Boot only applies to the injected builder.

Hence the example has **two tiers**: a plain JUnit test executing real HTTP, and a full-context Spring Boot test confirming the injectable `WebClient.Builder` also reaches the stub server.

### HTTP transport errors differ from HTTP status errors

Distinguish clearly:

- **HTTP status error:** The server actually sent a response, e.g., `404` or `503`. With default `retrieve()`, `WebClient` creates `WebClientResponseException` for 4xx/5xx unless customized with `onStatus`.
- **Network/transport error:** DNS failure, connection refused/reset, SSL handshake failure, read timeout, or connection pool acquisition failure. There is not necessarily an HTTP status because no complete response arrived. Errors usually surface as `WebClientRequestException` with nested causes, though exact exception chains vary by connector.
- **Publisher timeout:** `mono.timeout(Duration...)` emits `TimeoutException` when no signal arrives in time; this is a Reactor operator timeout, not synonymous with a socket-level read timeout.
- **Decode error:** HTTP 200 with JSON incompatible with the DTO; raises a decoding exception rather than an HTTP status error.

Tests must simulate **the right kind of failure** to protect the corresponding error-handling code.

## 5. Designing counter-example HTTP fixtures

Stubbing an arbitrary response and checking that `Mono` emits an object is often not enough. A good fixture suite catches:

| Request/response attribute | Case to build | Bug caught |
| --- | --- | --- |
| Method | GET to read product; POST to create reservation | Client sends wrong method |
| Path | `/api/v1/products/BK-001` | Client drops version or uses wrong SKU |
| Query | `include=stock` | Client omits param |
| Query encoding | `q=Java & Spring` | `&` splits into an extra parameter |
| Default header | `X-Client-Name: shop-backend` | Filter/builder not applied |
| Accept | `application/json` | Client fails to declare desired format |
| Content-Type | POST `application/json` | DTO sent with wrong media type |
| JSON body | `sku=BK-001`, `quantity=2` | Serializer/misspelled field/quantity |
| Correlation ID | `X-Request-Id: req-007` | Client omits trace/business request ID |
| 200 | Valid Product DTO | Response mapping |
| 404 | Missing product | Business error mapping |
| 503 | Provider unavailable | Proper HTTP error propagation |
| 204 | Empty body | Handling empty completion rather than assuming DTO |
| Delay | Noticeably slow server | Timeout and cancellation policy |
| Request count | Exactly one request | Catches duplicate calls/unwanted retries |

**Independent expected values:** Never generate expected JSON using the same serializer under test and compare against it, because both can share the same bug. Write literal JSON fixtures derived from the API contract.

**Do not assert only `verify(1, getRequestedFor(...))` while skipping response mapping.** When body decoding fails, the request may still look fine. Verify **both directions**.

## 6. Runnable project architecture

The project uses **Java 17 + Spring Boot 3.3.5 + Gradle + JUnit 5 + WireMock 3.9.2**. No Docker or real partner API is needed.

- **`PartnerGateway`** is the production adapter holding `WebClient`.
- `getProduct` issues GET with path variable, query `include=stock`, Accept header, and custom 404 handling.
- `searchOne` tests query parameters containing spaces and `&`.
- `reserve` issues POST, serializing a JSON body alongside `X-Request-Id`.
- `PartnerGatewayTransportTest` starts/stops a WireMock server **per test method**, constructs the gateway with a real `WebClient`, and verifies requests and responses.
- `PartnerGatewayBootWiringTest` boots a full Spring Boot context, supplies `partner.base-url` via `@DynamicPropertySource`, injects **Boot's `WebClient.Builder`** via the service, and verifies real outbound traffic.
- Tests simulate **404, 503, 204, slow responses**, with zero requests to the internet.

### 6.1. Directory tree

~~~text
webclient-transport-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/transport/
    │   ├── TransportDemoApplication.java
    │   └── PartnerGateway.java
    └── test/java/com/example/transport/
        ├── PartnerGatewayTransportTest.java
        └── PartnerGatewayBootWiringTest.java
~~~

Wrapper scripts/JAR must be generated from a compatible Gradle installation or copied from an existing project; `gradle-wrapper.jar` is a binary and cannot be created by copying Markdown.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'webclient-transport-lab'
~~~

### 6.3. `build.gradle`

~~~groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.wiremock:wiremock-standalone:3.9.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Why are these dependencies sufficient for the example?**

- `spring-boot-starter-webflux`: `WebClient`, Reactor, JSON codecs via Jackson, and the default Reactor Netty HTTP connector.
- `spring-boot-starter-test`: Spring TestContext, JUnit Jupiter, assertions, and Spring Boot testing.
- `reactor-test`: `StepVerifier` to verify `Mono` without sleeping or polling.
- `wiremock-standalone:3.9.2`: WireMock Java HTTP server with shaded/bundled dependencies to minimize classpath conflicts.
- `junit-platform-launcher` and `useJUnitPlatform()` for Gradle/JUnit Jupiter support.
- `@WebFluxTest` is unnecessary because the target is outbound `WebClient`, not a controller.
- No H2, database, Testcontainers, or Docker needed.

**Version note:** The project pins Boot **3.3.5** and WireMock **3.9.2**; do not mix WireMock 4 beta or Spring Boot 4 imports/APIs. In real projects, follow your team's standardized BOM/versions and inspect the dependency tree for Netty/Jackson/SLF4J conflicts.

### 6.4. `TransportDemoApplication.java`

~~~java
package com.example.transport;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TransportDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransportDemoApplication.class, args);
    }
}
~~~

The demo application requires `partner.base-url` to construct `PartnerGateway`. In Spring Boot tests, this value comes from local WireMock. Running `bootRun` without configuring the property fails startup for missing `partner.base-url`, which is safer than silently calling a production URL. The runnable target for this lesson is **`gradlew test`**.

### 6.5. `PartnerGateway.java`: real outbound adapter

~~~java
package com.example.transport;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class PartnerGateway {

    private final WebClient webClient;

    public PartnerGateway(
            WebClient.Builder builder,
            @Value("${partner.base-url}") String baseUrl) {

        this.webClient = builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Client-Name", "shop-backend")
                .build();
    }

    public Mono<Product> getProduct(String sku) {
        return webClient.get()
                .uri(builder -> builder
                        .path("/api/v1/products/{sku}")
                        .queryParam("include", "stock")
                        .build(sku))
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .onStatus(
                        code -> code.value() == 404,
                        response -> response.createException()
                                .map(error ->
                                    new ProductNotFoundException(
                                            sku, error)))
                .bodyToMono(Product.class)
                .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                                "Empty body for product " + sku)));
    }

    public Mono<Product> searchOne(String term) {
        return webClient.get()
                .uri(builder -> builder
                        .path("/api/v1/search")
                        .queryParam("q", "{term}")
                        .build(term))
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(Product.class);
    }

    public Mono<ReserveReceipt> reserve(
            ReserveRequest request, String requestId) {

        return webClient.post()
                .uri("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", requestId)
                .bodyValue(request)
                .retrieve()
                .bodyToMono(ReserveReceipt.class);
    }

    public Mono<Product> getProductWithTimeout(
            String sku, Duration timeout) {

        // This is a Reactor publisher timeout; not
        // Netty's socket read-timeout.
        return getProduct(sku).timeout(timeout);
    }

    public record Product(
            String sku, String title, long priceCents) {
    }

    public record ReserveRequest(
            String sku, int quantity) {
    }

    public record ReserveReceipt(
            String reservationId, String state) {
    }

    public static class ProductNotFoundException
            extends RuntimeException {

        public ProductNotFoundException(
                String sku, Throwable cause) {
            super("Product not found: " + sku, cause);
        }
    }
}
~~~

**Why does this production code suit transport testing?**

1. Uses `WebClient.Builder`, allowing full-context tests to inject the same Boot builder/customizers instead of mocking chains.
2. `baseUrl` is injected via `partner.base-url`, letting tests point the client to the HTTP stub without modifying production logic.
3. `getProduct` uses a path variable **without raw string concatenation** in the URI; the query parameter is added separately.
4. `searchOne` uses `"{term}"` as a URI variable inside the query: spaces and `&` are encoded via `WebClient`'s URI variable handling.
5. `defaultHeader` attaches `X-Client-Name` so tests confirm final request headers.
6. `reserve` serializes `ReserveRequest` to JSON through the real HTTP codec, then deserializes `ReserveReceipt`.
7. `retrieve()` handles 4xx/5xx by default; `404` specifically maps to `ProductNotFoundException` via `onStatus`.
8. `response.createException()` consumes the error body to build the underlying exception before wrapping it, avoiding an unhandled response body.
9. `switchIfEmpty` makes the contract explicit: GET product **forbids an empty body**; 204 does not silently become a `null` product.
10. `getProductWithTimeout` demonstrates a **Reactor publisher timeout** that tests can verify without claiming TCP socket/connect timeouts were configured.

### Why Java records?

Java 17 supports `record`, and Spring Boot-managed Jackson can serialize/deserialize record DTOs in the appropriate context. Monetary amounts use `priceCents: long` to avoid floating-point errors in this transport lesson. Real business code should verify currency, precision, and validation separately.

## 7. Testing HTTP transport with WireMockServer and JUnit Jupiter

**`src/test/java/com/example/transport/PartnerGatewayTransportTest.java`**

~~~java
package com.example.transport;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.test.StepVerifier;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PartnerGatewayTransportTest {

    private WireMockServer server;
    private PartnerGateway gateway;

    @BeforeEach
    void startServerAndCreateRealClient() {
        server = new WireMockServer(
                wireMockConfig().dynamicPort());
        server.start();

        // Do not mock ExchangeFunction: WebClient calls over HTTP.
        gateway = new PartnerGateway(
                WebClient.builder(), server.baseUrl());
    }

    @AfterEach
    void stopServer() {
        if (server != null && server.isRunning()) {
            server.stop();
        }
    }

    @Test
    void getSendsCorrectMethodPathQueryAndHeaders() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/BK-001"))
                .withQueryParam("include", equalTo("stock"))
                .withHeader("X-Client-Name",
                        equalTo("shop-backend"))
                .withHeader("Accept",
                        containing("application/json"))
                .willReturn(okJson(
                    "{\"sku\":\"BK-001\","
                    + "\"title\":\"Java Basics\","
                    + "\"priceCents\":2500}")));

        StepVerifier.create(gateway.getProduct("BK-001"))
                .assertNext(product -> {
                    assertEquals("BK-001", product.sku());
                    assertEquals("Java Basics", product.title());
                    assertEquals(2500L, product.priceCents());
                })
                .verifyComplete();

        server.verify(1, getRequestedFor(
                    urlPathEqualTo("/api/v1/products/BK-001"))
                .withQueryParam("include", equalTo("stock"))
                .withHeader("X-Client-Name",
                        equalTo("shop-backend"))
                .withHeader("Accept",
                        containing("application/json")));
    }

    @Test
    void queryParameterIsEncodedAndNotSplitByAmpersand() {
        server.stubFor(get(urlPathEqualTo("/api/v1/search"))
                .withQueryParam("q",
                        equalTo("Java & Spring"))
                .willReturn(okJson(
                    "{\"sku\":\"BK-010\","
                    + "\"title\":\"Java & Spring\","
                    + "\"priceCents\":4100}")));

        StepVerifier.create(
                    gateway.searchOne("Java & Spring"))
                .assertNext(result -> {
                    assertEquals("BK-010", result.sku());
                    assertEquals("Java & Spring",
                            result.title());
                })
                .verifyComplete();

        server.verify(1, getRequestedFor(
                    urlPathEqualTo("/api/v1/search"))
                .withQueryParam("q",
                        equalTo("Java & Spring")));
    }

    @Test
    void postSerializesJsonAndCorrelationHeader() {
        server.stubFor(post(
                    urlEqualTo("/api/v1/reservations"))
                .withHeader("Content-Type",
                        containing("application/json"))
                .withHeader("X-Request-Id",
                        equalTo("req-007"))
                .withRequestBody(equalToJson(
                    "{\"sku\":\"BK-001\",\"quantity\":2}"))
                .willReturn(okJson(
                    "{\"reservationId\":\"RES-9\","
                    + "\"state\":\"ACCEPTED\"}")));

        StepVerifier.create(
                    gateway.reserve(
                        new PartnerGateway.ReserveRequest(
                                "BK-001", 2),
                        "req-007"))
                .assertNext(result -> {
                    assertEquals("RES-9",
                            result.reservationId());
                    assertEquals("ACCEPTED", result.state());
                })
                .verifyComplete();

        server.verify(1, postRequestedFor(
                    urlEqualTo("/api/v1/reservations"))
                .withHeader("Content-Type",
                        containing("application/json"))
                .withHeader("X-Request-Id",
                        equalTo("req-007"))
                .withRequestBody(equalToJson(
                    "{\"sku\":\"BK-001\",\"quantity\":2}")));
    }

    @Test
    void notFoundMapsHttp404ToDomainError() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/MISSING"))
                .willReturn(aResponse()
                    .withStatus(404)
                    .withHeader("Content-Type",
                            "application/json")
                    .withBody("{\"code\":\"NOT_FOUND\"}")));

        StepVerifier.create(gateway.getProduct("MISSING"))
                .expectErrorSatisfies(error -> {
                    assertInstanceOf(
                        PartnerGateway.ProductNotFoundException.class,
                        error);
                    assertEquals(
                        "Product not found: MISSING",
                        error.getMessage());
                })
                .verify();

        server.verify(1, getRequestedFor(
                urlPathEqualTo("/api/v1/products/MISSING")));
    }

    @Test
    void serviceUnavailableRetainsHttpStatus() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/DOWN"))
                .willReturn(aResponse()
                    .withStatus(503)
                    .withHeader("Content-Type",
                            "application/json")
                    .withBody("{\"error\":\"unavailable\"}")));

        StepVerifier.create(gateway.getProduct("DOWN"))
                .expectErrorSatisfies(error -> {
                    WebClientResponseException ex =
                        assertInstanceOf(
                            WebClientResponseException.class,
                            error);
                    assertEquals(503,
                            ex.getStatusCode().value());
                    assertTrue(ex.getResponseBodyAsString()
                            .contains("unavailable"));
                })
                .verify();
    }

    @Test
    void noContentDoesNotBecomeFakeProduct() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/EMPTY"))
                .willReturn(aResponse().withStatus(204)));

        StepVerifier.create(gateway.getProduct("EMPTY"))
                .expectErrorSatisfies(error -> {
                    IllegalStateException ex =
                        assertInstanceOf(
                            IllegalStateException.class,
                            error);
                    assertEquals(
                        "Empty body for product EMPTY",
                        ex.getMessage());
                })
                .verify();
    }

    @Test
    void slowResponseCausesReactivePublisherTimeout() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/SLOW"))
                .willReturn(aResponse()
                    .withStatus(200)
                    .withHeader("Content-Type",
                            "application/json")
                    .withFixedDelay(1500)
                    .withBody(
                        "{\"sku\":\"SLOW\","
                        + "\"title\":\"Slow\","
                        + "\"priceCents\":1}")));

        StepVerifier.create(
                    gateway.getProductWithTimeout(
                            "SLOW", Duration.ofMillis(250)))
                .expectError(TimeoutException.class)
                .verify(Duration.ofSeconds(5));

        // Do not assert a JSON response: timeout
        // terminated the reactive pipeline before body arrival.
    }

    @Test
    void monoIsColdAndSendsNoRequestBeforeSubscription() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/COLD"))
                .willReturn(okJson(
                    "{\"sku\":\"COLD\","
                    + "\"title\":\"Cold Mono\","
                    + "\"priceCents\":99}")));

        var result = gateway.getProduct("COLD");

        // Mono built only, not subscribed yet -> no HTTP sent.
        server.verify(0, getRequestedFor(
                urlPathEqualTo("/api/v1/products/COLD")));

        StepVerifier.create(result)
                .assertNext(value ->
                    assertEquals("COLD", value.sku()))
                .verifyComplete();

        server.verify(1, getRequestedFor(
                urlPathEqualTo("/api/v1/products/COLD")));
    }
}
~~~

### Why does this test suite actually verify transport?

**`WireMockServer` uses a dynamic port and real HTTP sockets.** `server.start()` runs before the client constructs its base URL; `server.baseUrl()` yields the live endpoint. No JDK interface mock replaces `WebClient` or `ClientHttpConnector`.

**Server-side WireMock matchers** see the request *after* URI encoding, HTTP header formatting, and serialization. For instance, if the client accidentally concatenates `"?q=Java & Spring"` without encoding, `withQueryParam("q", equalTo("Java & Spring"))` will fail to match even though the Java string looks fine on the client side.

**`equalToJson`** compares JSON content structurally. It does not require identical key order by default, since JSON object key ordering is normally not part of an API contract. When strict fields are required, the default matcher does not loosely ignore unexpected fields by accident.

**`StepVerifier`** verifies the publisher emits the expected signal value or error. Avoid using `block()` or arbitrary `Thread.sleep(...)` calls in every test.

**Request counts** are verified on the server. A bug causing the client to send two requests in one test is caught by `verify(1, ...)`, even if both requests return the same DTO.

**HTTP statuses/errors** originate from the stub server and pass through `WebClient.retrieve()` and real reactive handling. Never construct `WebClientResponseException` by hand just to force a test green.

### About the timeout test

- The stub holds the response for **1,500 ms**.
- The client pipeline sets `Mono.timeout(250 ms)`.
- The test waits up to 5 seconds for verification.
- Expected error is `java.util.concurrent.TimeoutException` from the **Reactor timeout operator**.
- This **does not prove** that Netty's `responseTimeout` or TCP connect timeout is configured.
- An overloaded CI runner can add timing jitter; if the test flakes, widen the margin between timeout and delay or use virtual time for pure time-based logic. Never use `VirtualTimeScheduler` to claim you tested real socket timeouts.

### Why reset the server per method?

`@BeforeEach` creates a fresh server and `@AfterEach` stops it. Because each test owns its own request journal and stubs, an earlier test can never leave mappings behind for a later test to hit accidentally. The trade-off is higher startup cost per method. For large suites, you can start one class-scoped server and call `resetAll()` before each test, provided parallel test methods are managed properly.

## 8. Verifying Spring Boot wiring: injected `WebClient.Builder` must also hit the stub

Plain JUnit tests exercise `WebClient.builder()`, yet do not prove **Spring Boot's `WebClient.Builder`** is injected into the `@Service` and receives the base URL properly from application properties.

To verify wiring, add a `@SpringBootTest` class using the same production `PartnerGateway`. WireMock starts **before Spring resolves dynamic properties**, and the context is evicted after the class to avoid reusing a DataSource/HTTP client pointing at a stopped server.

**`src/test/java/com/example/transport/PartnerGatewayBootWiringTest.java`**

~~~java
package com.example.transport;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import reactor.test.StepVerifier;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    classes = TransportDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PartnerGatewayBootWiringTest {

    // Intentionally started before Spring creates ApplicationContext.
    // Only this class uses this URL; context is evicted after class.
    private static final WireMockServer SERVER =
            startServer();

    private static WireMockServer startServer() {
        WireMockServer server = new WireMockServer(
                wireMockConfig().dynamicPort());
        server.start();
        return server;
    }

    @DynamicPropertySource
    static void registerPartnerUrl(
            DynamicPropertyRegistry registry) {
        registry.add("partner.base-url",
                SERVER::baseUrl);
    }

    @Autowired
    private PartnerGateway gateway;

    @BeforeEach
    void resetStubMappingsAndRequestJournal() {
        SERVER.resetAll();
    }

    @AfterAll
    static void stopStub() {
        SERVER.stop();
    }

    @Test
    void bootConfiguredClientCallsLocalStub() {
        SERVER.stubFor(get(
                    urlPathEqualTo("/api/v1/products/BOOT-1"))
                .withHeader("X-Client-Name",
                        equalTo("shop-backend"))
                .withQueryParam("include",
                        equalTo("stock"))
                .willReturn(okJson(
                    "{\"sku\":\"BOOT-1\","
                    + "\"title\":\"Spring Boot\","
                    + "\"priceCents\":7000}")));

        StepVerifier.create(gateway.getProduct("BOOT-1"))
                .assertNext(value -> {
                    assertEquals("BOOT-1", value.sku());
                    assertEquals(7000L, value.priceCents());
                })
                .verifyComplete();

        SERVER.verify(1, getRequestedFor(
                    urlPathEqualTo("/api/v1/products/BOOT-1"))
                .withQueryParam("include",
                        equalTo("stock")));
    }

    @Test
    void bootConfiguredClientSerializesPostBody() {
        SERVER.stubFor(post(
                    urlEqualTo("/api/v1/reservations"))
                .withHeader("X-Request-Id",
                        equalTo("boot-request"))
                .withRequestBody(equalToJson(
                    "{\"sku\":\"BOOT-1\",\"quantity\":3}"))
                .willReturn(okJson(
                    "{\"reservationId\":\"RES-BOOT\","
                    + "\"state\":\"ACCEPTED\"}")));

        StepVerifier.create(gateway.reserve(
                    new PartnerGateway.ReserveRequest(
                            "BOOT-1", 3),
                    "boot-request"))
                .assertNext(receipt ->
                    assertEquals("RES-BOOT",
                            receipt.reservationId()))
                .verifyComplete();

        SERVER.verify(1, postRequestedFor(
                urlEqualTo("/api/v1/reservations"))
                .withRequestBody(equalToJson(
                    "{\"sku\":\"BOOT-1\",\"quantity\":3}")));
    }
}
~~~

### Why is this a full-context test and not a controller test?

- `@SpringBootTest(webEnvironment=NONE)` loads Spring Boot application beans without opening an inbound HTTP server.
- Real `PartnerGateway` is created by Spring using **Boot-provided `WebClient.Builder`**.
- `@DynamicPropertySource` registers `partner.base-url` pointing to the local stub before the bean reads it.
- WireMock still receives **outbound HTTP** over sockets; it does not mock the application's own server.
- `@DirtiesContext(AFTER_CLASS)` prevents reusing a cached context after the local server stops.
- `SERVER.resetAll()` clears mappings and the request journal before each method, ensuring independence when run sequentially.
- The static server starts during class initialization so the URL exists when Spring builds the bean. This is a demo-specific choice; larger projects can use `WireMockExtension` or matching framework integration.

### What if there are global WebClient filters?

In real apps, a `WebClientCustomizer` may attach OAuth Bearer tokens, trace headers, logging filters, or custom codecs. Plain `WebClient.builder()` tests **do not automatically include** those customizations. Full-context tests use the injected builder and can add matchers for headers added by customizers:

~~~java
SERVER.stubFor(get(urlPathEqualTo("/protected"))
        .withHeader("X-Trace-Id", matching(".+"))
        .willReturn(okJson("{\"ok\":true}")));
~~~

This is an extension snippet; production must actually configure the header on the `WebClient` builder for the matcher to pass. Never place real tokens in WireMock mappings or logs.

## 9. Summary of test cases and expected results

The project provides **10 JUnit `@Test` methods**:

| Class | Test | What it guards |
| --- | --- | --- |
| `PartnerGatewayTransportTest` | `getSendsCorrectMethodPathQueryAndHeaders` | GET, path, query, headers, response DTO |
| `PartnerGatewayTransportTest` | `queryParameterIsEncodedAndNotSplitByAmpersand` | URI encoding of `&` and spaces |
| `PartnerGatewayTransportTest` | `postSerializesJsonAndCorrelationHeader` | POST, JSON body, Content-Type, request ID |
| `PartnerGatewayTransportTest` | `notFoundMapsHttp404ToDomainError` | 404 → domain exception |
| `PartnerGatewayTransportTest` | `serviceUnavailableRetainsHttpStatus` | 503 → `WebClientResponseException` |
| `PartnerGatewayTransportTest` | `noContentDoesNotBecomeFakeProduct` | 204 → error when contract requires body |
| `PartnerGatewayTransportTest` | `slowResponseCausesReactivePublisherTimeout` | Reactor publisher timeout |
| `PartnerGatewayTransportTest` | `monoIsColdAndSendsNoRequestBeforeSubscription` | Reactive cold publisher and request count |
| `PartnerGatewayBootWiringTest` | `bootConfiguredClientCallsLocalStub` | Spring-injected `WebClient.Builder` + base URL |
| `PartnerGatewayBootWiringTest` | `bootConfiguredClientSerializesPostBody` | Spring full wiring sending real JSON POST |

### Running the project

Requires JDK 17, compatible Gradle Wrapper, and internet access to fetch Maven dependencies the first time. **Docker is not required**.

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run a single class:

~~~bash
./gradlew test --tests 'com.example.transport.PartnerGatewayTransportTest'
./gradlew test --tests 'com.example.transport.PartnerGatewayBootWiringTest'
~~~

Reports are usually located at:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.transport.PartnerGatewayTransportTest.xml
    └── TEST-com.example.transport.PartnerGatewayBootWiringTest.xml
~~~

Expect **10 passing tests** when code and environment match. This is **an expectation from inspecting the source**, not a claim that Gradle ran on the reader's machine. Tests have no `System.out.println`, so there is no fixed business stdout. Gradle may print `BUILD SUCCESSFUL`, or use `UP-TO-DATE/FROM-CACHE`.

To force re-execution when diagnosing transport failures:

~~~bash
./gradlew test --rerun-tasks
~~~

If the wrapper is missing while a compatible Gradle is installed:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then commit the scripts/JAR per repository policy. Never upgrade a real project's dependencies solely because a tutorial uses a different Boot version.

### Assertions must not hardcode WireMock's port

Never assert `server.port() == 8080`. WireMock chooses an available ephemeral port; `server.baseUrl()` supplies it to the client. Tests only care that the client reaches the current server and the server verifies the right request.

## 10. Request matching: avoiding "false green" tests

WireMock supports many matchers. Pick the ones matching the API contract:

### `urlEqualTo` and `urlPathEqualTo`

~~~java
get(urlEqualTo("/api/v1/products/BK-001?include=stock"))
~~~

matches the URL including query string (sensitive to query order and encoded characters).

~~~java
get(urlPathEqualTo("/api/v1/products/BK-001"))
    .withQueryParam("include", equalTo("stock"))
~~~

matches path and query separately, usually easier to maintain with multiple query params when order does not matter.

### `withHeader`

~~~java
withHeader("Accept", containing("application/json"))
~~~

checks the header **actually received by the stub server**. `Content-Type` often includes a charset suffix, so `containing("application/json")` can be safer than `equalTo("application/json")` if the contract allows suffixes. For headers requiring an exact value (like an application-specific ID), `equalTo` catches mismatches.

### JSON: structural matching

~~~java
withRequestBody(equalToJson(
        "{\"sku\":\"BK-001\",\"quantity\":2}"))
~~~

JSON objects need not share key order, while fields and values must match. When a contract only requires a subset of fields and permits payload extensions, use `matchingJsonPath` deliberately; avoid loosening tests so much that misspelled fields go undetected.

### Request count and retry

~~~java
server.verify(1, postRequestedFor(
        urlEqualTo("/api/v1/reservations")));
~~~

A normal order action should not automatically issue two POSTs unless the API defines an idempotency key and retry policy. Verifying counts catches double subscriptions or unintended retries. When retries are designed, expected count may be 2 or 3, and tests must exercise the **response sequence** (503 first, 200 later) and verify business idempotency.

### Unmatched requests

When a request matches no stub, WireMock normally returns a **default 404** and records an unmatched entry in the request journal; under some JUnit extension settings, unmatched requests also fail the test. If a client maps 404 to a domain error, the root bug "wrong URL/header" can be masked as "product not found."

When a test fails, check:

1. What did the stub matcher specify?
2. What method/path/query/headers/body did the actual request have?
3. Was a query parameter encoded into a different param?
4. Is `Accept`/`Content-Type` missing or wrong in case/value?
5. Did the client call the wrong hostname, port, or API version?
6. Does WireMock hold entries in the request journal from an earlier test?
7. Was the 404 an **unmatched** default instead of an explicitly stubbed 404 scenario?

Practical rule: **Even in a test expecting a business 404, verify that the request matched the intended stub path.**

## 11. HTTP response statuses: 2xx/4xx/5xx and empty bodies

### 2xx success

`retrieve().bodyToMono(Product.class)` decodes the JSON body into `Product`. If HTTP status is 200 while the body is invalid JSON, the decoder fails—that is a **decode error**, not an HTTP status failure. JSON test fixtures must match contract field types/ranges (e.g., `priceCents` as an integer).

### 204 No Content

HTTP 204 normally carries no response body. If business logic expects a `Product`, default `bodyToMono(Product.class)` completes empty. The demo uses `switchIfEmpty(Mono.error(...))` to turn it into an explicit contract failure. Do not apply that rule universally: for a successful DELETE returning 204, `Mono<Void>` completion is valid.

### 404 Not Found

`retrieve()` converts 4xx/5xx into `WebClientResponseException` by default. The demo uses `onStatus` **exclusively for 404** to map to `ProductNotFoundException`. Other statuses like 503 keep the default behavior.

To verify exception logic, assert the exact **type** and appropriate message/cause; avoid asserting broad `RuntimeException.class`, which decode or connection errors also satisfy.

### 503 Service Unavailable

HTTP 503 delivers a response with headers and status code. Do not confuse it with connection refused or DNS failures, because transport errors **have no HTTP 503** to inspect.

If the app implements retry/backoff, only retry **classified transient failures**. For reservation-creating POSTs, enforce an idempotency key and provider contract: a timeout after the server committed the request means a blind retry creates duplicate reservations.

## 12. Delays, timeouts, cancellation, and socket errors

An HTTP stub server can inject controlled delays:

~~~java
server.stubFor(get(urlEqualTo("/slow"))
        .willReturn(aResponse()
            .withFixedDelay(1500)
            .withStatus(200)
            .withBody("OK")));
~~~

There are multiple timeout layers:

| Timeout | Handling layer | Meaning |
| --- | --- | --- |
| `Mono.timeout(Duration)` | Reactor operator | Publisher emitted no signal within the deadline |
| Connect timeout | HTTP connector/TCP | Failed to establish a connection in time |
| Response timeout | HTTP connector/runtime | Server failed to respond within the limit |
| Read timeout | Socket/network/connector | Waiting too long for data while reading |
| Pool acquire timeout | Connection pool | Failed to obtain a connection in time |
| Business deadline | Service/application | Total time across calls/retries exceeded SLA |

`slowResponseCausesReactivePublisherTimeout` **only tests the Reactor timeout**. To test Netty's `responseTimeout`, configure `HttpClient.responseTimeout` on `ReactorClientHttpConnector` and use a delayed stub server. When asserting the exception, check the **transport exception family/root cause** rather than hardcoding a Netty message string that may change across versions.

### Configuring Reactor Netty response timeout (extension snippet)

~~~java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofMillis(400));

WebClient client = WebClient.builder()
        .clientConnector(
            new ReactorClientHttpConnector(httpClient))
        .baseUrl(stubBaseUrl)
        .build();
~~~

This snippet requires imports for `reactor.netty.http.client.HttpClient`, `ReactorClientHttpConnector`, and `WebClient`, plus a real stub server URL. It **replaces the connector with a new one**, so in a real app ensure you preserve or integrate existing SSL, proxy, observability, connection pool settings, and customizers if part of the production contract.

### Connection reset and malformed responses

WireMock offers fault injection (e.g., `Fault.CONNECTION_RESET_BY_PEER` depending on server/HTTP runtime). Conceptual snippet:

~~~java
server.stubFor(get(urlEqualTo("/broken"))
        .willReturn(aResponse()
                .withFault(Fault.CONNECTION_RESET_BY_PEER)));
~~~

When the connection drops, `WebClient` raises a transport exception **with no HTTP status**. Verify behavior against your connector/OS rather than assuming every platform throws the exact same exception class or message.

### Do not use arbitrary `Thread.sleep`

`Thread.sleep(500)` to "wait for a request" easily flakes under CI scheduling and CPU contention. Use `StepVerifier`, the server request journal, latches, or bounded await mechanisms. For pure Reactor timing logic without HTTP, `StepVerifier.withVirtualTime` is helpful; however, **virtual time does not simulate network sockets**.

## 13. Retries and idempotency with a stub server

Many HTTP client bugs live in retry policies:

- On 503, the client retries too aggressively and amplifies load on the provider.
- On 404, the client retries pointlessly.
- A POST times out after the server persisted data, and a retry creates duplicates.
- Ignores `Retry-After`/rate limits.
- Drops correlation/idempotency keys across retry attempts.
- Unit mocks just return 200 immediately, hiding the true request count.

A meaningful retry test must:

1. Stub the first attempt to return 503.
2. Stub the next attempt to return 200 (WireMock **scenarios** or stateful response templating).
3. Invoke the real client.
4. Assert the final DTO and exact request count.
5. Verify idempotency/correlation headers are preserved on every attempt.
6. Assert retries apply only to classified status codes/exceptions.
7. Verify bounds (max retries, backoff, jitter) and total deadline.

**Do not blindly add retries to the production adapter just to create extra test cases.** The demo keeps the client simple with no auto-retry; `verify(1)` helps detect unintended double requests. Any system adding retries must define a clear contract, especially for state-mutating operations.

### A conceptual policy example

~~~java
mono.retryWhen(
    Retry.backoff(2, Duration.ofMillis(200))
         .filter(error -> isTransient(error)));
~~~

This is a conceptual snippet requiring the `Retry` import, `mono`, and an application-defined `isTransient` predicate; do not copy and run standalone. With `WebClientResponseException`, you can filter on 502/503/504/429 per contract. With network errors, distinguish safely retryable faults from non-retryable ones.

## 14. Verifying HTTPS/TLS and proxies when part of the contract

For many tasks, HTTP loopback suffices to test method/URI/body/status. Yet if the production client requires:

- Mutual TLS (client certificates).
- Custom truststore/CA, certificate pinning.
- Authenticated HTTP proxies.
- SNI and hostname verification.
- HTTP/2 ALPN.
- Custom connection pools, TLS renegotiation, keep-alive, or redirects.

then a **plaintext HTTP stub server** proves none of those configurations. You need an **HTTPS stub** with test certificates, matching client SSL configuration, and assertions proving handshakes succeed when valid and fail when misconfigured.

WireMock supports dynamic HTTPS ports. You can use:

~~~java
new WireMockServer(
    wireMockConfig()
        .dynamicHttpsPort()
        .httpDisabled(true));
~~~

This is an advanced configuration snippet outside the runnable demo and may require truststore/key setup. Never disable certificate validation in production to make tests pass; doing so defeats the very TLS property under test.

### Redirects

An HTTP stub can return `301/302/307/308` with `Location`. Whether the client runtime follows redirects depends on connector/config. Tests must verify **request counts, method/body preservation, host allowlists, and sensitive header handling**. Above all, never forward `Authorization` to an untrusted redirect host.

### Proxies

If an app uses a corporate proxy, WireMock on `localhost` may bypass the proxy and fail to exercise proxy config. Testing proxies requires a dedicated test proxy without production credentials.

## 15. Distinguishing outbound client tests from inbound WebTestClient

Two easily confused names:

- **`WebClient`**: the HTTP **client** an application uses to call external REST APIs.
- **`WebTestClient`**: the test client for WebFlux/web app endpoints; it can bind directly to a controller, application context, or live server.

When testing an outbound call:

~~~text
Application's WebClient -> external HTTP stub
~~~

When testing an inbound controller:

~~~text
WebTestClient -> application's WebFlux controller
~~~

If you use `@WebFluxTest` and `WebTestClient.bindToApplicationContext(...)`, the test may not open an inbound socket. It checks controller mapping/validation well, yet does not automatically verify **`WebClient` sending requests over transport to a provider**.

If you must test both directions together, write an integration test with the app's HTTP server on `RANDOM_PORT` and an external WireMock stub, send an HTTP request into the app, and verify the app calls the stub. That is **two-hop end-to-end**, slower and requiring more cleanup/port management than this demo.

## 16. Configuring base URLs properly in Spring Boot

In real applications, never hardcode partner URLs in adapters. Use configuration properties or `@Value` with an explicit key:

~~~properties
partner.base-url=https://api.partner.example
~~~

This illustrates production settings. In integration tests, override the value to point to the **local stub**:

~~~java
@DynamicPropertySource
static void partnerUrl(DynamicPropertyRegistry registry) {
    registry.add("partner.base-url", SERVER::baseUrl);
}
~~~

Benefits:

- Tests do not need to know the stub port in advance.
- No JVM-wide `System.setProperty`.
- No edits to production source just to hit a mock.
- The `PartnerGateway` bean keeps using the exact same constructor/config wiring.
- Fails fast if the base URL is missing instead of accidentally calling another server.

**Do not mix multiple URL sources for the same client without understanding precedence**, e.g., combining `@Value("${partner.base-url}")` with a custom `WebClientCustomizer` that hardcodes another base URL. Tests mocking only collaborators miss precedence bugs; full-context tests against a real HTTP stub catch them.

### When to use `@TestPropertySource`

If a stub sits at a fixed address and you control the port, `@TestPropertySource(properties=...)` can override it. With WireMock's dynamic ports, however, `@DynamicPropertySource` is much cleaner.

### When using JUnit `@RegisterExtension`

WireMock 3 provides `WireMockExtension` for JUnit Jupiter:

~~~java
@RegisterExtension
static WireMockExtension wiremock =
    WireMockExtension.newInstance()
        .options(wireMockConfig().dynamicPort())
        .build();
~~~

This is an illustrative snippet requiring imports. The extension manages start/stop/reset and exposes `wiremock.stubFor(...)` and `wiremock.port()`. It eliminates manual lifecycle boilerplate, though when paired with Spring context caching you must keep server lifetime synchronized with cached context reuse. In the runnable project, plain JUnit uses a manual per-test server, while the full-context test uses an eagerly started static server and `@DirtiesContext` to keep boundaries crystal clear.

## 17. Isolation and parallel tests

HTTP stub tests can leak state in subtle ways:

- Mappings from a prior test remain active.
- WireMock's request journal still holds old requests; `verify(1)` fails with count 2.
- Two test classes both bind port 8080.
- A static server stops while Spring's cached `ApplicationContext` retains a `WebClient` pointing at the old base URL.
- One test calls `server.resetAll()` while another parallel test is calling the server.
- One test uses a stateful response scenario without resetting state before the method.
- A background client retry continues running after test completion and hits a stopped server.

Countermeasures:

1. **Random port** per server instance.
2. Isolate servers per test method or per class with clear lifecycles.
3. Call `resetAll()` on stubs/request journal before each test when sharing a server.
4. When parallel tests share a server, avoid mid-flight resets; use dedicated servers or resource locks.
5. Never reuse a Spring context pointing at a stopped local server; use `@DirtiesContext` or unify lifetimes.
6. Ensure every reactive pipeline is subscribed and verified to completion/timeout before teardown.
7. Never depend on test method ordering; keep fixtures independent.
8. Never fall back to a real partner URL as a default in tests.
9. Restrict logging of bodies containing tokens, user PII, or sensitive data.
10. When using file-based WireMock mappings, verify they belong to the right resource directory and avoid loading mappings from other modules.

A test that passes **alone** yet fails in the **full suite** points to isolation or lifecycle bugs—not a reason to insert `Thread.sleep`.

## 18. Reading errors and fixing the right layer

| Symptom | Likely cause | Diagnosis |
| --- | --- | --- |
| `Connection refused` | WireMock not started or wrong base URL port | Start server before client call; use `server.baseUrl()` |
| Unexpected `404` | Unmatched stub due to wrong path/query/header | Inspect request journal and matchers |
| `ProductNotFoundException` in happy-path test | Request unmatched so WireMock returned 404 | Verify exact request URL/path/query |
| `JsonParseException`/`DecodingException` | Response body/header is not valid JSON | Use `okJson` and matching DTO schema |
| `UnsupportedMediaTypeException` | `Content-Type` incompatible with codec | Stub the header per contract |
| POST matcher missed | Client body field/order/media type mismatch | Inspect recorded body, use `equalToJson` |
| `StepVerifier` never completes | `Mono` not subscribed, or server delay/timeout | Check cold publisher, timeout, and lifecycle |
| Verify expected 1, found 0 | Client never subscribed or called another URL | Check `StepVerifier` before verify, inspect journal |
| Verify expected 1, found 2 | Retry/double subscription/stale request | Reset server, inspect retry policy |
| Timeout with no HTTP status | Transport/publisher error | Do not assert HTTP status code on socket errors |
| 503 mapped to `ProductNotFoundException` | `onStatus` predicate too broad | Map 404 only, preserve other statuses |
| 204 treated as null DTO | Empty `Mono` unhandled | Add `switchIfEmpty` per contract |
| WebFlux test context missing `PartnerGateway` | `@WebFluxTest` is a controller slice | Use full context or import the needed bean |
| Boot client missing custom header/filter | Built `WebClient.builder()` outside Boot | Inject Boot `WebClient.Builder` and run full-context test |
| Parallel CI port bind failure | Hardcoded port 8080 | Use dynamic port |
| HTTPS handshake fails | Truststore/SNI/cert mismatch | Use HTTPS stub + test CA |
| Proxy redirect leaks headers | Client follows redirect to another host | Test header forwarding and allowlists |
| Passes alone, fails in suite | Server reset/context cache/static state | Isolate lifecycle/reset/deliberate `@DirtiesContext` |
| WireMock class/version conflict | Mixed WireMock 2/3/4 or Jetty deps | Inspect Gradle dependency tree; align versions |
| Suite too slow | Starting server per every method | Use class-scoped server + safe resets |
| `WebClient` logs leak real tokens | Overly broad debug logging | Use fake credentials/sanitization, disable sensitive logs |
| Passes without making HTTP calls | `WebClient` or gateway mocked with Mockito | Use real `WebClient` + `server.verify(...)` |

### Optimal debugging flow

1. **Identify the test type:** collaborator mock, fake `ExchangeFunction`, or real HTTP stub?
2. **Verify lifecycle:** is the server running, on which port, and what is the client's base URL?
3. **Verify the wire path:** did an actual request arrive at the server?
4. **Inspect the request journal:** method/path/query/headers/body, not merely `WebClient`'s exception.
5. **Check stub matchers:** where is the mismatch—query encoding or `Content-Type`?
6. **Check the response:** status, headers, content type, valid JSON, and delays/faults.
7. **Check `WebClient` error handling:** `retrieve`, `onStatus`, `exchangeToMono`, decoding.
8. **Check reactive subscription:** `Mono` only builds a plan; was `StepVerifier`/`block` invoked?
9. **Check timeout/retries** and request counts. Operator timeout differs from socket timeout.
10. **Check Boot wiring/context caching** if plain tests pass while full-context tests fail.
11. **Check parallel suite interaction:** static servers, `resetAll`, and shared state.
12. **Never loosen matchers just to pass** before verifying the true API contract.

## 19. Worthwhile follow-up topics

### Large request bodies, streaming, and backpressure

Small JSON bodies and single responses do not prove multipart uploads, `Flux<DataBuffer>` streaming, chunked transfer encoding, SSE, or backpressure with slow consumers. When contracts cover these, use stubs supporting streaming/chunking and verify cancellation and resource cleanup. Calling `bodyToMono(String.class)` alone is insufficient.

### Binary payloads

If `WebClient` uploads files or downloads images/PDFs, tests must verify bytes/hashes, content length, content disposition, multipart boundaries, and appropriate codecs—not just JSON strings. WireMock can return `byte[]` bodies. Avoid converting binary payloads into `String` for comparison, as character encoding corrupts binary data.

### Redirects and cookie jars

`WebClient`/Netty connectors handle redirects and cookies differently from browsers. Test redirects, cookies, `Set-Cookie`, and forbidden header forwarding whenever your application relies on them.

### OAuth/OIDC

If `WebClient` uses OAuth2 client credentials, test the token request/client filter alongside resource requests or stub the token endpoint separately. Never hardcode production tokens; use fake tokens and verify header forwarding. Do not mock a token service and claim you verified TLS trust or transport.

### Observability

HTTP clients often emit trace/span headers and Micrometer metrics. Tests can verify correlation/trace headers reach the stub and metrics are recorded, while avoiding assertions that a random trace ID equals a fixed string. Unless tracing is part of the contract, avoid coupling every test to an external telemetry backend.

## 20. Self-practice exercises

**Exercise A — change HTTP method:** Temporarily switch `getProduct` from `get()` to `post()` and run the GET test. Because the WireMock matcher requires GET, the test must fail. Revert.

**Exercise B — remove query param:** Remove `queryParam("include", "stock")`. Both matcher and verify must catch it. Explain why asserting only the DTO is insufficient.

**Exercise C — URI encoding:** Temporarily replace `searchOne("Java & Spring")` with raw string concatenation `"?q=" + term` in a scratch branch. Inspect the request journal and observe the matcher fail to receive the proper `q` value. Revert.

**Exercise D — header:** Remove `defaultHeader("X-Client-Name", ...)` and run the GET test. Matcher/verify must fail.

**Exercise E — JSON body:** Rename field `quantity` to `qty` in the DTO or break serialization with a converter. The POST test's `equalToJson` must catch the mismatch.

**Exercise F — 404 vs. 503:** Change the `onStatus` predicate to match all 4xx/5xx. The 503 test must fail due to the wrong domain exception; restore the 404-only mapping.

**Exercise G — 204 No Content:** Remove `switchIfEmpty` and run the 204 test. Explain why the publisher completes empty and why GET product must not treat that as success when a body is required.

**Exercise H — cold Mono:** Remove `StepVerifier.create(result)` while keeping the request count verification. With no subscription, zero requests occur. Explain the difference between assembling a publisher and executing it.

**Exercise I — timeout:** Replace `Mono.timeout` with Reactor Netty `responseTimeout` in a separate test. Keep stub delay > timeout. Verify the exception category/root cause without hardcoding connector messages.

**Exercise J — retry 503:** Add bounded retry for idempotent GET using a WireMock scenario returning 503 then 200. Assert the final DTO and exactly two requests. Do not apply blind retries to POST.

**Exercise K — Boot customizer:** Add a `WebClientCustomizer` attaching `X-App-Trace` and verify it in the full-context test. Plain builder tests lack that header; explain the difference.

**Exercise L — WireMock extension:** Replace the manual per-method server with `@RegisterExtension static WireMockExtension`. Verify pre-test reset and server lifetime alongside Spring context caching.

**Exercise M — HTTPS:** Run WireMock on a dynamic HTTPS port, create test-only CA/certs, and configure the client truststore. Prove valid handshakes succeed and a deliberately wrong CA fails. Never disable TLS verification.

**Exercise N — socket fault:** Use `Fault.CONNECTION_RESET_BY_PEER` to inject a transport fault. Assert there is no HTTP status because the connection dropped before a response was processed.

**Exercise O — contract versioning:** Rename JSON field `priceCents` to `amountCents` in the stub. Keep the old DTO and observe default decoding behavior. Add validation if missing fields violate business rules.

**Exercise P — parallel:** Have two test classes share one class-scoped `WireMockServer` and enable parallel execution. Observe `resetAll()` conflicts mid-flight; switch to isolated servers or resource locks.

## 21. Pre-merge checklist for HTTP client integration tests

- [ ] Test uses **real `WebClient`** and a real stub server when transport is the target?
- [ ] Outbound `WebClient` is not confused with inbound `WebTestClient`?
- [ ] Stub server runs on localhost/random port, with client base URL taken from the server instance?
- [ ] No production/fallback URLs or real credentials in tests?
- [ ] Verifies HTTP method/path/query/headers **actually received** by the stub?
- [ ] URI variables/query encoding tested with tricky inputs like spaces/`&`?
- [ ] POST JSON verifies `Content-Type`, body, and response DTO?
- [ ] Request counts verified when retries/double subscriptions are a risk?
- [ ] 2xx, 404, 5xx, and 204 tested per contract?
- [ ] HTTP status errors are not conflated with connection/transport exceptions?
- [ ] Timeout tests clearly distinguish **which timeout layer** is tested?
- [ ] No `Thread.sleep` replacing reactive completion?
- [ ] WireMock mappings/request journal reset between tests when sharing a server?
- [ ] Server lifecycle aligns with Spring context caching and parallel execution?
- [ ] If using global Boot `WebClient` customization, tested with full-context injected builder?
- [ ] When TLS/proxy/HTTP2 is required, tested over the real protocol rather than plain HTTP stubs?
- [ ] Certificate validation is never disabled just to get a green test?
- [ ] Retries/backoff enforce max attempts/deadlines and an idempotency contract?
- [ ] Test data/headers leak no tokens, PII, or secrets into logs?
- [ ] CI needs no real third-party API to run repeatably?
- [ ] Tests verify both outbound requests and inbound responses, not just non-null DTOs?
- [ ] Before merging, inspected the test report to ensure tests actually executed?

## 22. References

- [Spring Framework — Testing WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): recommends real mock web servers such as WireMock/OkHttp MockWebServer when testing network clients.
- [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): injected `WebClient.Builder`, connectors/runtimes, and customizers.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): request building, `retrieve`/`exchangeToMono`, filters, status handling.
- [Spring Framework 6.1 — WebClient.RequestHeadersSpec](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/web/reactive/function/client/WebClient.RequestHeadersSpec.html): default 4xx/5xx behavior and `onStatus`.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): request matching and response configuration.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): path/query/header/body matchers.
- [WireMock — Verifying](https://wiremock.org/docs/verifying/): request journal and exact request counts.
- [WireMock — JUnit Jupiter](https://wiremock.org/docs/junit-jupiter/): `WireMockExtension`, random ports, reset lifecycle.
- [WireMock — Configuration](https://wiremock.org/docs/configuration/): `dynamicPort`, HTTPS/faults, and server options.
- [WireMock — Installation](https://wiremock.org/docs/download-and-installation/): WireMock 3.x standalone Java dependency.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, publisher signaling, and virtual time.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slices, context.

**Remember:** When you need to prove **an HTTP client sends the right request over transport**, connect real `WebClient` to a **local WireMock/MockWebServer**. Stubs must match **method/path/query/headers/body**, and tests must assert both **the response/error and the real HTTP request count**. For Spring Boot filters/codecs/properties, add a full-context test using the **injected `WebClient.Builder`**. Distinguish status errors, decode errors, operator timeouts, and socket faults; manage lifecycle cleanly so tests run reliably on CI.
