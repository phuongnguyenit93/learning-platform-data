# Testing WebClient with a Realistic Mock HTTP Server

## 1. Context: mocking methods is not enough to prove an HTTP client is right

`WebClient` is Spring WebFlux's reactive HTTP client. A service layer may call a partner API to fetch inventory, submit a reservation order, handle error codes, or stream updates. Correct Java logic does not guarantee a correct HTTP exchange: the request may use the wrong URI, miss headers, serialize JSON off-contract, mishandle 404/503, fail to enforce timeouts, or fail to release bodies/connections.

Example class calling an inventory system:

~~~java
public Mono<Item> getItem(String sku) {
    return webClient.get()
        .uri("/v1/items/{sku}", sku)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Item.class);
}
~~~

If you only mock `WebClient` with Mockito at the level of `get()`, `uri()`, `retrieve()`, and `bodyToMono()`, tests must stub a complex fluent API chain; they **do not actually make HTTP requests**, do not run connectors, do not encode/decode bodies, and do not observe network state.

A more reliable solution is running **a real mock HTTP server on loopback**:

- OkHttp's `MockWebServer` or `WireMock` listens on `127.0.0.1:port`.
- The production `WebClient` is configured to call this mock server instead of an Internet API.
- The mock server returns queued or stubbed HTTP responses per request.
- Tests inspect the HTTP method, path, query, headers, and request body actually sent.
- Response delays, 4xx/5xx errors, chunked bodies, socket disconnects, and other conditions can be simulated.

This is a **client integration test with a mock server**: the client side runs real codecs, `ClientHttpConnector`, TCP I/O, and response logic; the remote server side is controlled so tests are fast and repeatable. A mock server is not a full replica of the partner system.

Lesson goals:

1. Choose the right testing level for WebClient.
2. Understand `MockWebServer.enqueue`, `takeRequest`, and using a random port.
3. Verify the outgoing request actually sent rather than just checking mock method calls.
4. Test success, 404, 503, retries, timeouts, no-content, response headers, and NDJSON streams.
5. Write a complete example with Java 17, Spring Boot 3.5.7, OkHttp MockWebServer 4.12.0, and JUnit Jupiter.
6. Know how to extend to WireMock, network faults, TLS, pooling, backpressure, and CI.

## 2. Choosing the test layer that fits the goal

| Testing approach | Real HTTP socket? | What it verifies | Limitations |
| --- | --- | --- | --- |
| Mockito mock service/repository | No | Business decisions and method calls | Does not test encoding, status, transport |
| Mock `ExchangeFunction` | No | WebClient request construction and custom filters at boundary | Skips connector, wire-level semantics |
| `MockWebServer`/`WireMock` on loopback | Yes | URI, headers, body, codecs, status, timeout, transport errors | Real remote server does not participate |
| `WebTestClient.bindToController` | No external server | Inbound WebFlux controller/handler | Does not replace outbound WebClient tests |
| `WebTestClient.bindToServer` | Yes | HTTP requests to the server under test | Usually used to test server-side APIs |
| Testing against partner sandbox/test environment | Yes | End-to-end integration close to real system | Slow, hard to reproduce, data/credentials |

**Recommendation:** for a service using WebClient to call a REST API, use MockWebServer/WireMock at the client boundary; add unit tests for complex business logic and some contract/end-to-end tests against a real sandbox when needed.

Spring Framework officially recommends mock HTTP servers like OkHttp MockWebServer or WireMock for WebClient testing because they allow using the same HTTP client configuration as production and simulating network scenarios that method mocks cannot uncover.

### 2.1. Connection diagram

~~~text
JUnit / StepVerifier
        |
        v
WarehouseClient (real application code)
        |
        v
Spring WebClient
        |
        v
Reactor Netty ClientHttpConnector + codecs
        |
        v
localhost:random-port  <------ actual HTTP over TCP ------>
        |
        v
MockWebServer
        |
        +--> queued MockResponse 200 / 404 / 503
        +--> delayed response / chunked body / socket policy
        |
        +--> RecordedRequest to assert method/path/headers/body
~~~

The core value is verifying **both the outgoing request and the incoming response received by the client**. A test that only stubs a response and checks the final DTO is insufficient: the application might call the wrong path or headers while MockWebServer still returns the queued response.

## 3. Core components of MockWebServer

### 3.1. Choosing an explicit API version

Examples in this lesson use **OkHttp MockWebServer 4.12.0**, Java packages:

~~~java
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.RecordedRequest;
import okhttp3.mockwebserver.SocketPolicy;
~~~

With OkHttp 5, MockWebServer's artifact, package, and builder API may differ (e.g., `mockwebserver3`). Do not copy imports and methods directly from 4.12.0 to 5.x and expect them to compile.

### 3.2. Mock server lifecycle

~~~java
MockWebServer server = new MockWebServer();
server.start();

try {
    String baseUrl = server.url("/").toString();
    WebClient client = WebClient.builder()
        .baseUrl(baseUrl)
        .build();

    // enqueue response; make WebClient request; inspect RecordedRequest.
} finally {
    server.shutdown();
}
~~~

`start()` opens a real HTTP listener; `shutdown()` closes the server and frees resources. `server.url("/")` returns an HTTP URL containing the host and **actual port**, avoiding hardcoded ports like 8080/9999 that collide in parallel tests.

`@BeforeAll`/`@AfterAll` or a JUnit extension can also be used. If the Spring ApplicationContext needs the base URL at initialization time, use `@DynamicPropertySource` with a server already started before the property is read.

### 3.3. Enqueueing responses

~~~java
server.enqueue(new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("""
        {"sku":"SKU-7","name":"Keyboard","stock":12}
        """));
~~~

