# MockRestServiceServer for Synchronous Clients and Mock Servers for WebClient

## 1. What must be mocked when testing an HTTP client?

When a Spring application calls an external HTTP service, service unit tests usually should not depend on the live API: networks can drop, data can change, authentication expires, and rate limits, cost, and latency make tests flaky. The goal is testing whether **the application's own HTTP client code** builds the right request and interprets the response properly against a controlled server side.

A sample contract: the app calls a catalog API:
- **GET /api/books/7?lang=en**, header **X-Tenant: training**, Accept: application/json. Server responds **200**, body **{"id":7,"title":"Spring"}**.
- **POST /api/books**, Content-Type: application/json, body **{"title":"New Book"}**; server responds **201**, Location: /api/books/8, and the new book JSON.
- When the server responds **404**, the client must propagate the error or map it per business policy; tests must not always stub 200.

Here we test the **outgoing client**. Do not confuse this with **MockMvc** or **WebTestClient.bindToController(...)**: those two APIs test **server-side controllers/handlers**. The tools in this lesson act on the client side producing outbound HTTP requests.

### Two simulation approaches

1. **Spring Test's `MockRestServiceServer`**: attaches a mock request factory to synchronous **RestClient** or **RestTemplate**. The client still runs through Spring's URI construction, headers, and serialization/deserialization, yet **no real HTTP connection is opened**. Tests declare expectations with **expect(...).andRespond(...)**, invoke real code, and call **verify()**.
2. **A mock HTTP server on a loopback port**: such as **OkHttp MockWebServer** or **WireMock**. It listens for real HTTP on localhost, returns preconfigured responses, and records requests for inspection. **WebClient** calls the mock server through a real HTTP client/connector, making it better suited for testing encoding, timeouts, networking, connection behavior, or streaming.

Spring Framework officially recommends a mock web server when full transport/network testing is needed; **MockRestServiceServer** remains useful, fast, and well isolated for RestTemplate/RestClient. Pick the tool according to what you want to prove, and never use HTTP mocks to replace all business integration tests.

## 2. Comparing scope, speed, and reliability

| Criterion | MockRestServiceServer | MockWebServer or WireMock |
| --- | --- | --- |
| Typical target under test | RestClient, RestTemplate (synchronous) | WebClient, RestClient, RestTemplate, HTTP service proxies |
| Real HTTP socket | No | Yes: mock server opens a localhost port |
| Real HTTP client connector | Replaced by test mock request factory | Can match production configuration |
| Behavior declaration | **expect** + **andRespond** | Enqueue/dispatcher/stub HTTP responses |
| Request inspection | Spring request matchers, counts, and verify() | RecordedRequest / mock server verification API |
| Serialization + headers testing | Yes | Yes |
| Connect/response timeout, transfer encoding | Incomplete | Better suited; depends on connector and fixtures |
| Resources requiring cleanup | Expectation state between tests | Must shut down server/port and clear request queue |
| Ideal use case | Fast, deterministic synchronous client logic tests | Reactive WebClient and network behavior tests |
| Shared limitation | Does not verify real external Internet APIs | Still does not prove the real API matches schema and deployment |

**A mock server** is not the same as **mocking a Java interface**. When mocking a repository/client interface with Mockito, we never learn whether URLs, queries, HTTP methods, or Content-Type are encoded properly. In this lesson, call **real RestClient/WebClient code** to observe the outbound HTTP contract.

## 3. MockRestServiceServer: binding to RestClient.Builder in the right order

Since Spring Framework 6.1, **MockRestServiceServer.bindTo(RestClient.Builder)** supports RestClient. Example:

~~~java
RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://catalog.example.test");

MockRestServiceServer server =
    MockRestServiceServer.bindTo(builder).build();

RestClient client = builder.build();
~~~

**Critical point:** use the **same RestClient.Builder** to create the mock server and only *afterward* call **builder.build()**. If you call **build()** first or the service creates an independent builder/client, the mock request factory will not sit on the client your code actually uses. Host **catalog.example.test** is strictly an example host and is never contacted over the network in MockRestServiceServer tests when bound properly.

A conceptually complete test:

