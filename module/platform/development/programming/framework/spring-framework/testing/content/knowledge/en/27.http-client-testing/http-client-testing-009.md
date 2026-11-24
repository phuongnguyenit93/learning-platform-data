# Mock Web Server for Running Real HTTP Client Configuration

When a Spring application calls an external HTTP service, tests need to verify more than whether the service returns the right object. The client may have to build the right URL, method, query parameters, authentication headers, JSON body, timeouts, retries, and response decoding. If you only mock the HTTP client interface, none of this configuration actually runs.

A mock web server solves that by opening a small HTTP server on the loopback interface and a random port. The test configures the HTTP client to point at this server, queues mock responses, and sends requests through the application's real HTTP stack. The server records received requests so the test can verify method, path, headers, and body.

In Spring, this is especially useful when testing `RestClient` or `WebClient` together with their real request factory, connector, codecs, interceptors/filters, and timeout configuration. There is no need to call external services, yet requests still travel through real HTTP transport on the test machine.

## 1. Why Use a Mock Web Server?

Suppose `CatalogClient` calls a catalog service. A test that only mocks `CatalogClient` can check that the business service called the right method, but cannot prove the HTTP request was built properly. A test that only mocks the request factory can also skip the HTTP connector's behavior or body serialization.

A mock web server lets you check both directions:

```text
Application / Real HTTP client
        |
        | GET /catalog/42
        | Accept: application/json
        v
Application HTTP stack
        |
        | TCP loopback
        v
MockWebServer (localhost, random port)
        |
        +--> Return enqueued response
        |
        +--> Record RecordedRequest
                     |
                     v
             Test inspects request
```

Tests can verify:

- The client uses the right base URL and assembles path/query parameters accurately.
- The HTTP method and headers are sent properly.
- Interceptors or filters add tokens, correlation ids, or user agents.
- Objects are serialized into properly formatted JSON.
- Responses are decoded into the right DTO types.
- The client handles error statuses, retries, timeouts, or dropped connections per configuration.
- The real request factory or connector is used during the exchange.

The mock server is not an external service. It only simulates the server side and runs inside the test process or a local process, typically listening on loopback with an automatically assigned port.

## 2. Choosing a Mock Web Server vs. a Mock Request Factory

Spring provides `MockRestServiceServer` for certain types of HTTP client tests. That tool intercepts requests at Spring's request factory layer and matches test-declared expectations. It is very helpful for unit tests focused on how the application builds requests.

A mock web server such as OkHttp `MockWebServer` operates at the HTTP server layer. The client makes a local network connection, sends requests through its configured request factory or connector, and receives responses over HTTP transport.

| Criterion | `MockRestServiceServer` | Mock web server |
|---|---|---|
| Where requests are intercepted/received | Spring request factory layer | A local HTTP server |
| Real socket/HTTP transport? | No | Yes, over loopback |
| Tests real request factory/connector? | No, because request factory is replaced by mock | Yes |
| Tests serialization/deserialization over HTTP | Tested at Spring converter layer, depending on setup | Tested via real HTTP request/response |
| Tests transport timeouts, disconnects, retries | Limited | Better suited |
| Setup | Usually concise for Spring client tests | Requires starting and stopping server |

Use `MockRestServiceServer` when you want fast tests of a Spring client's request contract without needing to test transport. Use a mock web server when the goal is running real HTTP client configuration, including the request factory or connector. The two approaches complement each other; you do not have to pick one for every test.

## 3. Adding MockWebServer to Test Dependencies

Examples in this guide use OkHttp MockWebServer 4.x with the `okhttp3.mockwebserver` package. Add the library only in the test scope:

```groovy
dependencies {
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}
```

If the project uses Maven:

```xml
<dependency>
    <groupId>com.squareup.okhttp3</groupId>
    <artifactId>mockwebserver</artifactId>
    <version>4.12.0</version>
    <scope>test</scope>
</dependency>
```

Pick a version compatible with the OkHttp version already in the project's dependency graph. If internal dependency management already controls versions, use the project-specified version instead of introducing an unnecessary extra version.

Common classes:

| Class | Role |
|---|---|
| `MockWebServer` | Starts a local HTTP server and manages the response queue |
| `MockResponse` | Declares status, headers, body, or socket policy for the next response |
| `RecordedRequest` | Holds the request received by the server for test inspection |
| `SocketPolicy` | Simulates socket scenarios such as closing connections |

## 4. Lifecycle of the Mock Server in JUnit