Each HTTP request handled by the server takes the next response from the queue. This fits retry testing or ordered workflows very well:

~~~java
server.enqueue(new MockResponse().setResponseCode(503));
server.enqueue(new MockResponse().setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("..."));
~~~

**Important:** the queue mechanism does not match paths automatically. A request to the wrong URI can still receive the first 200 response. Always inspect `RecordedRequest` afterward, or use a `Dispatcher`/WireMock stubs if responses should depend on method/path/headers.

### 3.4. Recording the actual HTTP request

~~~java
RecordedRequest request = server.takeRequest(
    2, TimeUnit.SECONDS
);

assertNotNull(request);
assertEquals("GET", request.getMethod());
assertEquals("/v1/items/SKU-7", request.getPath());
assertEquals("application/json", request.getHeader("Accept"));
~~~

For POST, read the request body with:

~~~java
String json = request.getBody().readUtf8();
assertTrue(json.contains("\"sku\":\"SKU-7\""));
~~~

`takeRequest(timeout, unit)` returns null if no request arrives within the wait time. Use a finite timeout to avoid hanging tests indefinitely when code fails to subscribe or misses a condition.

### 3.5. HTTP status, headers, and body are three independent signals

An HTTP response has:

- Status line (200, 204, 400, 404, 429, 503, etc.).
- Response headers such as `Content-Type`, `ETag`, and `Retry-After`.
- Body, which may be empty, JSON, NDJSON, SSE, HTML, or chunked bytes.

`WebClient.retrieve()` by default turns 4xx/5xx into `WebClientResponseException`, with subclasses for several common codes. Do not assume 404 returns `Mono.empty()`. If fallback behavior is wanted, client code must explicitly map statuses/errors to suitable values.

## 4. Mandatory test categories for WebClient

### 4.1. Request contract

For every important operation, check:

- Method: GET/POST/PATCH/DELETE.
- Path and percent-encoding.
- Query parameters and encoded values.
- `Accept`, `Content-Type`, authorization/correlation headers.
- JSON field names, null handling, and data types.
- Response DTO or `ResponseEntity`.

Avoid checking only the output. A mock server queue can return valid JSON for a request sent to **the wrong path**.

### 4.2. Success with JSON

When the server returns 200 and a JSON body, the test should prove WebClient decodes it into the expected DTO. With Java `record` and Jackson (included in the matching WebFlux starter), fields `sku`, `name`, and `stock` map by name.

### 4.3. 204 No Content

~~~java
server.enqueue(new MockResponse().setResponseCode(204));
~~~

`bodyToMono(Item.class)` creates no `Item` when the body is empty; the stream can complete without emitting an item. `StepVerifier.verifyComplete()` distinguishes 204 success from a 404 error.

### 4.4. 4xx and 5xx

With `retrieve()`, 404 can emit `WebClientResponseException.NotFound`; 503 can emit `WebClientResponseException.ServiceUnavailable`.

Test two separate groups:

- 404 is protocol-valid yet the resource does not exist: error or fallback as decided by business rules.
- 503 is usually a transient error eligible for policy-driven retry.
- 400/401/403 should not be blindly retried.
- 429 may require honoring `Retry-After` or rate-limiting policies.

### 4.5. Bounded retries and idempotency

~~~java
return client.get()
    .uri("/v1/items/{sku}", sku)
    .retrieve()
    .bodyToMono(Item.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(20))
            .jitter(0d)
            .filter(error ->
                error instanceof WebClientResponseException.ServiceUnavailable)
    );
~~~

`Retry.backoff(2,...)` means **at most two retries after the initial request**, potentially making three total HTTP requests. Use jitter=0 in tests to avoid random backoff variance; production should consider jitter to mitigate retry storms.

Placing retry after `bodyToMono` causes the source to be **resubscribed** on each attempt. For idempotent GETs this is usually suitable; for resource-creating POSTs, retries can cause duplicate side effects even if the first response was lost. Require an idempotency key or dedicated protocol before retrying write operations.

### 4.6. Delayed response bodies and timeouts

MockWebServer can delay the body:

~~~java
server.enqueue(new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("{\"sku\":\"slow\",\"name\":\"Slow\",\"stock\":1}")
    .setBodyDelay(700, TimeUnit.MILLISECONDS));
~~~

If WebClient uses:

~~~java
return getItem("slow")
    .timeout(Duration.ofMillis(150));
~~~

then StepVerifier observes `TimeoutException`. This is a timeout on **the reactive operation** since subscription; it is not the same as Reactor Netty's socket connect timeout or per-read timeout.

### 4.7. NDJSON streams and chunked transfer

WebClient can decode a stream with:

~~~java
Flux<Item> updates = webClient.get()
    .uri("/v1/updates")
    .accept(MediaType.APPLICATION_NDJSON)
    .retrieve()
    .bodyToFlux(Item.class);
~~~

MockWebServer returns multiple JSON objects separated by newlines with header `Content-Type: application/x-ndjson`. `setChunkedBody` can split the body across multiple HTTP chunks.

**HTTP chunk boundaries do not equal JSON object boundaries.** Client decoders must tolerate objects split across multiple TCP reads/HTTP chunks; do not assume every `DataBuffer` is one complete JSON line.

### 4.8. Transport errors differ from HTTP status errors

- 404/503 are valid HTTP responses; clients typically receive `WebClientResponseException`.
- Connection refused, socket reset, and premature close are transport errors; clients may receive `WebClientRequestException` or connector-related errors.
- Reactive pipeline timeouts can emit `TimeoutException`.

Do not lump everything into "server returned 500." When testing transport failures, avoid asserting overly specific Netty exception messages because they depend on OS/connector. Note that Reactor Netty may automatically retry certain failures on incompletely sent requests; do not rigidly assert a single request on disconnect tests.

