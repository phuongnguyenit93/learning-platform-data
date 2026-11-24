# bindToServer for Testing HTTP Over a Real Network

## 1. What Is `bindToServer()` Used For?

`WebTestClient` is an HTTP client with a fluent testing API. It lets you send requests, await responses, and assert status, headers, cookies, bodies, or streaming data. When using `bindToServer()`, the client connects to a running HTTP server over a network address and TCP port.

This tests at the application's real HTTP boundary. Requests pass through the server's HTTP stack, servlet filters or WebFlux filters, routing, message conversion, and response serialization before returning to the client. Consequently, this approach can test a Spring MVC or Spring WebFlux application running on a real port.

Crucially, `bindToServer()` **does not start a server automatically**. It creates a client targeting an already-addressed server. The test must start the application or a separate server before sending requests.

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

The snippet above creates a client that sends HTTP requests to `localhost:8080`. If no server is listening at that address, requests will fail at the connection step.

## 2. Distinguishing `bindToServer()` from Other Binding Modes

`WebTestClient` can test at several different boundaries. Choosing the binding mode determines which components the test calls directly and whether a running server is required.

| Binding Mode | Components Tested | Running HTTP Server Required? |
|---|---|---|
| `bindToController(...)` | Directly registered WebFlux controller(s) | No |
| `bindToRouterFunction(...)` | WebFlux `RouterFunction` | No |
| `bindToApplicationContext(...)` | Web configuration and beans in the application context via mock server infrastructure | No real network server needed |
| `bindToServer()` | HTTP application listening at the configured address | Yes |

In-process binding modes suit tests focused on handlers, routing, or web configuration. `bindToServer()` suits verifying behavior at the HTTP boundary that external clients actually use.

A Spring MVC application does not need to switch to WebFlux to use `WebTestClient` as an HTTP client. `WebTestClient` sends HTTP requests to a server; the server can be Spring MVC, Spring WebFlux, or any other compatible HTTP server. However, the test side needs the required Spring WebFlux client libraries and an available `ClientHttpConnector` on the classpath.

## 3. Starting the Application on a Random Port