Each test should have a clear server lifecycle: start before configuring the client, enqueue responses before sending requests, and shut down after the test finishes.

```java
import java.io.IOException;

import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class CatalogClientTests {

    private MockWebServer server;

    @BeforeEach
    void startServer() throws IOException {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void stopServer() throws IOException {
        server.shutdown();
    }
}
```

`start()` typically selects an available port automatically. Do not hardcode `localhost:8080`, as that port may already be used by another application or test. Obtain the dynamic URL via `server.url("/")`:

```java
String baseUrl = server.url("/").toString();
```

The returned URL has the form `http://localhost:<port>/`. Use this URL as the client's base URL. If the client needs a path prefix, configure the prefix consistently in client configuration or in the test URL.

If tests run in parallel, do not share a single server with a response queue across independent tests unless request ordering is synchronized. Giving each test instance its own server prevents responses from being consumed by another test.

## 5. Using RestClient with MockWebServer

`RestClient` is Spring Framework's synchronous HTTP client. An adapter can accept a configured `RestClient` and use it to call services:

```java
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

record CatalogItem(String id, String name) {
}

class CatalogClient {

    private final RestClient restClient;

    CatalogClient(RestClient.Builder builder, String baseUrl) {
        this.restClient = builder
                .baseUrl(baseUrl)
                .defaultHeader("Accept", MediaType.APPLICATION_JSON_VALUE)
                .build();
    }

    CatalogClient(RestClient restClient) {
        this.restClient = restClient;
    }

    CatalogItem findById(String id) {
        return restClient.get()
                .uri("/catalog/{id}", id)
                .retrieve()
                .body(CatalogItem.class);
    }
}
```

The test creates the mock server, enqueues a response, and initializes the client with the server-assigned URL:

```java
import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientTests {

    private MockWebServer server;
    private CatalogClient catalogClient;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        catalogClient = new CatalogClient(
                RestClient.builder(), server.url("/").toString());
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void sendsRequestAndDecodesResponse() throws Exception {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .setBody("""
                        {
                          "id": "42",
                          "name": "Spring in Action"
                        }
                        """));

        CatalogItem item = catalogClient.findById("42");

        assertThat(item).isEqualTo(
                new CatalogItem("42", "Spring in Action"));

        RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
        assertThat(request).isNotNull();
        assertThat(request.getMethod()).isEqualTo("GET");
        assertThat(request.getPath()).isEqualTo("/catalog/42");
        assertThat(request.getHeader("Accept"))
                .isEqualTo(MediaType.APPLICATION_JSON_VALUE);
    }
}
```

This test performs a real HTTP request to a loopback port. `MockWebServer` returns the enqueued JSON; `RestClient` uses message converters to decode JSON into `CatalogItem`. Then `takeRequest(...)` retrieves the recorded request from the server to verify method, path, and headers.

`takeRequest(1, TimeUnit.SECONDS)` waits up to one second to receive the request. Using a finite timeout ensures the test fails clearly if the client never sends a request, instead of hanging indefinitely. Check that `request` is non-null before reading its properties.

## 6. Checking Request Body and Authentication Headers

When a client sends a POST, you can inspect the actual body received by the server. Example of an admin client creating items:

```java
record CreateCatalogItem(String name) {
}

class CatalogAdminClient {

    private final RestClient restClient;

    CatalogAdminClient(RestClient.Builder builder, String baseUrl, String apiKey) {
        this.restClient = builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Api-Key", apiKey)
                .build();
    }

    void create(CreateCatalogItem command) {
        restClient.post()
                .uri("/catalog")
                .contentType(MediaType.APPLICATION_JSON)
                .body(command)
                .retrieve()
                .toBodilessEntity();
    }
}
```

The test can verify headers and JSON body:

```java
server.enqueue(new MockResponse().setResponseCode(201));

catalogAdminClient.create(new CreateCatalogItem("Spring Guide"));

RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
assertThat(request).isNotNull();
assertThat(request.getMethod()).isEqualTo("POST");
assertThat(request.getPath()).isEqualTo("/catalog");
assertThat(request.getHeader("X-Api-Key")).isEqualTo("test-api-key");
assertThat(request.getHeader("Content-Type"))
        .contains(MediaType.APPLICATION_JSON_VALUE);
assertThat(request.getBody().readUtf8())
        .contains("\"name\":\"Spring Guide\"");
```

Property order or whitespace in JSON may depend on the message converter. If ordering is not part of the contract, avoid comparing raw JSON as an exact string. You can parse the JSON and compare fields, or use a JSON assertion library.