## 5. How "realistic" is a mock HTTP server?

### 5.1. MockWebServer versus Mockito

MockWebServer opens a real HTTP listener, processes HTTP bytes, maintains socket lifecycles, and records requests. Thus it verifies encoding, decoders, body aggregation, and part of the HTTP client's behavior.

However, the server does not fully simulate production:

- Does not automatically reproduce load balancers, proxies, service meshes, or CDNs.
- Does not simulate server business state by default when using only `enqueue`.
- Does not automatically simulate every nuance of TLS, HTTP/2, slow consumers, or NAT.
- Does not simulate the API data contract if tests author the wrong JSON schema.
- Does not replace partner contract tests or sandbox tests.

Treat it as a **controlled test double at the HTTP boundary**, not a "real remote."

### 5.2. Simulating network faults

Mechanisms available in MockWebServer 4.x include:

~~~java
new MockResponse().setSocketPolicy(
    SocketPolicy.DISCONNECT_AT_START
);
~~~

And:

~~~java
new MockResponse()
    .setResponseCode(200)
    .setBody("some bytes")
    .throttleBody(5, 100, TimeUnit.MILLISECONDS);
~~~

Or:

~~~java
new MockResponse()
    .setResponseCode(200)
    .setBody("slow-body")
    .setHeadersDelay(200, TimeUnit.MILLISECONDS);
~~~

Use these to test:
- Connections dropped before returning a response.
- Connections cut mid-stream while sending body.
- Responses returning very slowly without disconnecting.
- Header arrival delays, body delays, or bandwidth throttling.

These are **illustrative API snippets**, not part of the full runnable project in section 8. With SocketPolicy, resulting exceptions and attempt counts can depend on connector/retries; write tests around reliable invariants and avoid flaky assertions.

### 5.3. When responses depend on the request

`MockWebServer.enqueue` works well for predetermined request sequences. If multiple client requests run concurrently, responses taken in server arrival order may differ from expected logical order.

In that case, use MockWebServer's `Dispatcher` or WireMock stubs to match requests by path/method/headers:

~~~java
server.setDispatcher(new Dispatcher() {
    @Override
    public MockResponse dispatch(RecordedRequest req) {
        if ("/health".equals(req.getPath())) {
            return new MockResponse()
                .setResponseCode(200)
                .setBody("ok");
        }
        return new MockResponse().setResponseCode(404);
    }
});
~~~

`Dispatcher` fits stateful simulations or multiple routes with distinct responses. Avoid mixing both the queue and a custom Dispatcher in the same test unless you clearly understand server precedence rules.

### 5.4. WireMock when richer contracts are needed

`WireMock` supports HTTP stubs by URL, method, headers, body matchers, scenario state, response templating, faults, delays, request journals, and record/playback. It fits APIs with many endpoints and multi-step scenarios.

Conceptual example, not part of the sample project code:

~~~java
stubFor(get(urlEqualTo("/v1/items/SKU-7"))
    .willReturn(okJson(
        "{\"sku\":\"SKU-7\",\"name\":\"Keyboard\",\"stock\":12}"
    )));
~~~

The snippet above assumes WireMock static API imports and separate instance/port setup. Do not mix WireMock examples with MockWebServer packages/imports.

### 5.5. HTTPS/TLS

MockWebServer can be configured with an SSL socket factory. On WebClient, configure a matching test truststore/certificate. **Never disable certificate validation in production** just to make testing easier. To simulate mutual TLS, configure certificates and client auth on both the mock server and the HTTP connector.

### 5.6. Ports and parallel tests

- Always use dynamic ports: `server.start()` picks an ephemeral port; obtain `server.url("/")`.
- Start/stop the server per test class or test instance.
- Do not let server state or queues bleed across tests without controlled state management.
- For parallel tests, each test/class needs its own server or a thread-safe dispatcher.
- Do not call real Internet APIs in routine CI unit/integration tests; data and rate limits vary.
- Use finite timeouts in StepVerifier and `takeRequest`.

## 6. retrieve(), onStatus(), exchangeToMono(), and releasing response bodies

### 6.1. retrieve() handles error statuses by default

~~~java
Mono<Item> item = webClient.get()
    .uri("/v1/items/{sku}", sku)
    .retrieve()
    .bodyToMono(Item.class);
~~~

`retrieve()` is most convenient when decoding bodies with default error behavior (>=400 becomes `WebClientResponseException`). When domain-specific error mapping is needed:

~~~java
Mono<Item> item = webClient.get()
    .uri("/v1/items/{sku}", sku)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> Mono.error(new ItemNotFoundException(sku))
    )
    .bodyToMono(Item.class);
~~~

This is an illustrative snippet; `ItemNotFoundException` is an application-defined class. If reading the error body is needed to build the exception, call `response.bodyToMono(String.class)` before constructing the exception; avoid ignoring body/resource ownership.

### 6.2. exchangeToMono() for complex status handling

~~~java
Mono<Item> result = webClient.get()
    .uri("/v1/items/{sku}", sku)
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(Item.class);
        }
        return response.createError();
    });
~~~

In Spring Framework 6.2, after the Publisher returned by `exchangeToMono` completes, any unconsumed response body is checked and released to prevent resource leaks. If you need to read the body, do it **inside the lambda**; never retain `ClientResponse` to decode downstream after the response has been released.

### 6.3. Avoid casual use of legacy exchange()

Low-level APIs require careful response body management. Forgetting to release/consume bodies can hurt connection pooling. Prefer `retrieve()` or `exchangeToMono/Flux()` and test consecutive error scenarios.

### 6.4. Tests that highlight the differences

Explicitly test:

- 204 returns Mono.empty (not 404).
- 404 via default retrieve emits WebClientResponseException.
- Error mapping with onStatus preserves the contract expected by the service.
- Across multiple retries, error response bodies from failed attempts are handled/released properly before new requests.
- When cancellation happens, connections/resources of the canceled request are handled properly by the connector.

### 6.5. Logging and observability

Never log Bearer tokens, cookie/session IDs, or sensitive data from RecordedRequest. Tests can assert that a token was sent, yet never put production tokens in fixtures. In production, tracing and HTTP metrics need low-cardinality path templates rather than attaching every random ID as a metric label.

## 7. Designing anti-flaky tests with accurate Reactor semantics

### 7.1. Always trigger a subscription from the test

~~~java
Mono<Item> result = warehouseClient.getItem("SKU-7");
~~~

The line above creates no HTTP traffic yet. You must subscribe via StepVerifier:

~~~java
StepVerifier.create(result)
    .expectNext(new Item("SKU-7", "Keyboard", 12))
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Do not call `server.takeRequest` before a subscriber exists. Once the test method has `verify`ed a terminal signal, the request has normally been sent, and RecordedRequest can verify it.

### 7.2. Test response first, request second

A typical sequence follows:

1. `server.enqueue(new MockResponse(...))`.
2. Build the Publisher or call the service method.
3. `StepVerifier...verify(Duration)`.
4. `server.takeRequest(timeout, unit)`.
5. Assert method/path/query/headers/body.

If coordinating request-response under complex concurrency, use a Dispatcher or `CountDownLatch` with timeout and cleanup. Avoid overusing `Thread.sleep` because it creates timing-dependent tests.

### 7.3. Keep retry tests independent of wall-clock precision

Use short backoffs (e.g., 10–20ms) and jitter=0 for unit/integration tests. Do not assert exact millisecond counts; schedulers, CI load, and OS thread scheduling can vary.

To test retries, enqueue 503, 503, 200; after success, read three RecordedRequests and assert all three share the same method/path. Never assert only the final DTO.

### 7.4. Avoid order-dependent tests

JUnit does not guarantee test method ordering by default. Each method should enqueue the exact number of responses it consumes, take the exact number of RecordedRequests, and not depend on requests from earlier tests. A class-wide shared server is acceptable if test methods run sequentially and the queue is managed strictly; when running in parallel, use per-test servers or a dispatcher.

### 7.5. Be explicit about timeout types

Three common timeouts differ:

| Timeout | Used when | Example |
| --- | --- | --- |
| Connect timeout | Cannot connect to server within allowed time | Reactor Netty `CONNECT_TIMEOUT_MILLIS` |
| Response timeout | Server fails to send response fast enough at HTTP client layer | Reactor Netty `responseTimeout` |
| Reactor `timeout(Duration)` | Entire reactive operation fails to emit expected signal before deadline | `mono.timeout(...)` |

`StepVerifier.verify(Duration)` is a **test harness** timeout to prevent hanging tests; it does not configure production WebClient timeouts. Have both client operation bounds and test harness bounds.

### 7.6. Do not use virtual time to simulate real networking

`StepVerifier.withVirtualTime` is helpful for Reactor timers driven by VirtualTimeScheduler. However, a mock HTTP server actually sleeping, delaying sockets, or sending bytes on real threads does not speed up under the virtual scheduler. For network delays, use finite timeouts and real-time tests; reserve virtual time for pure reactive retry/backoff logic without real network I/O.

## 8. Runnable project: Spring Boot 3.5.7, Java 17, MockWebServer 4.12.0

In this project, `WarehouseClient` is a real production service using Boot's auto-configured `WebClient.Builder`. Tests use `@SpringBootTest(webEnvironment=NONE)` to wire beans without starting the application's own HTTP server; only MockWebServer on loopback serves outbound HTTP.

### 8.1. Directory structure

~~~text
webclient-mock-server-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/httpclient/
    │   │   ├── HttpClientDemoApplication.java
    │   │   └── WarehouseClient.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/example/httpclient/
            └── WarehouseClientTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webclient-mock-server-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Relevant versions:
- Spring Boot 3.5.7 manages compatible Spring Framework 6.2.x, Reactor, JUnit 5, and Netty.
- MockWebServer 4.12.0 is pinned directly to keep the `okhttp3.mockwebserver` package.
- Maven downloads dependencies from configured repositories on first run; the project requires access to Maven Central or an internal mirror.
- `reactor-test` and `mockwebserver` are test-only; never include the mock server in production runtime.

### 8.3. application.properties

~~~properties
spring.main.web-application-type=none
partner.base-url=http://127.0.0.1:1
~~~

The default `partner.base-url` value is merely a safe placeholder for the example, not a real production endpoint. In tests, `@DynamicPropertySource` replaces it with the started MockWebServer URL. In real deployments, configure partner URLs via controlled environment/configuration secrets.

### 8.4. HttpClientDemoApplication.java

~~~java
package example.httpclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpClientDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpClientDemoApplication.class, args);
    }
}
~~~

### 8.5. WarehouseClient.java