~~~java
server.expect(requestTo(
        "https://catalog.example.test/api/books/7?lang=en"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("X-Tenant", "training"))
    .andRespond(withSuccess(
        "{\"id\":7,\"title\":\"Spring\"}",
        MediaType.APPLICATION_JSON));

Book result = client.get()
    .uri("/api/books/{id}?lang={lang}", 7, "en")
    .header("X-Tenant", "training")
    .retrieve()
    .body(Book.class);

assertEquals(new Book(7, "Spring"), result);
server.verify();
~~~

This sample needs static imports **MockRestRequestMatchers.requestTo/method/header**, **MockRestResponseCreators.withSuccess**, **Assertions.assertEquals**, and the corresponding Spring types.

### Internal workflow

~~~text
JUnit test
   |
   | register expect(requestTo(...)), andExpect(...), andRespond(...)
   v
MockRestServiceServer
   |
   | bindTo(RestClient.Builder), replaces ClientHttpRequestFactory
   v
Application code calls real RestClient API
   |
   | builds URI + headers + JSON encoding
   v
Mock ClientHttpRequestFactory
   |
   | matches request against expectations, returns stub response
   v
RestClient decodes JSON response into DTO
   |
   v
JUnit asserts DTO/exception + mockServer.verify()
~~~

There is no real TCP/HTTP server in this flow. Thus, to test TLS handling, proxies, connect timeouts, or differences across HTTP clients (Reactor Netty, JDK, Apache), use a mock web server or integration environment.

## 4. Declaring expectations: URL, method, headers, and body

A MockRestServiceServer expectation typically includes:
- **requestTo(String/URI)** or custom request matcher logic.
- **method(HttpMethod.GET/POST/PUT...)**.
- **header(...)**, **headerDoesNotExist(...)**, **queryParam(...)** (depending on Spring version), **content().contentType(...)**, **content().json(...)**, **content().string(...)**.
- **andRespond(withSuccess(...))**, **withStatus(HttpStatus...)**, **withServerError()**, and other response creators.

JSON POST example:

~~~java
server.expect(requestTo(
        "https://catalog.example.test/api/books"))
    .andExpect(method(HttpMethod.POST))
    .andExpect(header("X-Tenant", "training"))
    .andExpect(content().contentType(MediaType.APPLICATION_JSON))
    .andExpect(content().json("{\"title\":\"New Book\"}"))
    .andRespond(withStatus(HttpStatus.CREATED)
        .contentType(MediaType.APPLICATION_JSON)
        .header("Location", "/api/books/8")
        .body("{\"id\":8,\"title\":\"New Book\"}"));
~~~

**Request headers vs. response headers**:
- **.andExpect(header("X-Tenant","training"))** checks the header **sent by the client**.
- **.andRespond(... .header("Location", ...))** sets the header **returned by the mock server**.
- If code needs to read **Location**, it must read response headers—e.g., via **toEntity(Book.class)**—instead of only **body(Book.class)**.

**content().json(...)** compares JSON structurally, preventing test failures merely from field ordering or whitespace. For strict contracts, add checks for unexpected fields/data types or use strict matchers if supported by your Spring/Test dependencies.

### Checking call counts and ordering

By default **MockRestServiceServer** expects requests in registration order (with some exceptions when an expectation allows multiple invocations). You can specify counts:

~~~java
server.expect(ExpectedCount.times(2),
        requestTo("https://catalog.example.test/api/books/7?lang=en"))
    .andRespond(withSuccess(
        "{\"id\":7,\"title\":\"Spring\"}",
        MediaType.APPLICATION_JSON));
~~~

When testing retries, specify the exact expected request count. If the app calls once when two calls are expected, **server.verify()** fails. When testing independent requests without guaranteed ordering, the builder supports **ignoreExpectOrder(true)**; still prove no extra or missing requests occurred.

If multiple expectations share a URL, distinguish them clearly by headers/body. Never use overly broad matchers (checking only host) that pass even when hitting the wrong endpoint.

### Returning 404, 429, 500 errors

~~~java
server.expect(requestTo(
        "https://catalog.example.test/api/books/404?lang=vi"))
    .andRespond(withStatus(HttpStatus.NOT_FOUND)
        .contentType(MediaType.APPLICATION_JSON)
        .body("{\"message\":\"Not found\"}"));
~~~

With **RestClient.retrieve()**, 4xx/5xx responses by default become **RestClientResponseException** (such as **HttpClientErrorException.NotFound**). Assertion style:

~~~java
assertThrows(HttpClientErrorException.NotFound.class,
    () -> catalog.find(404, "vi"));
server.verify();
~~~

To test retry/bulkhead/circuit-breaker behavior, configure it genuinely on the client/service under test. MockRestServiceServer does not retry on its own and does not turn 503 into 200. Do not overuse successful stub responses when your goal is testing error handling.

## 5. Why should WebClient use a mock web server?

**WebClient** works through reactive **Mono/Flux** APIs and an HTTP connector such as Reactor Netty. **MockRestServiceServer.bindTo(RestClient.Builder)** does not hook directly into WebClient the way it does RestClient. You could swap WebClient's ExchangeFunction with a manual mock, but that bypasses transport and risks testing your mock instead of real requests.

A **mock HTTP server** accepts real TCP/HTTP requests from WebClient on localhost; it lets you verify:

1. URL/path/query encoding produced by WebClient.
2. HTTP verb, headers, Content-Type, and JSON request bytes.
3. Status codes and JSON responses decoded by WebClient codecs.
4. Timeouts, connection resets, chunked transfer, or delayed responses when fixtures are configured.
5. NDJSON/SSE streams frame by frame or chunk by chunk with bounded timing.

Spring Framework recommends **OkHttp MockWebServer** or **WireMock** for testing WebClient. Do not confuse this with **WebTestClient.bindToController**: that tool builds a mock server framework for testing *server-side code*; to test a WebClient service like production, point a real WebClient at the mock HTTP server's localhost URL.

## 6. MockWebServer: enqueue(response) and takeRequest()

**OkHttp MockWebServer 4.12.0** Java API:

~~~java
MockWebServer server = new MockWebServer();
server.start();

try {
    server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":7,\"title\":\"Spring\"}"));

    WebClient client = WebClient.builder()
        .baseUrl(server.url("/").toString())
        .build();

    Book book = client.get()
        .uri("/api/books/{id}?lang={lang}", 7, "en")
        .header("X-Tenant", "training")
        .retrieve()
        .bodyToMono(Book.class)
        .block(Duration.ofSeconds(5));

    RecordedRequest request =
        server.takeRequest(5, TimeUnit.SECONDS);

    assertNotNull(request);
    assertEquals("GET", request.getMethod());
    assertEquals("/api/books/7?lang=en", request.getPath());
    assertEquals("training", request.getHeader("X-Tenant"));
    assertEquals(new Book(7, "Spring"), book);
} finally {
    server.shutdown();
}
~~~

