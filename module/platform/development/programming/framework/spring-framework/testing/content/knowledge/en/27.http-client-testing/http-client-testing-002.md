# MockRestServiceServer and the Request Factory Replacement Mechanism

When a service uses `RestTemplate` to call an external HTTP API, unit tests often need to verify the outgoing request and check how the service handles the response. `MockRestServiceServer` supports this without spinning up a real HTTP server. It connects to `RestTemplate` by replacing that instance's `ClientHttpRequestFactory` with a mock request factory.

The key point is that `RestTemplate` still executes most of the client-side HTTP processing flow: creating the request, applying interceptors, converting the body with message converters, handling status codes, and converting the response into a Java type. What gets replaced is the layer that creates the actual HTTP connection. Requests are routed to the mock server to match expectations and return responses defined by the test.

## 1. What Is MockRestServiceServer Used to Test?

Suppose `OrderService` calls an inventory service using `RestTemplate`. The test needs to verify:

- The service calls the right URL and HTTP method.
- The request sends the right headers, query parameters, and body.
- The service converts the response into the right object.
- The service handles error statuses or unexpected responses properly.
- The request is sent the expected number of times.

`MockRestServiceServer` lets you declare expected requests up front and the responses to return when requests match. It verifies outbound communication at the HTTP client boundary without calling external systems.

Example processing flow:

```text
Service under test
       |
       v
  RestTemplate
       |
       v
ClientHttpRequestFactory
       |
       v
MockClientHttpRequestFactory
       |
       v
MockRestServiceServer
  - match request expectations
  - return configured response
       |
       v
RestTemplate response handling
       |
       v
Service receives Java object
```

## 2. What Is a Request Factory?

`ClientHttpRequestFactory` is the abstraction that `RestTemplate` uses to create a `ClientHttpRequest`. That request represents a single HTTP call and can record the method, URI, headers, and body, then execute to obtain a `ClientHttpResponse`.

In a real runtime environment, the request factory is typically backed by an HTTP implementation such as JDK `HttpURLConnection`, Apache HttpComponents, or another HTTP client. The request factory is responsible for transport concerns, such as opening connections, setting up TLS, timeouts, and sending bytes over the network.

When `MockRestServiceServer` is bound, the test replaces this transport layer with a mock request factory. The mock factory does not open sockets or send requests over the network; it creates a mock request and forwards the request information to the expectation manager to find a declared response.

| Component | When running the real application | When MockRestServiceServer is bound |
|---|---|---|
| Service | Calls `RestTemplate` | Still calls the same service and `RestTemplate` |
| URI, method, headers, body | Built by RestTemplate | Still built by RestTemplate |
| Message converters | Serialize requests and deserialize responses | Still participate in serialization/deserialization |
| Client interceptors | Can modify or observe requests/responses | Remain in the RestTemplate pipeline |
| `ClientHttpRequestFactory` | Creates real requests and network connections | Replaced by mock request factory |
| External HTTP server | Receives real requests | Not called |

As a result, the test focuses on service behavior and request/response structure. It does not verify real transport configuration such as TLS handshakes, connection pools, or timeouts of the underlying HTTP client.

## 3. Creating MockRestServiceServer from RestTemplate

The most common approach is using the builder:

```java
RestTemplate restTemplate = new RestTemplate();

MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();
```

`bindTo(restTemplate)` returns a builder that binds the mock server to a specific `RestTemplate` instance. When `.build()` is called, Spring installs the mock request factory into that `RestTemplate`.

There is an equivalent convenience method:

```java
MockRestServiceServer server = MockRestServiceServer
        .createServer(restTemplate);
```

`createServer(...)` creates the server and binds it immediately to `RestTemplate`. Use `bindTo(...).build()` when you want to configure the expectation manager or builder options; use `createServer(...)` when the default configuration suffices.

### Binding the Server After Configuring RestTemplate

Client-side components can be configured before binding the mock server:

```java
RestTemplate restTemplate = new RestTemplate();
restTemplate.getInterceptors().add(new CorrelationIdInterceptor());
restTemplate.setErrorHandler(new DefaultResponseErrorHandler());

MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();
```