In integration tests, it is best to let Spring Boot start the real web server on a random port. `RANDOM_PORT` avoids conflicts when multiple tests or processes run concurrently.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @LocalServerPort
    private int port;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    void returnsOrderList() {
        client.get()
                .uri("/api/orders")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Spring Boot starts the application before the test runs. `@LocalServerPort` receives the actual port chosen by the embedded server. In `@BeforeEach`, the test creates the client with the corresponding base URL. Each request uses a relative URI such as `/api/orders`; WebTestClient resolves that URI against the base URL.

`RANDOM_PORT` is preferable to hardcoding `8080`, because that port may already be in use by another application. If you need to test a specifically configured port, you can use `DEFINED_PORT`, though the test must then ensure the port is available and not occupied by another process.

## 4. Sending Requests and Asserting Responses

A basic request consists of a method, URI, headers or body, followed by calling `exchange()` to send the request over HTTP:

```java
client.get()
        .uri("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(OrderResponse.class)
        .value(order -> {
            assertThat(order.id()).isEqualTo(42L);
            assertThat(order.status()).isEqualTo("CONFIRMED");
        });
```

The steps have the following meanings:

1. `get()` selects HTTP GET.
2. `uri(...)` selects the endpoint on the server.
3. `accept(...)` declares the media type accepted by the client.
4. `exchange()` sends the request and receives the response.
5. `expectStatus()` verifies the status code.
6. `expectHeader()` verifies response headers.
7. `expectBody(...)` decodes the body into the desired Java type.
8. `value(...)` runs assertions on the decoded object.

To check JSON structurally without declaring a DTO, you can use JSONPath:

```java
client.get()
        .uri("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42)
        .jsonPath("$.status").isEqualTo("CONFIRMED");
```

If an endpoint returns JSON and you need to compare the entire representation, you can use:

```java
client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {
                  "id": 42,
                  "status": "CONFIRMED"
                }
                """);
```

## 5. Sending a Request Body

For JSON requests, use `contentType(...)` to describe the body format and `bodyValue(...)` to send an object. WebTestClient uses the corresponding message writer to convert the object into HTTP bytes.

```java
@Test
void createsOrder() {
    CreateOrderRequest request = new CreateOrderRequest("BOOK-01", 2);

    client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody(OrderResponse.class)
            .value(response -> {
                assertThat(response.productCode()).isEqualTo("BOOK-01");
                assertThat(response.status()).isEqualTo("CREATED");
            });
}
```

`bodyValue(...)` fits a single object. If you need to send a publisher, you can use `body(...)`:

```java
client.post()
        .uri("/api/orders/batch")
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(Flux.just(order1, order2), OrderRequest.class)
        .exchange()
        .expectStatus().isAccepted();
```

The publisher example illustrates sending data as a stream. `APPLICATION_NDJSON` is only appropriate if the endpoint actually publishes and consumes NDJSON; the media type and data type must be compatible with the client's message writer and how the endpoint reads requests. Use the exact media type advertised by the API.

For plain text or byte bodies, you can send them directly:

```java
client.post()
        .uri("/api/messages")
        .contentType(MediaType.TEXT_PLAIN)
        .bodyValue("Xin chào Spring")
        .exchange()
        .expectStatus().isCreated();
```

## 6. Asserting Status, Headers, Cookies, and Body

WebTestClient provides dedicated expectation groups to make clear which part of the response is being verified.

```java
client.get()
        .uri("/api/profile")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals("X-API-Version", "v1")
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(ProfileResponse.class)
        .value(profile -> assertThat(profile.username()).isNotBlank());
```

Commonly used assertions:

| Goal | Example |
|---|---|
| Success status | `expectStatus().isOk()` |
| Created status | `expectStatus().isCreated()` |
| Not found status | `expectStatus().isNotFound()` |
| Header equals exact value | `expectHeader().valueEquals("X-Trace-Id", expected)` |
| Compatible content type | `expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)` |
| Body as DTO | `expectBody(OrderResponse.class)` |
| JSONPath body | `expectBody().jsonPath("$.status").isEqualTo("READY")` |
| Text body | `expectBody(String.class).isEqualTo("OK")` |
| Response without body | `expectBody().isEmpty()` |

You can assert cookies in the response using `expectCookie()`:

```java
client.post()
        .uri("/api/session")
        .bodyValue(new LoginRequest("alice", "test-password"))
        .exchange()
        .expectStatus().isOk()
        .expectCookie().exists("SESSION");
```

Cookie names and authentication behavior in the example depend on server configuration. Do not put real passwords into tests; use accounts and data dedicated to the test environment.

## 7. Shared Client Configuration

The builder lets you set defaults so multiple tests share a common configuration:

```java
client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:" + port)
        .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
        .responseTimeout(Duration.ofSeconds(5))
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024))
        .build();
```

- `baseUrl(...)` sets the server's base address.
- `defaultHeader(...)` adds a default header for requests.
- `responseTimeout(...)` limits the wait time for a response.
- `codecs(...)` configures client-side codecs, such as the memory limit when buffering bodies.

The memory limit should match a reasonable response size for the API. If a body exceeds the limit, reading the body may fail with a memory-limit error; do not raise the limit arbitrarily just to mask an abnormally large response.

If you need to configure a specific HTTP connector, pass a `ClientHttpConnector` to `bindToServer(...)`:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(5));

client = WebTestClient.bindToServer(
                new ReactorClientHttpConnector(httpClient))
        .baseUrl("http://localhost:" + port)
        .build();
```

This example uses the Reactor Netty connector; the corresponding dependency must be on the test runtime classpath. Calling `bindToServer()` without arguments uses the default connector chosen by Spring based on libraries on the classpath. Only specify a custom connector when the test needs to control connection settings or transport behavior.

## 8. Reusing and Mutating the Client

Once you have a base client, you can create a variant client with additional configuration:

```java
WebTestClient authenticatedClient = client.mutate()
        .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
        .build();