Imports include:
- **okhttp3.mockwebserver.MockWebServer**, **MockResponse**, **RecordedRequest**.
- **org.springframework.web.reactive.function.client.WebClient**.
- **java.time.Duration**, **java.util.concurrent.TimeUnit**, and JUnit assertions.

**enqueue** queues stub responses in order. **takeRequest** dequeues and returns a recorded request; use the timeout overload to avoid hanging forever when WebClient never sends anything because subscription was forgotten. **server.url("/")** builds a URL with the randomly assigned localhost port, preventing fixed-port conflicts.

### Common mistake: Mono only runs when subscribed

~~~java
Mono<Book> pending = client.get()
    .uri("/api/books/7")
    .retrieve()
    .bodyToMono(Book.class);

// Only builds the pipeline; no HTTP request is sent yet.
~~~

Calling **takeRequest()** immediately afterward without subscribing causes the test to hang/time out because no request was ever sent. In synchronous tests, use **block(Duration.ofSeconds(5))** at the test boundary, or **StepVerifier** when **reactor-test** is present:

~~~java
StepVerifier.create(pending)
    .expectNextMatches(book -> book.id() == 7)
    .verifyComplete();
~~~

StepVerifier is only a fragment when the dependency and **reactor.test.StepVerifier** import are present. For infinite streams, use take(n), verification bounds, and subscription cleanup rather than unbounded collectList().

### How does MockWebServer differ from the real remote API?

MockWebServer plays the role of the *remote HTTP server*. **WebClient still uses its real HTTP connector** and runs real HTTP calls, codecs, and lifecycle. Still:
- The real production remote API may require TLS, OAuth, or proxies and differ in JSON content.
- Test fixtures are only as accurate as the responses authored in the test.
- Localhost has much lower latency than the Internet. Timeout tests must simulate slow responses intentionally rather than assuming the network is slow.

## 7. Runnable Java 17 project: RestClient + MockRestServiceServer, WebClient + MockWebServer