The mock server replaces the request factory, while settings such as interceptors, message converters, and error handlers belong to `RestTemplate`'s pipeline. Finish configuring `RestTemplate` before binding, and do not call `setRequestFactory(...)` again afterward, as doing so may overwrite the mock factory that the server just installed.

## 4. Example of Testing a Service Calling a REST API

Suppose a service needs to retrieve order information from an inventory system:

```java
public record InventoryOrder(String id, String status) {}

public class InventoryClient {

    private final RestTemplate restTemplate;
    private final String baseUrl;

    public InventoryClient(RestTemplate restTemplate, String baseUrl) {
        this.restTemplate = restTemplate;
        this.baseUrl = baseUrl;
    }

    public InventoryOrder findOrder(String id) {
        return restTemplate.getForObject(
                baseUrl + "/orders/{id}",
                InventoryOrder.class,
                id);
    }
}
```

The test creates `RestTemplate`, binds the mock server, and declares the response:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.MockRestServiceServer.bindTo;

class InventoryClientTests {

    @Test
    void retrievesOrderFromInventoryService() {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = bindTo(restTemplate).build();
        InventoryClient client = new InventoryClient(
                restTemplate, "https://inventory.example.test");

        server.expect(requestTo("https://inventory.example.test/orders/42"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"id\":\"42\",\"status\":\"READY\"}",
                        MediaType.APPLICATION_JSON));

        InventoryOrder order = client.findOrder("42");

        assertThat(order.id()).isEqualTo("42");
        assertThat(order.status()).isEqualTo("READY");
        server.verify();
    }
}
```

When `client.findOrder("42")` runs, the request is created by `RestTemplate` and forwarded to the mock request factory. The mock server checks the URI and method; if they match, it returns the declared JSON. RestTemplate's message converter reads the JSON into `InventoryOrder`. Finally, `verify()` confirms all expectations were met.

## 5. Checking Request Headers, Query Parameters, and Body

The mock server provides many request matchers in the `org.springframework.test.web.client.match.MockRestRequestMatchers` package.

### Checking Headers

```java
server.expect(requestTo("https://inventory.example.test/orders/42"))
        .andExpect(method(HttpMethod.GET))
        .andExpect(header("X-Client-Name", "order-service"))
        .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
```

You can check header presence, exact values, or accepted values. This is useful for verifying that interceptors added an authentication token, correlation ID, or client metadata.

### Checking Query Parameters

```java
server.expect(requestTo("https://inventory.example.test/orders?status=READY&page=0"))
        .andExpect(queryParam("status", "READY"))
        .andExpect(queryParam("page", "0"))
        .andRespond(withSuccess("[]", MediaType.APPLICATION_JSON));