```

The new client inherits the base configuration and adds the Authorization header. This is useful when multiple tests hit the same endpoints but use different identities or default headers.

When testing authentication against a real server, send credentials or tokens according to the protocol the application actually supports. For example, send a Basic Authorization header, a bearer token signed for the test environment, or a server-issued cookie/session. Helpers that fabricate mock principals for in-process testing do not replace sending credentials over HTTP and verifying them on the server.

When verifying that the server rejects requests missing a token, send a request without an Authorization header. When verifying permissions, send a test token with the appropriate authority and assert both status and response. This exercises both the authentication filter and authorization rules along the HTTP path.

## 9. Testing HTTP Errors and Content Negotiation

Testing only success cases is not enough. Real clients must also receive the right responses when requests are malformed, missing data, or unauthorized.

For example, an endpoint accepting only JSON may reject a request sent as text/plain:

```java
client.post()
        .uri("/api/orders")
        .contentType(MediaType.TEXT_PLAIN)
        .bodyValue("productCode=BOOK-01")
        .exchange()
        .expectStatus().isEqualTo(HttpStatus.UNSUPPORTED_MEDIA_TYPE);
```

If the client requests a response format the endpoint does not support, you can check for `406 Not Acceptable`:

```java
client.get()
        .uri("/api/orders")
        .accept(MediaType.APPLICATION_XML)
        .exchange()
        .expectStatus().isEqualTo(HttpStatus.NOT_ACCEPTABLE);
```

Exact results depend on the application's mappings, message converters, and exception handling. Tests must reflect the endpoint's actual contract. Do not assume all incompatible requests return a fixed status if the application has a custom error handler or negotiation strategy.

## 10. Testing Asynchronous and Streaming Endpoints

WebTestClient has a reactive API, making it suitable for endpoints returning streaming data, such as Server-Sent Events (SSE). For non-terminating streams, do not wait for the entire body to complete. You can receive the response body as a `Flux` and use Reactor Test to verify a few elements and then cancel the subscription.

```java
FluxExchangeResult<ServerSentEvent<String>> result = client.get()
        .uri("/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(new ParameterizedTypeReference<ServerSentEvent<String>>() {});

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event -> "READY".equals(event.data()))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

Tests should set a finite timeout so they do not hang if the server stops emitting events. `thenCancel()` stops reading the stream after receiving the expected element. For endpoints returning a finite publisher, you can use `expectBodyList(...)` or `returnResult(...)` depending on the test goal.

For asynchronous endpoints like HTTP `202 Accepted`, distinguish between the response acknowledging receipt of the request and the final result once background work completes. If an API returns a job ID and processes in the background, the test should check the job-acceptance response first, then await completion via a status endpoint or a test synchronization mechanism. Avoid using long `Thread.sleep(...)` calls to guess when background work finishes.

## 11. Testing HTTPS Servers and Transport Details

Because `bindToServer()` is an HTTP client, the base URL can use `https://` if the server has TLS enabled:

```java
client = WebTestClient.bindToServer()
        .baseUrl("https://localhost:" + httpsPort)
        .build();
```

To connect successfully, the client must trust the certificate presented by the server and the hostname must match the certificate. For self-signed test certificates, configure a trust store or SSL context dedicated to tests. Do not disable certificate verification in tests and treat that as proof that TLS is configured correctly.

Testing HTTPS on localhost verifies that the application or embedded server handles TLS according to the test configuration. It does not automatically verify the TLS configuration of a reverse proxy, ingress, load balancer, or production certificates if those components are not in the request path.

Similarly, sending requests to `localhost` verifies the local server's HTTP stack. It does not automatically verify public DNS, firewalls, cross-network routing, production gateways, or CDN policies. To test those boundaries, you need a test deployed to the target environment or an appropriate network testing setup.

## 12. Server Lifecycle and Test Isolation