This example uses **Spring Boot 3.5.0** (Spring Framework 6.2), **JDK 17+**, JUnit Jupiter, Spring Test, and **MockWebServer 4.12.0**. All tests instantiate clients and mocks directly, requiring no running Spring Boot server or runtime Internet access (Maven still needs to download dependencies the first time).

Structure:

~~~text
client-http-contract-tests/
├── pom.xml
├── src/main/java/demo/
│   ├── Book.java
│   ├── CreateBook.java
│   ├── CatalogRestClient.java
│   └── CatalogWebClient.java
└── src/test/java/demo/
    ├── CatalogRestClientTest.java
    └── CatalogWebClientTest.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>client-http-contract-tests</artifactId>
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
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**src/main/java/demo/Book.java**:

~~~java
package demo;

public record Book(long id, String title) {}
~~~

**src/main/java/demo/CreateBook.java**:

~~~java
package demo;

public record CreateBook(String title) {}
~~~

**src/main/java/demo/CatalogRestClient.java**:

~~~java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class CatalogRestClient {
    private final RestClient client;

    public CatalogRestClient(RestClient client) {
        this.client = client;
    }

    public Book find(long id, String lang) {
        return client.get()
            .uri("/api/books/{id}?lang={lang}", id, lang)
            .header("X-Tenant", "training")
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(Book.class);
    }

    public Book create(CreateBook body) {
        return client.post()
            .uri("/api/books")
            .header("X-Tenant", "training")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .body(body)
            .retrieve()
            .body(Book.class);
    }
}
~~~

**src/main/java/demo/CatalogWebClient.java**:

~~~java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public final class CatalogWebClient {
    private final WebClient client;

    public CatalogWebClient(WebClient client) {
        this.client = client;
    }

    public Mono<Book> find(long id, String lang) {
        return client.get()
            .uri("/api/books/{id}?lang={lang}", id, lang)
            .header("X-Tenant", "training")
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .bodyToMono(Book.class);
    }

    public Mono<Book> create(CreateBook body) {
        return client.post()
            .uri("/api/books")
            .header("X-Tenant", "training")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(body)
            .retrieve()
            .bodyToMono(Book.class);
    }
}
~~~

Both classes share DTOs yet have different semantics:
- **CatalogRestClient.find** is synchronous, blocks for the response, and returns Book.
- **CatalogWebClient.find** returns **Mono<Book>**; HTTP runs upon subscription.
- **create** sends JSON using Jackson converters/codecs provided by the Spring WebFlux starter.
- HTTP 4xx/5xx errors in **retrieve()** default to exceptions/error signals; tests must verify error paths.

### 7.1 Synchronous test with MockRestServiceServer