```

`requestTo(...)` checks the complete URI; `queryParam(...)` expresses the individual query parameters to verify. You can combine both when the exact URI is part of the contract.

### Checking a JSON Request Body

For POST or PUT, use `content()` to verify the body:

```java
server.expect(requestTo("https://inventory.example.test/orders"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().contentType(MediaType.APPLICATION_JSON))
        .andExpect(content().json(
                "{\"customerId\":\"C-12\",\"quantity\":2}"))
        .andRespond(withSuccess(
                "{\"id\":\"order-42\",\"status\":\"CREATED\"}",
                MediaType.APPLICATION_JSON));
```

`content().json(...)` compares JSON structurally, avoiding dependence on whitespace or field order. If you need to verify exact text or byte bodies, you can use `content().string(...)` or `content().bytes(...)` matchers respectively.

### Example of a Service Sending a POST

```java
public record CreateOrderRequest(String customerId, int quantity) {}

public InventoryOrder createOrder(CreateOrderRequest request) {
    return restTemplate.postForObject(
            baseUrl + "/orders", request, InventoryOrder.class);
}
```

Expectations for this method should verify POST, Content-Type, the JSON body, and the response the service needs to deserialize. That way the test verifies both the outbound request and the result the service returns to its caller.

## 6. Declaring Responses for Expected Requests

Response creators in the `org.springframework.test.web.client.response.MockRestResponseCreators` package help construct mock responses:

```java
withSuccess("{\"id\":\"42\"}", MediaType.APPLICATION_JSON);
withStatus(HttpStatus.NOT_FOUND);
withBadRequest();
withServerError();
withNoContent();
```

Example verifying 404 handling:

```java
server.expect(requestTo("https://inventory.example.test/orders/missing"))
        .andRespond(withStatus(HttpStatus.NOT_FOUND));

assertThatThrownBy(() -> client.findOrder("missing"))
        .isInstanceOf(HttpClientErrorException.NotFound.class);

server.verify();
```

By default, `RestTemplate` uses `DefaultResponseErrorHandler`, so 4xx/5xx statuses are typically converted into exceptions before `getForObject(...)` returns. If the application configures a custom error handler, the test must use that same configuration to verify the exact behavior.

## 7. Checking Call Counts and Request Ordering

The default expectation requires the request to appear once. `ExpectedCount` can be used to specify the count:

```java
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.ExpectedCount.times;
import static org.springframework.test.web.client.ExpectedCount.never;

server.expect(once(), requestTo("https://service.example.test/health"))
        .andRespond(withSuccess());

server.expect(times(2), requestTo("https://service.example.test/metrics"))
        .andRespond(withSuccess("ok", MediaType.TEXT_PLAIN));

server.expect(never(), requestTo("https://service.example.test/admin"))
        .andRespond(withSuccess());
```

Common count types include `once()`, `manyTimes()`, `times(n)`, `min(n)`, `max(n)`, and `never()`.

By default, `SimpleRequestExpectationManager` checks expectations in declaration order. If requests can arrive in a different order and order is not what needs testing, you can enable ignoring expectation order:

```java
MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .ignoreExpectOrder(true)
        .build();
```

When ignoring order, the mock server still verifies that requests match expectations and call counts. Only use this mode when outbound order is not part of the contract under test; if order has business significance, keep the default mode.

## 8. How Does the Request Factory Replacement Work?

When calling:

```java
MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();
```

Spring creates a mock request factory tied to an expectation manager and installs that factory into `RestTemplate` via its request factory configuration. From that moment on, requests emitted from that exact `restTemplate` instance are routed to the mock factory instead of the original HTTP request factory.

The sequence can be described as follows:

1. The test creates and configures `RestTemplate`.
2. The test calls `MockRestServiceServer.bindTo(restTemplate).build()`.
3. The builder installs a mock `ClientHttpRequestFactory` into `RestTemplate`.
4. The service calls `RestTemplate` as usual.
5. The mock factory creates a mock request and hands it to the expectation manager.
6. Matchers verify the request; response creators produce the mock response.
7. `RestTemplate` processes the response through its existing error handler and message converters.

Because the request factory is replaced, the test does not use real HTTP transport. Settings belonging to the original transport such as TLS, connection pooling, or socket timeouts are not verified by this test. To verify those details, integration tests with a real HTTP client/server are needed.

### Preserved vs. Replaced Configurations

| RestTemplate configuration | After binding MockRestServiceServer |
|---|---|
| `ClientHttpRequestFactory` | Replaced by mock request factory |
| Message converters | Continue to be used for writing requests and reading responses |
| `ResponseErrorHandler` | Continues to handle response statuses |
| `ClientHttpRequestInterceptor` | Still participates in the pipeline and can modify/observe requests |
| URI template handler | Continues to participate in URI expansion |
| TLS, socket timeout, connection pool of old factory | Not executed through the mock factory |

Do not call `restTemplate.setRequestFactory(...)` after binding the mock server, because that operation can replace the mock factory with another factory and prevent the mock server from receiving requests.

## 9. Resetting Expectations and Test Lifecycle

`MockRestServiceServer` provides `verify()` to confirm all expectations were satisfied. It also provides `reset()` to clear expectations and associated state so the server can be reused in another test scenario.

```java
server.verify();
server.reset();

server.expect(requestTo("/next-call"))
        .andRespond(withSuccess("done"));
```

Usually, the simplest approach is to create a fresh `RestTemplate` and `MockRestServiceServer` for each test. This prevents expectations from a previous test from affecting the next one and gives each test its own mock request factory.

If reusing the server, you must call `reset()` at the right time and re-declare all expectations. Do not share the same bound `RestTemplate` across tests running in parallel, as tests can contend over expectations and request factory state.

## 10. Using with Spring Boot and RestTemplateBuilder

In Spring Boot applications, `RestTemplateBuilder` is often used to create `RestTemplate` instances with shared configuration such as base URL, interceptors, or error handlers. Tests can still build an instance and bind the mock server:

```java
RestTemplate restTemplate = restTemplateBuilder
        .rootUri("https://inventory.example.test")
        .build();

MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();
```

When using `@RestClientTest`, Spring Boot can auto-configure `MockRestServiceServer` and `RestTemplateBuilder` to test REST client components. In that case, use the server injected by the test slice rather than creating a second server for the same `RestTemplate`.

Test slice example:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class InventoryClient {

    private final RestTemplate restTemplate;

    public InventoryClient(RestTemplateBuilder builder,
                           @Value("${inventory.base-url}") String baseUrl) {
        this.restTemplate = builder.rootUri(baseUrl).build();
    }

    public InventoryOrder findOrder(String id) {
        return restTemplate.getForObject(
                "/orders/{id}", InventoryOrder.class, id);
    }
}
```

Test slice declaring base URL via property:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(value = InventoryClient.class,
        properties = "inventory.base-url=https://inventory.example.test")
class InventoryClientSliceTests {

    @Autowired
    private InventoryClient client;

    @Autowired
    private MockRestServiceServer server;

    @Test
    void readsOrder() {
        server.expect(requestTo("https://inventory.example.test/orders/42"))
                .andRespond(withSuccess(
                        "{\"id\":\"42\",\"status\":\"READY\"}",
                        MediaType.APPLICATION_JSON));

        InventoryOrder order = client.findOrder("42");

        assertThat(order.status()).isEqualTo("READY");
        server.verify();
    }
}
```

The Boot test slice provides a focused context for the REST client and related components. Configure the base URL or root URI consistently with how the client constructs requests in the project.

## 11. When Is MockRestServiceServer Not Enough?

Because the mock server replaces the request factory, it cannot test the full behavior of real HTTP transport. Consider a mock HTTP server or integration test when you need to verify:

- TLS certificates, hostname verification, or mutual TLS.
- Connection pooling, connection reuse, or socket timeouts.
- Redirects, compression, or behavior of a specific HTTP implementation.
- Network interaction between two processes or reverse proxy configuration.
- Behavior of an HTTP client library at the transport layer.

`MockRestServiceServer` is suitable for testing request/response contracts and processing logic of code using `RestTemplate`. It does not replace real network testing.

## 12. Common Mistakes

| Symptom | Common cause | Solution |
|---|---|---|
| Requests go out to the real network | Mock server is not bound to the exact `RestTemplate` instance the service uses | Bind the server to the exact instance injected into the service |
| Request does not match expectation | Wrong URL, method, query parameter, header, or body | Inspect the actual request and declare specific matchers |
| `verify()` fails due to missing request | Code did not call the endpoint or business branch did not run | Check code branches and when the service is called |
| Unexpected request occurs | Code calls an extra undeclared endpoint | Add an expectation if that behavior is right, or fix logic emitting unintended requests |
| JSON fails to deserialize | Missing message converter or mismatched Content-Type | Return the right media type and configure needed converters |
| 4xx/5xx response throws exception | `DefaultResponseErrorHandler` turns status into an exception | Assert the exception or configure the error handler matching the application |
| Mock server receives no requests after binding | Setup code calls `setRequestFactory(...)` afterward | Configure the request factory before binding the mock server |
| Parallel tests interfere with each other | Multiple tests share a `RestTemplate` and expectation manager | Create separate client/server instances per test |

## 13. Key Takeaways

`MockRestServiceServer` tests outbound code using `RestTemplate` by declaring request expectations and mock responses. `bindTo(restTemplate).build()` installs a mock `ClientHttpRequestFactory` into the passed instance; `RestTemplate` still performs URI expansion, interceptors, message conversion, and error handling, without opening real HTTP connections. Declare requests with matchers, return responses with response creators, and call `verify()` to confirm expectations. Because the real request factory is replaced, these tests verify client logic and HTTP contracts, while TLS, timeouts, connection pools, and real transport must be verified in integration tests.