For tokens or API keys, only use fake values in tests. Recorded requests may contain headers and bodies; do not log full sensitive payloads in real test execution environments.

## 7. Testing RestClient Configuration Created in a Spring Context

The previous example constructed `RestClient.Builder` directly. That tests how `CatalogClient` configures the builder, yet does not necessarily test `RestClientCustomizer` beans, request factories, SSL, or interceptors provided by Spring Boot.

If the goal is testing the production client bean, load the real application context and override only the base URL to point to the mock server. Example bean configuration:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogHttpClientConfiguration {

    @Bean
    CatalogClient catalogClient(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {

        RestClient restClient = builder
                .baseUrl(baseUrl)
                .defaultHeader(HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();

        return new CatalogClient(restClient);
    }
}
```

In a Spring Boot application, `RestClient.Builder` is auto-configured and can be tailored by application customizers. The test uses `@SpringBootTest` to load the same production configuration, while `@DynamicPropertySource` supplies the dynamic base URL:

```java
import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class CatalogClientContextTests {

    private static final MockWebServer SERVER = startServer();

    @Autowired
    CatalogClient catalogClient;

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        }
        catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("catalog.base-url", () -> SERVER.url("/").toString());
    }

    @AfterAll
    static void stopServer() throws IOException {
        SERVER.shutdown();
    }

    @Test
    void usesConfiguredCatalogClientBean() throws Exception {
        SERVER.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""
                        {"id":"7","name":"Reactive Systems"}
                        """));

        CatalogItem item = catalogClient.findById("7");

        assertThat(item.name()).isEqualTo("Reactive Systems");
        RecordedRequest request = SERVER.takeRequest(1, TimeUnit.SECONDS);
        assertThat(request).isNotNull();
        assertThat(request.getPath()).isEqualTo("/catalog/7");
    }
}
```

This example assumes the application has a `@SpringBootApplication` scanning `CatalogHttpClientConfiguration`, and `CatalogClient` has the `findById(...)` method from the earlier section. If your configuration does not use Spring Boot, declare `RestClient.Builder` and the needed customizers in the test context.

The mock server starts in a static initializer so it is ready when Spring builds the context and reads dynamic properties. `@AfterAll` shuts down the server after the test class completes. When a context is cached across multiple test classes, design the server lifecycle to remain compatible for as long as the context still uses the client; do not shut down the server while that context is still being reused.

## 8. Using MockWebServer with WebClient

`WebClient` is Spring WebFlux's reactive HTTP client. MockWebServer still works because it receives HTTP requests over sockets; the difference lies in how the test consumes the reactive result.

```java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class ReactiveCatalogClient {

    private final WebClient webClient;

    ReactiveCatalogClient(WebClient.Builder builder, String baseUrl) {
        this.webClient = builder
                .baseUrl(baseUrl)
                .defaultHeader("Accept", "application/json")
                .build();
    }

    Mono<CatalogItem> findById(String id) {
        return webClient.get()
                .uri("/catalog/{id}", id)
                .retrieve()
                .bodyToMono(CatalogItem.class);
    }
}
```

The test uses Reactor Test to await publisher completion:

```java
import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ReactiveCatalogClientTests {

    private MockWebServer server;
    private ReactiveCatalogClient catalogClient;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();
        catalogClient = new ReactiveCatalogClient(
                WebClient.builder(), server.url("/").toString());
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void sendsRequestAndReceivesReactiveResponse() throws Exception {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"id\":\"9\",\"name\":\"WebFlux\"}"));

        StepVerifier.create(catalogClient.findById("9"))
                .expectNext(new CatalogItem("9", "WebFlux"))
                .verifyComplete();

        RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
        assertThat(request).isNotNull();
        assertThat(request.getMethod()).isEqualTo("GET");
        assertThat(request.getPath()).isEqualTo("/catalog/9");
    }
}
```

`StepVerifier` subscribes to the `Mono`, awaits the response, and asserts the emitted value. After the publisher completes, the test reads `RecordedRequest` to verify the actual HTTP request. In Spring Boot, if you want to verify `WebClient.Builder` and production `WebClientCustomizer` beans, load the application context and override the base URL just like in the `RestClient` example.

`WebClient` requires a `ClientHttpConnector`. The actual connector is selected by project dependencies and application configuration. If you want to verify Reactor Netty, ensure the test uses the exact Reactor Netty connector used by the application; do not replace the connector with a mock just to make the test run.

## 9. Simulating Error Statuses and Verifying Error Handling

The mock server can return any status code to test client error handling:

```java
server.enqueue(new MockResponse()
        .setResponseCode(404)
        .addHeader("Content-Type", "application/json")
        .setBody("""
                {"code":"ITEM_NOT_FOUND"}
                """));
```

With `RestClient.retrieve()`, 4xx/5xx responses default to throwing an exception in the `RestClientResponseException` family unless the application registers a custom status handler. You can assert the status and error body:

```java
import org.springframework.web.client.HttpClientErrorException;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

assertThatThrownBy(() -> catalogClient.findById("missing"))
        .isInstanceOf(HttpClientErrorException.NotFound.class);
```

With `WebClient.retrieve()`, 4xx/5xx responses are represented by `WebClientResponseException` by default. Reactive tests can assert the error signal:

```java
import org.springframework.web.reactive.function.client.WebClientResponseException;

StepVerifier.create(catalogClient.findById("missing"))
        .expectErrorSatisfies(error -> {
            assertThat(error)
                    .isInstanceOf(WebClientResponseException.NotFound.class);
        })
        .verify();
```

If the client has retries or fallbacks, the test needs to enqueue the corresponding sequence of responses. For example, enqueue `503` then `200`, call the client once, and assert the final result; then take two requests from the server to prove retries occurred the expected number of times. Do not use `Thread.sleep(...)` to wait for retries if time can be controlled using a scheduler or the application's retry test mechanism.

## 10. Testing Timeouts and Dropped Connections

MockWebServer supports simulating several transport scenarios that a mock request factory struggles to reproduce.

### Slow Responses

You can configure a response with a delayed body:

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":\"1\",\"name\":\"Slow item\"}")
        .setBodyDelay(2, TimeUnit.SECONDS));
```

Then run the client with a read/response timeout shorter than the server delay and verify that the timeout is handled according to the contract. Exact timeout behavior depends on the request factory or connector, so the timeout configured in the test must be the real configuration used by the application.

### Server Closing the Connection

You can simulate the server dropping the socket using `SocketPolicy`:

```java
import okhttp3.mockwebserver.SocketPolicy;

server.enqueue(new MockResponse()
        .setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST));
```

The client receives an I/O error or corresponding connector error. If the application retries, verify that the request is resent and the final response is handled. Specific exception classes may differ across JDK HTTP client, Apache HttpClient, and Reactor Netty; application contract tests should prefer verifying fallback/retry behavior or the public error type promised by the adapter.

Avoid writing timeout tests with overly tight real-time margins. Leave enough separation between the response delay and the timeout, or use a controllable clock/scheduler if the application's retry/timeout logic supports it.

## 11. Testing Retries and Request Ordering

MockWebServer uses a response queue: each subsequent request pops one enqueued `MockResponse`. This is convenient for retries:

```java
server.enqueue(new MockResponse().setResponseCode(503));
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":\"42\",\"name\":\"Recovered\"}"));

CatalogItem item = retryingCatalogClient.findById("42");

assertThat(item.name()).isEqualTo("Recovered");
RecordedRequest first = server.takeRequest(1, TimeUnit.SECONDS);
RecordedRequest second = server.takeRequest(1, TimeUnit.SECONDS);
assertThat(first).isNotNull();
assertThat(second).isNotNull();
assertThat(first.getPath()).isEqualTo("/catalog/42");
assertThat(second.getPath()).isEqualTo("/catalog/42");
```

The example assumes `retryingCatalogClient` has a retry policy handling `503`. Without retry, the first request would fail and the second request would not be sent. Tests should verify both the outcome and the request count so a fallback does not mask a retry that never ran.

With multiple concurrent requests, do not assume response queue ordering matches publisher completion order. If testing concurrency, use distinct request paths or headers to distinguish each request and inspect the corresponding `RecordedRequest` objects.

## 12. Testing URI, Encoding, and Redirects

One of the most common HTTP client bugs is incorrect URL assembly or query parameter encoding. Because the mock server records the actual path, tests can inspect the request line:

```java
RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
assertThat(request.getPath())
        .isEqualTo("/search?q=spring%20framework&page=2");
```

Encoding results depend on how the client and URI builder process characters. Verify against the upstream server's contract, especially for spaces, `+` signs, Unicode, `/` inside path variables, and multi-valued parameters.

MockWebServer can also return redirects using statuses `301`, `302`, `307`, or `308` with a `Location` header. Redirect-following behavior depends on the request factory/connector and redirect configuration. Tests should confirm whether the client follows or rejects redirects as required by the application, and use `RecordedRequest` to check whether the server receives a second request at the new path.

## 13. Testing TLS or mTLS Authentication

MockWebServer supports HTTPS configuration via `useHttps(...)` with an `SSLSocketFactory`. This is useful when the client configures a trust store, hostname verification, or client certificates and the test needs to verify a real handshake.

A TLS test must prepare test certificates, trust material, and possibly client key material. Do not disable hostname verification or trust all certificates just to make tests pass. Test configuration should reflect the security policy under test while using dedicated test-only certificates.

If you only need to verify `Authorization` headers or API keys, loopback HTTP is usually sufficient; avoid adding unnecessary TLS complexity. If the goal is verifying trust stores, certificate rotation, or mTLS, use an HTTPS mock server and confirm the handshake actually occurs.

## 14. MockWebServer vs. WireMock

OkHttp MockWebServer fits when you need a lightweight HTTP server, a response queue, request recording, and socket behavior simulation. WireMock provides a richer DSL for request matching, scenario state, verification, and complex stubs.

| Need | Suitable choice |
|---|---|
| Enqueue responses in order and retrieve received requests | MockWebServer |
| Test real transport and request factory/connector | MockWebServer or WireMock running a real server |
| Stubs based on JSONPath, complex headers, and queries | WireMock |
| Stateful multi-step scenarios, reusable mappings | WireMock |
| Test Spring `RestClient` at request factory layer without sockets | `MockRestServiceServer` |

Pick the smallest tool that meets the goal. For a client that only needs to verify URL, headers, JSON, and responses, MockWebServer is usually enough.

## 15. Common Mistakes

| Practice | Problem | Better practice |
|---|---|---|
| Hardcoding ports like `8080` | Port may be busy or collide in parallel runs | Use `server.start()` and `server.url(...)` |
| Forgetting `shutdown()` | Server and sockets may keep running after the test | Stop server in `@AfterEach` or `@AfterAll` |
| Enqueuing responses after sending requests | Request may hang or receive an unintended response | Enqueue before calling the client |
| Skipping `RecordedRequest` checks | Verifies only responses, missing sent URL/headers/body | Inspect requests received by the server |
| Mocking request factory and concluding real transport works | Mock replaces the transport layer needing verification | Use a mock web server to receive HTTP over sockets |
| Sharing one server across parallel tests | Response queue can be consumed by another test | Create dedicated servers or synchronize explicitly |
| Comparing raw JSON strings when order does not matter | Test couples to formatting and property order | Parse JSON and compare fields |
| Timeout too close to response delay | Results fluctuate on CI | Leave adequate margin and use finite timeouts |
| Disabling TLS verification to make tests pass easily | Fails to verify security policy | Use test certificates and proper trust configuration |

## 16. Workflow for Designing an HTTP Client Test

1. Identify which client configuration needs to run for real: base URL, request factory/connector, timeouts, converters/codecs, interceptors/filters, TLS, or retries.
2. Choose the tool: MockWebServer for real HTTP transport, `MockRestServiceServer` for a mock request factory, or WireMock for complex stubs.
3. Start the mock server on a random port before creating the client or Spring context.
4. Override only the upstream endpoint to point the production client to the mock server; preserve customizers and transport under test.
5. Enqueue appropriate responses before sending requests.
6. Call the application client method just as in production.
7. Assert decoded results or client-exposed exceptions/fallbacks.
8. Take `RecordedRequest` to verify actual method, path, query, headers, and body.
9. For retries, timeouts, or disconnects, verify both request count and final outcome.
10. Shut down the server and ensure server lifecycle is compatible with Spring context caching or test parallelism.

## 17. References

- [Spring Framework Reference — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `WebClient`, request factories, and HTTP client configuration.
- [Spring Framework Reference — Testing REST Clients](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): testing Spring clients and `MockRestServiceServer`.
- [OkHttp MockWebServer](https://github.com/square/okhttp/tree/master/mockwebserver): mock HTTP server library, response queue, and recorded requests.
- [Spring Boot Reference — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): configuring and using REST clients in Spring Boot.

A mock web server lets tests exercise real HTTP client configuration without depending on external services. Point the production client to a local server on a dynamic port, enqueue responses, invoke the client normally, and verify both the outcome and the requests received by the server. This provides evidence about the request factory or connector, codecs, and HTTP policies that interface-level mocks cannot replace.