**src/test/java/demo/CatalogRestClientTest.java**:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class CatalogRestClientTest {

    private MockRestServiceServer server;
    private CatalogRestClient catalog;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://catalog.example.test");
        server = MockRestServiceServer.bindTo(builder).build();
        catalog = new CatalogRestClient(builder.build());
    }

    @Test
    void getAssertsMethodUrlHeaderAndParsesJson() {
        server.expect(requestTo(
                "https://catalog.example.test/api/books/7?lang=en"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header("X-Tenant", "training"))
            .andRespond(withSuccess(
                "{\"id\":7,\"title\":\"Spring\"}",
                MediaType.APPLICATION_JSON));

        Book book = catalog.find(7, "en");

        assertEquals(new Book(7, "Spring"), book);
        server.verify();
    }

    @Test
    void postAssertsJsonBodyAndParsesCreatedResponse() {
        server.expect(requestTo(
                "https://catalog.example.test/api/books"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header("X-Tenant", "training"))
            .andExpect(content().contentType(MediaType.APPLICATION_JSON))
            .andExpect(content().json("{\"title\":\"New Book\"}"))
            .andRespond(withStatus(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .header("Location", "/api/books/8")
                .body("{\"id\":8,\"title\":\"New Book\"}"));

        Book created = catalog.create(new CreateBook("New Book"));

        assertEquals(new Book(8, "New Book"), created);
        server.verify();
    }

    @Test
    void notFoundPropagatesHttp404() {
        server.expect(requestTo(
                "https://catalog.example.test/api/books/404?lang=vi"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(
            HttpClientErrorException.NotFound.class,
            () -> catalog.find(404, "vi"));
        server.verify();
    }
}
~~~

Characteristics:
- **@BeforeEach** creates a fresh builder and mock server per test, preventing stale expectations from leaking into subsequent tests.
- You must call **MockRestServiceServer.bindTo(builder)** *before* **builder.build()** so the client uses the mock request factory.
- **expect** asserts outbound requests, **andRespond** stubs inbound responses, **assertEquals** checks decoded client data, and **verify()** confirms expectations were met.
- The POST test returns a Location header, yet **CatalogRestClient.create** currently returns only the body; this test does not verify whether the client reads Location. If business logic uses that header, update the implementation to **toEntity(Book.class)** or a response type exposing headers and assert accordingly.
- The 404 test asserts the exact exception subtype for default Spring config; custom status handlers may map it to another domain exception.

### 7.2 Testing WebClient with a real MockWebServer on loopback

**src/test/java/demo/CatalogWebClientTest.java**:

~~~java
package demo;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import static org.junit.jupiter.api.Assertions.*;

class CatalogWebClientTest {

    private MockWebServer server;
    private CatalogWebClient catalog;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient client = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .build();

        catalog = new CatalogWebClient(client);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void getUsesHttpTransportAndParsesJson() throws Exception {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"id\":7,\"title\":\"Spring\"}"));

        Book book = catalog.find(7, "en")
            .block(Duration.ofSeconds(5));

        assertEquals(new Book(7, "Spring"), book);

        RecordedRequest req = server.takeRequest(5, TimeUnit.SECONDS);
        assertNotNull(req);
        assertEquals("GET", req.getMethod());
        assertEquals("/api/books/7?lang=en", req.getPath());
        assertEquals("training", req.getHeader("X-Tenant"));
    }

    @Test
    void postEncodesJsonRequest() throws Exception {
        server.enqueue(new MockResponse()
            .setResponseCode(201)
            .addHeader("Content-Type", "application/json")
            .addHeader("Location", "/api/books/8")
            .setBody("{\"id\":8,\"title\":\"New Book\"}"));

        Book book = catalog.create(new CreateBook("New Book"))
            .block(Duration.ofSeconds(5));

        assertEquals(new Book(8, "New Book"), book);

        RecordedRequest req = server.takeRequest(5, TimeUnit.SECONDS);
        assertNotNull(req);
        assertEquals("POST", req.getMethod());
        assertEquals("/api/books", req.getPath());
        assertEquals("training", req.getHeader("X-Tenant"));
        assertTrue(req.getHeader("Content-Type")
            .startsWith("application/json"));
        assertEquals("{\"title\":\"New Book\"}",
            req.getBody().readUtf8());
    }

    @Test
    void notFoundProducesReactiveError() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(404));

        assertThrows(
            WebClientResponseException.NotFound.class,
            () -> catalog.find(404, "vi")
                .block(Duration.ofSeconds(5)));

        RecordedRequest req = server.takeRequest(5, TimeUnit.SECONDS);
        assertNotNull(req);
        assertEquals("/api/books/404?lang=vi", req.getPath());
    }
}
~~~

**Note how this test checks real HTTP requests:**
- **server.start()** allocates a random localhost port.
- **baseUrl(server.url("/").toString())** ensures WebClient hits the mock server rather than catalog.example.test.
- **server.enqueue** prepares the response for the corresponding call.
- **Mono.block(Duration)** subscribes and waits on the *JUnit test thread*, not the WebFlux event loop.
- **takeRequest(5, TimeUnit.SECONDS)** prevents waiting indefinitely if no request arrives.
- **getMethod, getPath, getHeader, getBody().readUtf8()** are real HTTP details recorded by the mock server after receiving the request.
- **@AfterEach** closes the mock server socket to avoid port/thread leaks.
- On HTTP POST, inspect both the **request body** and **response body**: a test asserting only the returned Book could miss a bug where the client sent the wrong title.

The JUnit test checks the POST JSON body as an exact string because the demo DTO has one stable field and Jackson emits simple JSON. For payloads with multiple fields whose order may vary, parse JSON with ObjectMapper/JsonNode and compare structurally instead of raw strings.

### 7.3 Running and expected results

In directory **client-http-contract-tests**, with JDK 17+ and Maven installed, run:

~~~bash
mvn test
~~~

The project has **6 @Test methods**: three RestClient tests and three WebClient tests. When dependencies, JDK, and localhost loopback are available, tests should finish with **0 failures** and **0 errors**, Maven **BUILD SUCCESS**. These are expected criteria for the example; do not assume Maven has been executed in any environment merely because code appears in the documentation.