~~~java
package example.httpclient;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class WarehouseClient {

    public record Item(String sku, String name, int stock) {}

    public record ReserveRequest(String sku, int count) {}

    public record Reservation(
        String reservationId,
        String status
    ) {}

    private final WebClient webClient;

    public WarehouseClient(
        WebClient.Builder builder,
        @Value("${partner.base-url}") String baseUrl
    ) {
        this.webClient = builder
            .baseUrl(baseUrl)
            .defaultHeader("X-Client-Id", "warehouse-demo")
            .build();
    }

    public Mono<Item> getItem(String sku) {
        return webClient.get()
            .uri("/v1/items/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .bodyToMono(Item.class);
    }

    public Mono<Item> getItemOrDefault(String sku) {
        return getItem(sku)
            .onErrorResume(
                WebClientResponseException.NotFound.class,
                error -> Mono.just(
                    new Item(sku, "unknown", 0)
                )
            );
    }

    public Mono<ResponseEntity<Item>> getItemEntity(String sku) {
        return webClient.get()
            .uri("/v1/items/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .toEntity(Item.class);
    }

    public Mono<Reservation> reserve(ReserveRequest request) {
        return webClient.post()
            .uri("/v1/reservations")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(Reservation.class);
    }

    public Mono<Item> getItemRetrying503(String sku) {
        return getItem(sku).retryWhen(
            Retry.backoff(2, Duration.ofMillis(20))
                .jitter(0d)
                .filter(error ->
                    error instanceof
                        WebClientResponseException.ServiceUnavailable)
        );
    }

    public Mono<Item> getItemWithDeadline(
        String sku, Duration timeout
    ) {
        return getItem(sku).timeout(timeout);
    }

    public Flux<Item> streamUpdates() {
        return webClient.get()
            .uri("/v1/updates")
            .accept(MediaType.APPLICATION_NDJSON)
            .retrieve()
            .bodyToFlux(Item.class);
    }
}
~~~

Design choices:

- Inject Spring Boot's `WebClient.Builder` to keep codecs, connector, and customization identical to the real application.
- Build `WebClient` once in the constructor; methods return cold `Mono/Flux` for test/service callers to subscribe to.
- `getItem` uses `retrieve()`'s default error mapping without hiding 4xx/5xx.
- `getItemOrDefault` falls back only on `NotFound`; 503 still emits as an error.
- `getItemRetrying503` retries only 503, up to 2 times, without retrying POST.
- `getItemWithDeadline` configures an overall timeout on the Publisher.
- `streamUpdates` decodes NDJSON item by item.
- `getItemEntity` allows asserting status, headers, and body together.

### 8.6. WarehouseClientTest.java — starting the server and injecting the base URL

~~~java
package example.httpclient;

import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

@SpringBootTest(
    classes = HttpClientDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class WarehouseClientTest {

    // Start before Spring resolves @DynamicPropertySource.
    private static final MockWebServer server = startServer();

    @Autowired
    WarehouseClient client;

    private static MockWebServer startServer() {
        MockWebServer instance = new MockWebServer();
        try {
            instance.start();
        } catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
        return instance;
    }

    @DynamicPropertySource
    static void partnerBaseUrl(DynamicPropertyRegistry registry) {
        registry.add(
            "partner.base-url",
            () -> server.url("/").toString()
        );
    }

    @AfterAll
    static void shutdownServer() throws IOException {
        server.shutdown();
    }

    private static MockResponse json(int status, String body) {
        return new MockResponse()
            .setResponseCode(status)
            .addHeader("Content-Type", "application/json")
            .setBody(body);
    }

    private static RecordedRequest nextRequest()
            throws InterruptedException {
        RecordedRequest req = server.takeRequest(
            2, TimeUnit.SECONDS
        );
        assertNotNull(req, "Expected a real HTTP request");
        return req;
    }

    @Test
    void getItemDecodesJsonAndSendsCorrectRequest()
            throws InterruptedException {
        server.enqueue(json(200,
            "{\"sku\":\"SKU-7\",\"name\":\"Keyboard\",\"stock\":12}"));

        StepVerifier.create(client.getItem("SKU-7"))
            .expectNext(new WarehouseClient.Item(
                "SKU-7", "Keyboard", 12))
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        RecordedRequest req = nextRequest();
        assertEquals("GET", req.getMethod());
        assertEquals("/v1/items/SKU-7", req.getPath());
        assertEquals("application/json", req.getHeader("Accept"));
        assertEquals(
            "warehouse-demo", req.getHeader("X-Client-Id"));
    }

    @Test
    void postReservationEncodesRequestBody()
            throws InterruptedException {
        server.enqueue(json(201,
            "{\"reservationId\":\"R-9\",\"status\":\"ACCEPTED\"}"));

        StepVerifier.create(client.reserve(
                new WarehouseClient.ReserveRequest("SKU-7", 2)))
            .expectNext(new WarehouseClient.Reservation(
                "R-9", "ACCEPTED"))
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        RecordedRequest req = nextRequest();
        assertEquals("POST", req.getMethod());
        assertEquals("/v1/reservations", req.getPath());
        assertTrue(req.getHeader("Content-Type")
            .startsWith("application/json"));

        String requestJson = req.getBody().readUtf8();
        assertTrue(requestJson.contains("\"sku\":\"SKU-7\""));
        assertTrue(requestJson.contains("\"count\":2"));
    }

    @Test
    void missingItemProduces404Exception()
            throws InterruptedException {
        server.enqueue(json(404,
            "{\"error\":\"not found\"}"));

        StepVerifier.create(client.getItem("missing"))
            .expectError(WebClientResponseException.NotFound.class)
            .verify(Duration.ofSeconds(4));

        assertEquals(
            "/v1/items/missing",
            nextRequest().getPath()
        );
    }

    @Test
    void missingItemCanUseBusinessFallback()
            throws InterruptedException {
        server.enqueue(json(404,
            "{\"error\":\"not found\"}"));

        StepVerifier.create(client.getItemOrDefault("missing"))
            .expectNext(new WarehouseClient.Item(
                "missing", "unknown", 0))
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        assertEquals(
            "/v1/items/missing",
            nextRequest().getPath()
        );
    }

    @Test
    void retry503TwiceThenSucceed()
            throws InterruptedException {
        server.enqueue(json(503,
            "{\"error\":\"temporary\"}"));
        server.enqueue(json(503,
            "{\"error\":\"temporary\"}"));
        server.enqueue(json(200,
            "{\"sku\":\"SKU-9\",\"name\":\"Mouse\",\"stock\":3}"));

        StepVerifier.create(client.getItemRetrying503("SKU-9"))
            .expectNext(new WarehouseClient.Item(
                "SKU-9", "Mouse", 3))
            .expectComplete()
            .verify(Duration.ofSeconds(6));

        for (int attempt = 0; attempt < 3; attempt++) {
            RecordedRequest req = nextRequest();
            assertEquals("GET", req.getMethod());
            assertEquals("/v1/items/SKU-9", req.getPath());
        }
    }

    @Test
    void badRequestDoesNotTrigger503Retry()
            throws InterruptedException {
        server.enqueue(json(400,
            "{\"error\":\"invalid sku\"}"));

        StepVerifier.create(client.getItemRetrying503("bad"))
            .expectError(WebClientResponseException.BadRequest.class)
            .verify(Duration.ofSeconds(4));

        assertEquals("/v1/items/bad", nextRequest().getPath());
        assertNull(server.takeRequest(200, TimeUnit.MILLISECONDS),
            "400 must not cause another attempt");
    }

    @Test
    void noContentCompletesWithoutItem()
            throws InterruptedException {
        server.enqueue(new MockResponse().setResponseCode(204));

        StepVerifier.create(client.getItem("empty"))
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        assertEquals("/v1/items/empty", nextRequest().getPath());
    }

    @Test
    void responseEntityPreservesEtag()
            throws InterruptedException {
        server.enqueue(json(200,
            "{\"sku\":\"SKU-1\",\"name\":\"Cable\",\"stock\":4}")
            .addHeader("ETag", "\"v1\""));

        StepVerifier.create(client.getItemEntity("SKU-1"))
            .assertNext(entity -> {
                assertEquals(HttpStatus.OK, entity.getStatusCode());
                assertEquals("\"v1\"",
                    entity.getHeaders().getETag());
                assertEquals(new WarehouseClient.Item(
                    "SKU-1", "Cable", 4), entity.getBody());
            })
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        assertEquals("/v1/items/SKU-1", nextRequest().getPath());
    }

    @Test
    void delayedBodyTriggersReactiveTimeout()
            throws InterruptedException {
        server.enqueue(json(200,
            "{\"sku\":\"slow\",\"name\":\"Delayed\",\"stock\":1}")
            .setBodyDelay(700, TimeUnit.MILLISECONDS));

        StepVerifier.create(client.getItemWithDeadline(
                "slow", Duration.ofMillis(150)))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(4));

        assertEquals("/v1/items/slow", nextRequest().getPath());
    }

    @Test
    void ndjsonStreamingDecodesMultipleItems()
            throws InterruptedException {
        String ndjson =
            "{\"sku\":\"A\",\"name\":\"Alpha\",\"stock\":1}\n" +
            "{\"sku\":\"B\",\"name\":\"Beta\",\"stock\":2}\n";

        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/x-ndjson")
            .setChunkedBody(ndjson, 8));

        StepVerifier.create(client.streamUpdates())
            .expectNext(
                new WarehouseClient.Item("A", "Alpha", 1),
                new WarehouseClient.Item("B", "Beta", 2))
            .expectComplete()
            .verify(Duration.ofSeconds(4));

        RecordedRequest req = nextRequest();
        assertEquals("GET", req.getMethod());
        assertEquals("/v1/updates", req.getPath());
        assertEquals(
            MediaType.APPLICATION_NDJSON_VALUE,
            req.getHeader("Accept")
        );
    }
}
~~~

### 8.7. Explaining the test design

**The mock server starts before Spring creates the client.** The static `server` field calls `startServer()`; when `@DynamicPropertySource` supplies `partner.base-url`, the URL already holds the real port. `@SpringBootTest(webEnvironment=NONE)` creates the service bean and WebClient.Builder without running an inbound application HTTP server.

**Each test enqueues its own responses and verifies received requests.** Reduces the risk of false passes from leftover data in the queue. By default JUnit Jupiter does not run test methods in parallel unless parallel execution is enabled; when enabling parallel execution, switch to per-test servers or a routing dispatcher.

**Request bodies are asserted by fields rather than JSON order.** JSON objects do not guarantee property order across serializers; tests check important content. For complex payloads, use Jackson `ObjectMapper.readTree` for semantic JSON comparison instead of raw byte-string matching.

**Retry tests check three real HTTP attempts.** If only the final DTO were asserted, retries could silently be replaced by a fallback or cached data without the test noticing.

**The timeout test delays the body after headers arrive.** Reactive `timeout` can trigger before enough body arrives to decode Item. This differs from connector connect timeout or response headers timeout.

**The NDJSON test splits objects across multiple chunks.** `setChunkedBody(ndjson,8)` does not align chunks with JSON object boundaries; the WebClient decoder must still reassemble and decode properly.

### 8.8. Running the project and expected results

Requires JDK 17+, Maven, and permission to bind a loopback port:

~~~bash
java -version
mvn test
~~~

Once dependencies resolve and tests pass, Maven normally ends with:

~~~text
Tests run: 10, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is **the expected result**, not measured output from an actual run. Maven Surefire may print class names, test timings, and other details.

The project exposes no HTTP controller of its own: `spring.main.web-application-type=none`. Its sole purpose is testing the outbound client. Tests open and close MockWebServer themselves and make no Internet API calls.

## 9. Extensions: stateful mocks, JSON schema, and protocol contracts

### 9.1. Stateful behavior and ordered responses

Suppose a reservation flow consists of:

1. POST `/v1/reservations` returns 202 Accepted with `reservationId`.
2. First GET `/v1/reservations/{id}` returns `PENDING`.
3. Second GET returns `ACCEPTED`.

You can enqueue responses in order and assert all RecordedRequests. However, if the client sends requests concurrently, the response queue is FIFO in HTTP server arrival order rather than logical business order. Use a path/state-aware Dispatcher or WireMock scenarios.

### 9.2. Verifying bidirectional contracts

A good HTTP client integration test has two kinds of assertions:

**Outgoing contract**
- Method, path, query, and percent-encoding.
- Headers, auth metadata, and content negotiation.
- Request JSON schema, field presence, data types, and serialization.

**Incoming contract**
- HTTP status mapping, including 204, 404, 429, 503.
- Charset, content type, gzip/transfer encoding when present.
- DTO mapping, nullable fields, field mismatches, and invalid JSON.
- Retry policy, timeout/cancellation, and response body release.
- Streaming item boundaries with SSE/NDJSON.

Do not invent "overly clean" JSON responses if the partner system has missing fields, unusual enums, or 429 rate limits. Obtain the partner's official contract and design representative fixtures.

### 9.3. Testing invalid JSON

~~~java
server.enqueue(new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("{not-valid-json"));
~~~

This is a dedicated sample test for decoding failure; the client `bodyToMono(Item.class)` fails in the decoder rather than with HTTP 500. Assertions should check the appropriate Spring codec exception type in your actual version rather than claiming every decode error is WebClientResponseException.

### 9.4. Testing request headers and authentication

If the client uses bearer tokens/Basic auth, the stub server records the `Authorization` header and the test asserts the fake value. Never put production tokens in test fixtures; redact tokens when printing failure logs and avoid recording full request bodies containing sensitive data.

### 9.5. Testing conditional requests, caching, and ETags

The mock server can return an `ETag` on GET and later reply 304 Not Modified if a request carries the matching `If-None-Match`. WebClient does not provide browser-like HTTP caching out of the box in all configurations; if the application wants caching, it needs an appropriate policy/service/cache layer. Test both outgoing headers and data-reuse decisions.

### 9.6. Testing wire-level compression

If the production client sends `Accept-Encoding` and the server replies with `Content-Encoding: gzip`, produce a real gzipped response body to test the connector/decoder. Never attach a gzip header to plaintext: that is a protocol-invalid fake response and can cause unrepresentative failures.

### 9.7. SSE, cancellation, and infinite streams

For `text/event-stream`, use `bodyToFlux(ServerSentEvent<T>)` or the appropriate client DSL. The mock server can keep the connection open and push events periodically. When the consumer uses `take(n)` and cancels, observe the resulting behavior; do not assume cancellation means the server sent complete. Test resource cleanup and connection reuse if those are non-functional requirements.

### 9.8. Avoiding confusion about network backpressure

A `Flux<T>` returned by `WebClient` can respect downstream demand inside the pipeline. However, when a remote server sends bytes over HTTP, network buffering and TCP flow control also participate. Do not conclude WebClient forced the server to pause item-by-item just because StepVerifier uses initial request 0. Measure throughput, memory, chunking, and cancellation at the appropriate layers.

## 10. Reliability testing: common bugs and races

### 10.1. Responses split across multiple TCP chunks

Real networks do not preserve Java/JSON message boundaries. With NDJSON, one object can span multiple chunks; bodyToFlux must decode it properly. Testing with `setChunkedBody` is a great way to catch faulty assumptions in decoders or custom parsers.

### 10.2. Slow responses and timeouts

Use `setBodyDelay` or `setHeadersDelay` with a large enough margin against the deadline to minimize flaky tests (e.g., 700ms vs 150ms). Never use narrow margins like 100ms vs 90ms because CI scheduling can make tests pass or fail erratically.

### 10.3. Unexpected disconnects and retries

With `SocketPolicy.DISCONNECT_AT_START` or `DISCONNECT_DURING_RESPONSE_BODY`, the HTTP client may reconnect/retry depending on connector and request state. Do not hardcode request counts in socket-failure tests if the connector auto-retries. Verify unsuccessful outcomes, error classification, safety, and idempotency rather than relying on Netty/OS exception messages.

### 10.4. Connection pooling and leaks

Generating many responses whose bodies remain unconsumed can exhaust connection pools. When business logic needs no body, use `toBodilessEntity()` or `exchangeToMono(response -> response.releaseBody().thenReturn(...))` per API and contract.

On error paths, ensure error bodies are read/released. Test repeated requests with a bounded connection pool to catch leaks, while using network timeouts so tests never hang indefinitely.

### 10.5. Retry storms

Continuous client retries on 503 can worsen an outage. In tests, assert attempt counts; in production, add jitter, deadlines, circuit breakers/rate limits. Honor `Retry-After` if required by the partner protocol.

### 10.6. Server state between tests

A class-shared MockWebServer records every request in its queue. Each test must consume the exact number of RecordedRequests it produces. If any test times out or cancels, leftover responses in the server queue can cause subsequent tests to receive the wrong response; consider per-test servers when strict isolation is required.

### 10.7. Unnecessary embedded HTTP servers

There is no need for `@SpringBootTest(webEnvironment=RANDOM_PORT)` just to test an outbound WebClient: you would start the application's entire inbound server, slowing tests and adding ports/state to manage. `NONE` still loads `WebClient.Builder` and service beans.

### 10.8. Statuses 204, 304, and empty responses

Distinguish clearly:
- 204: success, no body.
- 304: caching message, not a JSON payload.
- 404: `retrieve` emits an error by default, not Mono.empty.
- 5xx: HTTP error, distinct from decode/connection errors.

Use status-specific assertions; do not turn every empty body into "item not found."

## 11. WebClient test writing checklist

1. Are you testing **the outbound client** rather than confusing it with server-side WebTestClient?
2. Are you using MockWebServer/WireMock opening a real HTTP socket?
3. Do HTTP client/codecs/connector match production configuration?
4. Does the base URL use a random port injected before creating WebClient?
5. Are the actual outgoing method, path, query, headers, and request body verified?
6. Are the response DTO and necessary status/headers asserted?
7. Are 204, 404, 400, 429, and 5xx properly distinguished?
8. Are retries bounded and applied only to appropriate errors and idempotent operations?
9. Is **the actual request count** verified during retries?
10. Are timeouts configured on the client rather than only in StepVerifier?
11. Are delayed bodies or disconnects tested if required by the SLA?
12. Is chunked NDJSON/SSE tested when the client uses streaming?
13. Do tests use finite timeouts when awaiting requests/verifiers?
14. Does each test control its response queue, request queue, and server lifecycle?
15. Are tests independent of the Internet, real credentials, and real data?
16. Are assumptions that chunk boundaries equal item boundaries avoided?
17. Are error bodies consumed/released to prevent leaks?
18. Do parallel tests have server/dispatcher isolation?
19. Are malformed responses, unknown fields, and content-type mismatches checked?
20. Are unit tests, mock HTTP integration tests, contract tests, and end-to-end tests separated?

## 12. Self-check exercises

1. Why is mocking `WebClient.get()` with Mockito insufficient? **It does not test HTTP sockets, codecs, connectors, or wire semantics.**
2. Does `MockWebServer` open a real HTTP server? **Yes, on a loopback port.**
3. What does `server.enqueue` do? **Puts a MockResponse into the queue for the next request.**
4. What does `server.takeRequest` do? **Retrieves the actually received RecordedRequest to assert method/path/headers/body.**
5. Why use `server.url("/")`? **It contains the server's actual address and port.**
6. Does the response queue automatically match the URI? **No, assert RecordedRequest or use Dispatcher/WireMock.**
7. What does `retrieve()` do by default on 404/503? **Emits the corresponding WebClientResponseException.**
8. What does 204 with bodyToMono emit? **Completes empty when there is no body.**
9. How many total requests at most does `Retry.backoff(2,...)` send? **Three: one initial request and two retries if policy permits.**
10. Why avoid blindly retrying POST? **Risk of duplicate side effects.**
11. How does `Mono.timeout` differ from connect timeout? **It bounds the Publisher's total response time rather than just the TCP connect phase.**
12. Does `StepVerifier.verify(Duration)` replace production timeouts? **No, it only bounds the test duration.**
13. Why must tests subscribe to the Publisher? **Reactive WebClient is lazy.**
14. What does `setBodyDelay` simulate? **HTTP body arriving late after status/headers are sent.**
15. Which bug does `setChunkedBody` help catch? **The false assumption that one TCP/HTTP chunk equals one JSON object.**
16. What media type does NDJSON use? **application/x-ndjson.**
17. Does `WebTestClient.bindToController` replace an outbound mock server? **No, it primarily tests inbound WebFlux handlers.**
18. When can `exchangeToMono` release an unused body? **After the Publisher returned by the lambda completes per contract.**
19. How does HTTP 503 differ from a socket reset? **503 is an HTTP response with a status; a reset is a transport failure.**
20. Does a mock HTTP server prove the partner's real API is always compatible? **No; contract/sandbox tests are still needed.**
21. What should be used when multiple requests run concurrently? **Dispatcher/WireMock stubs or per-server/per-test isolation.**
22. Why avoid putting production tokens in mock fixtures? **Protects secrets and prevents leaks in logs.**

## 13. Summary and references

- To test WebClient realistically, use a loopback HTTP mock server instead of mocking every fluent API method.
- MockWebServer/WireMock lets you verify **outgoing requests** and **incoming responses** over real HTTP.
- `enqueue` provides responses and `takeRequest` captures requests; always check path/headers/body because the queue does not auto-match contracts.
- `retrieve` turns 4xx/5xx into WebClientResponseException by default; 204 normally completes empty.
- Retry tests must verify the number of HTTP attempts, not just the final DTO; never retry non-idempotent write operations.
- `setBodyDelay`, `setHeadersDelay`, `setSocketPolicy`, and `setChunkedBody` simulate critical network behaviors.
- `StepVerifier` creates a subscription to verify reactive signals; `verify(Duration)` prevents hanging tests but does not replace client timeouts.
- For NDJSON/SSE, do not assume each chunk aligns with one item; test streaming and cancellation.
- `exchangeToMono/Flux` and `retrieve` handle bodies/resources per contract to prevent connection leaks.
- Tests should use random ports, clear server lifecycles, independent response queues, and no Internet access.

**Official documentation:**

1. [Spring Framework 6.2 — WebClient Testing](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-testing.html): recommends MockWebServer/WireMock as an HTTP mock server for outbound WebClient.
2. [Spring Framework 6.2 — WebClient retrieve](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-retrieve.html): 4xx/5xx, onStatus, bodyToMono/Flux.
3. [Spring Framework 6.2 — WebClient exchange](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-exchange.html): exchangeToMono/Flux and body release lifecycle.
4. [Spring Framework 6.2 — WebClient Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html): connectors, Reactor Netty, timeouts, and resources.
5. [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): WebClient.Builder auto-configuration/prototype.
6. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest NONE vs RANDOM_PORT.
7. [OkHttp MockWebServer 4.x](https://square.github.io/okhttp/4.x/mockwebserver/): MockWebServer, MockResponse, RecordedRequest, and SocketPolicy.
8. [WireMock Reference](https://wiremock.org/docs/): stub matching, scenarios, request journal, faults, and delays.
9. [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, demand, timeouts, and virtual time.