With `RANDOM_PORT`, Spring Boot starts the server in a separate request-handling thread. Tests send requests over a socket to that server. This has an important consequence for transactions:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {
    // The test thread has its own transaction.
}
```

A transaction created by `@Transactional` on the test does not automatically propagate to the server thread handling the request. If the endpoint writes data, the server's transaction may commit independently. When the test ends and rolls back its own transaction, it does not automatically roll back data written by the HTTP request.

Therefore, for real-server tests:

- Create test data with unique identifiers to avoid execution-order dependencies.
- Clean up data through repositories or appropriate administrative APIs after the test.
- Do not assume `@Transactional` on the test will automatically revert operations sent over HTTP.
- Use a database or schema dedicated to tests, avoiding writes to shared data.
- Avoid tests depending on a previously run request or a fixed port.
- Set timeouts for responses, streams, and background tasks.

If the test starts the application on a random port, the server is typically managed by the Spring test context lifecycle. When multiple tests share a context, the server may be reused; therefore, data state and cookies must be actively isolated.

## 13. Comparing WebTestClient Against a Real Server vs MockMvc

| Criterion | `WebTestClient.bindToServer()` | `MockMvc` |
|---|---|---|
| Invocation mechanism | HTTP request over connector and socket | Simulates servlet request/response inside the test process |
| Running server required | Yes | No |
| Can test server port and HTTP transport | Yes | No |
| Tests servlet filters registered on the server | Yes, when requests go through the real server | Possible, if filters are added to MockMvc |
| Speed and startup cost | Usually higher due to server startup and HTTP communication | Usually lower |
| Best suited for | HTTP integration, serialization, filter chains, and real server behavior | In-process MVC slices, controllers, and servlet behavior |

The two tools complement each other. Use MockMvc for fast verification of MVC branches and use `bindToServer()` for contracts that must be verified over real HTTP. There is no need to move all controller tests to a real server if a test does not need the network boundary.

## 14. Common Pitfalls When Using `bindToServer()`

| Symptom | Common Cause | Resolution |
|---|---|---|
| Connection refused | Server has not started, wrong port, or wrong host | Use `RANDOM_PORT`, inject `@LocalServerPort`, and check server lifecycle |
| Test always calls port 8080 | Base URL is hardcoded | Construct the base URL with the injected runtime port |
| Request timeout | Endpoint hangs, stream does not terminate, or background task is not ready | Set appropriate timeouts and poll completion conditions instead of waiting forever |
| Body cannot be decoded | Client lacks codec or media type is incompatible | Check dependencies, `Content-Type`, body types, and codec configuration |
| Security test behaves differently from MockMvc | Real requests go through the filter chain and a separate server thread | Send credentials/tokens/cookies via real HTTP protocols and check server policy |
| Data remains after test | Test transaction does not cover the server thread's transaction | Clean up data explicitly and use isolated data per test |
| HTTPS handshake fails | Certificate is untrusted or hostname does not match | Configure a trust store and certificate appropriate for tests |
| Streaming test hangs | Test waits on a non-terminating response stream | Use `FluxExchangeResult`, `StepVerifier`, cancellation, and timeouts |

When investigating failures, verify step by step that the server has started, the base URL uses the right port, the connector can connect, the endpoint responds, and only then check codecs and body assertions. This layered approach helps separate connection errors from business logic or serialization errors.

## 15. When Should You Choose `bindToServer()`?

Choose `bindToServer()` when the test goal needs to pass through a running HTTP server, for example:

- Verifying that an endpoint works on a real port and returns the right status/headers/body.
- Checking message conversion and content negotiation across the client-server boundary.
- Testing servlet filters, WebFlux filters, authentication, and authorization under real server configuration.
- Testing cookies, redirects, compression, streaming, or timeouts.
- Verifying HTTPS and connector configuration in the test environment.
- Testing the application's HTTP contract without calling controllers directly.

Do not choose real-server tests just because the API can be called with WebTestClient. If the goal is simply to test a controller or handler, in-process tests are usually faster and easier to isolate.

`bindToServer()` turns WebTestClient into an HTTP testing client targeting a running server. Combined with a server on a random port, real requests, status/header/body assertions, and isolated test data, it provides closer evidence of the behavior that external clients actually observe.