If tests fail:
- Read the JUnit stack trace to pinpoint the first failing assertion or HTTP call.
- For MockRestServiceServer, verify the client was built from the exact RestClient.Builder that was bound.
- For MockWebServer, check the localhost URL, enqueue order before subscription, takeRequest timeout, and response Content-Type.
- Check Maven dependencies and Spring versions if an API method is missing.

## 8. Testing errors, timeouts, and retries in a controlled way

### 8.1 Error responses from a mock server

A RestClient test can use:

~~~java
server.expect(requestTo(
        "https://catalog.example.test/api/books/7?lang=en"))
    .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE)
        .contentType(MediaType.APPLICATION_JSON)
        .body("{\"error\":\"temporarily unavailable\"}"));
~~~

A WebClient test can use:

~~~java
server.enqueue(new MockResponse()
    .setResponseCode(503)
    .addHeader("Content-Type", "application/json")
    .setBody("{\"error\":\"temporarily unavailable\"}"));
~~~

The default expectation is that HTTP errors enter the exception/error signal path. If the app has **503** retry logic, tests should enqueue a response sequence (503 then 200), assert the call count, and enforce a bounded retry policy. Never design tests that retry endlessly.

### 8.2 Network timeouts and slow responses

MockRestServiceServer replaces transport with a mock request factory, so **it is unsuitable for proving real TCP connect timeouts or read timeouts**. MockWebServer can simulate slow responses:

~~~java
server.enqueue(new MockResponse()
    .setResponseCode(200)
    .setBody("{\"id\":7,\"title\":\"Spring\"}")
    .setBodyDelay(2, TimeUnit.SECONDS)
    .addHeader("Content-Type", "application/json"));
~~~

This fragment illustrates **setBodyDelay**; for a deterministic test, configure the timeout on the **WebClient HTTP connector or Reactor pipeline** below the delay, then assert the expected error type. Without an application-side timeout, a server delayed by two seconds can still succeed. Avoid **Thread.sleep()** just to guess network timing; mock servers provide controlled delay primitives.

Example WebClient pipeline with an application timeout:

~~~java
Mono<Book> result = catalog.find(7, "en")
    .timeout(Duration.ofMillis(200));
~~~

On subscription, **TimeoutException** (wrapped into Reactor's error signal) can occur when no value arrives within 200 ms. However, short durations can be flaky on slow CI; use clear margins and connector-level timeouts when testing the transport layer. Cancel tasks and shut down the server after the test.

### 8.3 Retries and idempotency

When retry is part of the contract, e.g., an idempotent GET:

~~~java
Mono<Book> result = catalog.find(7, "en")
    .retryWhen(
        Retry.backoff(1, Duration.ofMillis(100))
            .filter(error ->
                error instanceof WebClientResponseException.ServiceUnavailable));
~~~

This fragment needs imports **reactor.util.retry.Retry**, **java.time.Duration**, and WebClientResponseException types. With MockWebServer, enqueue **503** and **200** in sequence and assert exactly **two RecordedRequests**. With RestClient, retries usually live in the service layer, Resilience4j, or HTTP client policy; MockRestServiceServer offers **ExpectedCount.times(2)** to verify request counts when the app actually retries.

Never unconditionally retry a resource-creating POST: the remote server may already have created the resource while the client lost the connection before receiving the response. Require an idempotency key or deduplication mechanism before attempting retries.

## 9. Verifying JSON and headers on both sides

Four assertion layers must not be mixed up:

| Layer | Using MockRestServiceServer | Using MockWebServer |
| --- | --- | --- |
| Request method + URI | method(...), requestTo(...) | RecordedRequest.getMethod(), getPath() |
| Request headers | header(...), content().contentType(...) | RecordedRequest.getHeader(...) |
| Request JSON body | content().json(expected) | RecordedRequest.getBody() and JSON parser |
| Response status/headers/body | andRespond(...) creates stub; client asserts result/exception | enqueue(...) creates stub; client asserts result/exception |

**Remember data direction**:
- **Expect/RecordedRequest** is what the client **sends to the server**.
- **Stub response** is what the mock server **returns to the client**.
- **Java result assertions** prove the client code decoded the response and handled the status.

For example, a test stubbing status 201 and Location only truly protects Location consumption if the client returns **ResponseEntity<T>** or exposes the response header. If the implementation uses only **body(T.class)**, the test checks the POST body and DTO yet **cannot** prove the application used Location.

### JSON with dynamic fields

For responses containing timestamps, request IDs, or unordered arrays:
- Assert required fields, types, and meaningful constraints.
- Avoid hard-coding live timestamps, random UUIDs, or changing request IDs.
- For request bodies, use **ObjectMapper.readTree(...)** for structural JSON comparisons when key ordering does not matter.
- For binary/multipart data, compare Content-Type, part names, boundaries, and bytes per contract; never convert arbitrary files to UTF-8 Strings.

## 10. Multiple requests, concurrency, and isolation

### MockRestServiceServer

- **One dedicated mock server/RestClient.Builder per test** prevents expectation state from carrying over.
- **server.verify()** must be called to confirm the expected number of requests ran, even if the Java return value already matches.
- By default tests match expectations in order; when concurrency leaves ordering unspecified, use **ignoreExpectOrder(true)** or test threads in isolation.
- **ExpectedCount** checks request counts, but does not replace checking headers and bodies for each request type.

### MockWebServer

- **One instance per test** (or per test class with strict cleanup), closing sockets with **shutdown()**.
- Enqueue orders responses FIFO; tests firing parallel requests can consume the response queue out of expected order. When path/header routing is needed, use a custom **Dispatcher** or WireMock stubs.
- Avoid leaving unconsumed requests in the queue between tests. Always **takeRequest** with a finite timeout.
- Even mock HTTP server tests can have race/timing issues if subscriptions are missing or timeouts are too tight. Manage publisher lifecycles explicitly.
- When testing multiple network failures, WebClient may retry or the connector may reconnect depending on config: check the **actual request count** to catch duplicate invocations.

### How to point the base URL at the mock server?

A common anti-pattern:

~~~java
WebClient client = WebClient.create("https://api.company.com");
// MockWebServer is only started on localhost afterward.
// This WebClient still calls api.company.com and does not redirect automatically.
~~~

Correct approach: create the mock server first, grab its URL, and pass it into **WebClient.Builder.baseUrl(...)**. In real Spring Boot projects, inject the base URL via **@ConfigurationProperties** so production and tests share the same factory, with tests overriding only the property value.

Never couple tests to port 8080 or live external services. A random localhost port per test keeps CI stable and lets suites run in parallel.

## 11. Mock HTTP servers with WireMock

**WireMock** also spins up an HTTP mock server and excels at request matching, scenarios/state, query/header/JSON mappings, fault simulation, and recording. Useful when:
- Many endpoints/stubs and complex HTTP bodies are required.
- Mocking APIs by detailed path/query/auth criteria.
- Managing separate JSON fixtures, 429 → 200 scenarios, or integrating across test suites.
- Testing both RestClient and WebClient against one HTTP stub server instead of using MockRestServiceServer solely for RestClient.

Illustrative WireMock-style snippet:

~~~java
stubFor(get(urlPathEqualTo("/api/books/7"))
    .withQueryParam("lang", equalTo("en"))
    .withHeader("X-Tenant", equalTo("training"))
    .willReturn(okJson("{\"id\":7,\"title\":\"Spring\"}")));
~~~

This is a **fragment**; you must start a WireMockServer, configure WebClient's base URL to point to it, import the DSL for your WireMock version, and clean up resources afterward. Do not paste this verbatim into the MockWebServer demo in section 7 because they are independent libraries. When verification is needed:

~~~java
verify(getRequestedFor(urlPathEqualTo("/api/books/7"))
    .withQueryParam("lang", equalTo("en")));
~~~

WireMock serves real HTTP responses on localhost, so it shares MockWebServer's transport characteristics. Choose one primary mock server library per test suite to avoid overlapping fixture sources.

## 12. HTTP service interfaces can also be tested

If a Spring app uses declarative **@HttpExchange** interfaces built with **HttpServiceProxyFactory**, the HTTP contract should still be tested:

~~~java
@HttpExchange(url = "/api/books")
interface BookApi {
    @GetExchange("/{id}")
    Book find(@PathVariable("id") long id);
}
~~~

For synchronous interfaces:
1. Create a **RestClient.Builder** and bind **MockRestServiceServer** before building RestClient.
2. Create **RestClientAdapter.create(restClient)**, **HttpServiceProxyFactory.builderFor(adapter)**, and proxy **createClient(BookApi.class)**.
3. Register expectations, invoke the proxy, assert Book, and call **verify()**.

For reactive interfaces returning **Mono<Book>**:
1. Start **MockWebServer** or WireMock.
2. Build **WebClient** with the mock server's base URL and **WebClientAdapter.create(webClient)**.
3. Create the proxy for the reactive interface, subscribe/use StepVerifier, and verify **RecordedRequest** and response values.

This way tests still verify **annotation mappings, URI templates, headers, and JSON** produced by the proxy. Mocking BookApi directly with Mockito only tests business logic calling the interface, without verifying annotation/proxy transport.

## 13. Common pitfalls and fixes

| Symptom | Cause | How to check |
| --- | --- | --- |
| MockRestServiceServer receives no requests | RestClient built before binding or from a different builder | Bind the exact RestClient.Builder before build() |
| Test hits the Internet despite thinking it's mocked | URL/client not pointed at mock server properly | Log/check baseUrl and verify RecordedRequest |
| **verify()** reports expected but not executed | Code wasn't actually called or expected count is wrong | Invoke service and assert request counts |
| POST JSON test fails despite valid semantics | Comparing raw JSON strings with different field order/whitespace | Use content().json or parse JsonNode |
| MockWebServer **takeRequest** times out | Mono not subscribed, wrong URL, or connector error | block/StepVerifier, server.url, check exceptions |
| WebClient hits Codec/JSON decode error | Response missing JSON Content-Type or mismatched schema | Add proper header and DTO-compatible body |
| HTTP 404 treated as null | Default retrieve() emits status errors | Test exception/error signals and custom handlers if present |
| Timeout test never triggers | Delayed server without configuring client timeout | Set connector or Reactor timeout properly |
| Flaky timeout tests | Timeout too short, slow CI, test uses sleep | Use mock delays with margin and bounded waits |
| Test receives wrong stub response | Concurrent requests consume FIFO queue out of order | Use Dispatcher/WireMock matching by URI |
| Extra HTTP requests after retry | Client retries or logic invoked multiple times | Verify call counts and inspect recorded requests |
| Cannot read response Location | Implementation uses bodyToMono/body(...) only, discarding headers | Use toEntity/ResponseEntity |
| Connection errors after tests | Forgot to call server.shutdown | Use @AfterEach/finally |
| Fast tests pass yet production fails TLS | MockRestServiceServer has no transport; localhost differs from prod | Add integration/TLS config tests when needed |

## 14. Project implementation checklist

1. Identify what is being tested: client logic, URI/headers/JSON, status handling, or network conditions.
2. For synchronous **RestClient/RestTemplate**, prefer **MockRestServiceServer** for fast, deterministic HTTP contract tests.
3. For **WebClient**, use **MockWebServer/WireMock** to exercise real HTTP transport on localhost.
4. Bind the same **RestClient.Builder** before building; WebClient must take its base URL from the mock server's dynamic URL.
5. Declare expectations/stub responses before invoking the service; for WebClient, ensure subscription occurs.
6. Check request method, URL/query, headers, content-type, and body thoroughly, then assert response DTO/status/errors.
7. Verify call counts, retries, headers, and resource cleanup. Never assert only Java return values.
8. Add tests for 2xx, 4xx, 5xx, malformed JSON, and network delays per business policy.
9. Separate HTTP mock tests from end-to-end environment tests; a mock server cannot prove the real production remote API obeys the contract.

### Review questions

- Why must MockRestServiceServer.bindTo(RestClient.Builder) be called before builder.build()?
- Why can a WebClient test time out at takeRequest after creating a Mono without subscribing?
- How does MockRestServiceServer differ from MockWebServer at the transport layer?
- If POST returns valid JSON but the wrong Location header, would the current test catch it? Why or why not?
- How do you test WebClient retrying a GET after 503 without allowing infinite retries?
- When multiple concurrent requests hit MockWebServer, why can FIFO enqueue cause flakiness?
- If you mock an HTTP service interface with Mockito, which parts of @HttpExchange remain untested?

## Official documentation

- [Spring Framework – Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html)
- [Spring Framework – Testing WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html)
- [MockRestServiceServer Javadoc 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html)
- [RestClient (Spring Framework)](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [WebClient (Spring Framework)](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [OkHttp MockWebServer 4.12.0 (Maven Central)](https://central.sonatype.com/artifact/com.squareup.okhttp3/mockwebserver/4.12.0)
- [WireMock Documentation](https://wiremock.org/docs/)
