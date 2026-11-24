# Avoiding Over-Mocking of Client Fluent Chains

When writing unit tests for a service that calls an external HTTP API, a common pattern is mocking every call in the HTTP client's fluent chain: `get()`, `uri(...)`, `retrieve()`, and then `body(...)`. With `WebClient`, the chain can be even longer: `get()`, `uri(...)`, `retrieve()`, `bodyToMono(...)`. This approach usually requires deep stubbing or multiple nested mocks.

Such tests are tightly coupled to implementation details. Simply changing how the URI is built, adding a header, switching from `retrieve()` to `exchange()`, or refactoring the client can break the test even when external HTTP behavior remains correct. Moreover, when the whole chain is mocked, the test fails to verify how the request is actually sent, how JSON is serialized, how error statuses are handled, or whether the response body deserializes properly.

A more sustainable design separates two responsibilities: testing business logic through an application-owned interface, and testing the HTTP adapter with a real HTTP client connected to a mock HTTP server. With Spring, `MockRestServiceServer` fits `RestClient` and `RestTemplate`; `MockWebServer` or WireMock typically fits `WebClient` and clients communicating over sockets.

## 1. Why Does Deeply Mocking Fluent Chains Cause Problems?

Suppose a service uses `RestClient` to fetch inventory information:

```java
public class InventoryService {

    private final RestClient restClient;

    public InventoryService(RestClient restClient) {
        this.restClient = restClient;
    }

    public InventoryItem findBySku(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryItem.class);
    }
}
```

A test might attempt to mock the entire chain:

```java
@Mock(answer = Answers.RETURNS_DEEP_STUBS)
RestClient restClient;

when(restClient.get()
        .uri("/api/inventory/{sku}", "SKU-1")
        .retrieve()
        .body(InventoryItem.class))
    .thenReturn(new InventoryItem("SKU-1", 12));
```

This snippet illustrates using deep stubs to replace all intermediate objects. That approach has several drawbacks:

- The test must know the exact sequence of methods the implementation calls. Adding an `accept(...)` step or changing how the URI is built can break stubbing.
- Intermediate interfaces of `RestClient` are details of the fluent API. Mocking step by step couples the test to API usage rather than the behavior the application needs to provide.
- Mocking `retrieve()` and `body(...)` executes no HTTP exchange. The test does not verify the actual method, URL, headers, request body, status code, or response body.
- No real JSON serialization/deserialization runs in the mocked chain, so message converter misconfigurations can slip through.
- A test can pass even if the real request is wrong, because mocks return results based on predefined stubbed calls.

Deep stubs are not always wrong. They can be useful for simple fluent APIs or very narrow interaction tests. With HTTP clients, however, they usually replace the exact behavior that needs testing: HTTP communication and data conversion.

## 2. Separating Business Logic from the HTTP Client

A business service usually does not need to know which methods `RestClient` has. It only needs an application-level capability, such as "look up inventory by SKU." We can represent that capability with an application-owned interface.

```java
public interface InventoryGateway {
    InventoryItem findBySku(String sku);
}

public record InventoryItem(String sku, int availableQuantity) {
}
```

The business service depends on the interface:

```java
public class OrderService {

    private final InventoryGateway inventoryGateway;

    public OrderService(InventoryGateway inventoryGateway) {
        this.inventoryGateway = inventoryGateway;
    }

    public boolean canFulfill(String sku, int requestedQuantity) {
        InventoryItem item = inventoryGateway.findBySku(sku);
        return item.availableQuantity() >= requestedQuantity;
    }
}
```

Unit tests for `OrderService` only need to mock `InventoryGateway`:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    InventoryGateway inventoryGateway;

    @InjectMocks
    OrderService orderService;

    @Test
    void shouldAllowOrderWhenStockIsEnough() {
        when(inventoryGateway.findBySku("SKU-1"))
                .thenReturn(new InventoryItem("SKU-1", 12));

        assertThat(orderService.canFulfill("SKU-1", 5)).isTrue();

        verify(inventoryGateway).findBySku("SKU-1");
    }

    @Test
    void shouldRejectOrderWhenStockIsInsufficient() {
        when(inventoryGateway.findBySku("SKU-1"))
                .thenReturn(new InventoryItem("SKU-1", 3));

        assertThat(orderService.canFulfill("SKU-1", 5)).isFalse();
    }
}
```

This test focuses on business rules: whether the requested quantity is satisfied by available stock. It does not need to know whether inventory data comes from HTTP, a database, a cache, or another source. The interface acts as the boundary between business logic and external integration.

The implementation class for the interface uses the HTTP client:

```java
public class InventoryHttpAdapter implements InventoryGateway {

    private final RestClient restClient;

    public InventoryHttpAdapter(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public InventoryItem findBySku(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(InventoryItem.class);
    }
}
```

This adapter is where you test how HTTP requests are built and responses converted into `InventoryItem`. Instead of mocking individual `RestClient` methods, run the adapter with a real `RestClient` connected to a mock HTTP server.

## 3. Using `MockRestServiceServer` with `RestClient`

Spring Test provides `MockRestServiceServer` to test code using `RestClient` or `RestTemplate` without calling external services. The mock server receives requests emitted by the HTTP client, lets you set expectations on URL, method, headers, and body, and returns mock responses.

For `RestClient`, Spring Framework supports binding the mock server to `RestClient.Builder` since Spring Framework 6.1. Bind before calling `build()` so the builder uses the request factory configured by the mock server.

```java
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.http.HttpMethod.GET;

@Test
void shouldReadInventoryItemFromHttpResponse() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://inventory.example");

    MockRestServiceServer server = MockRestServiceServer
            .bindTo(builder)
            .build();

    RestClient restClient = builder.build();
    InventoryHttpAdapter adapter = new InventoryHttpAdapter(restClient);

    server.expect(requestTo("https://inventory.example/api/inventory/SKU-1"))
            .andExpect(method(GET))
            .andExpect(header("Accept", MediaType.APPLICATION_JSON_VALUE))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-1","availableQuantity":12}
                    """,
                    MediaType.APPLICATION_JSON
            ));

    InventoryItem item = adapter.findBySku("SKU-1");

    assertThat(item).isEqualTo(new InventoryItem("SKU-1", 12));
    server.verify();
}
```

This test uses Spring's real HTTP client. `MockRestServiceServer` intercepts requests at the request factory and returns the declared response. Consequently, the test genuinely traverses the `RestClient` chain used by the application, including URI building, header attachment, exchange execution, and JSON deserialization.

### Meaning of the Steps

1. Create `RestClient.Builder` with the service's base URL.
2. Bind `MockRestServiceServer` to the builder.
3. Build `RestClient` after binding the mock server.
4. Construct the adapter using the real client.
5. Set expectations for URL, HTTP method, and headers.
6. Declare the mock JSON response.
7. Invoke the adapter just like production code.
8. Assert the received DTO and call `server.verify()` to confirm expected requests occurred.

There is no need to mock `RequestHeadersUriSpec`, `RequestHeadersSpec`, `ResponseSpec`, or other intermediate interfaces. The test observes requests at the HTTP boundary.

## 4. Checking Request Body, Headers, and Response of a POST

For clients sending data, the mock server can inspect the JSON request body and return a corresponding response.

Suppose an adapter creates orders:

```java
public record CreateOrderRequest(String sku, int quantity) {
}

public record OrderResponse(long id, String status) {
}

public class OrderHttpAdapter {

    private final RestClient restClient;

    public OrderHttpAdapter(RestClient restClient) {
        this.restClient = restClient;
    }

    public OrderResponse create(CreateOrderRequest request) {
        return restClient.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(OrderResponse.class);
    }
}
```

Test verifying method, URL, content type, and JSON body:

```java
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.http.HttpMethod.POST;

@Test
void shouldSendOrderAsJsonAndReadCreatedOrder() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://orders.example");
    MockRestServiceServer server = MockRestServiceServer
            .bindTo(builder)
            .build();

    OrderHttpAdapter adapter = new OrderHttpAdapter(builder.build());

    server.expect(requestTo("https://orders.example/api/orders"))
            .andExpect(method(POST))
            .andExpect(header("Content-Type", MediaType.APPLICATION_JSON_VALUE))
            .andExpect(content().json("""
                    {"sku":"SKU-1","quantity":2}
                    """))
            .andRespond(withSuccess(
                    """
                    {"id":101,"status":"CREATED"}
                    """,
                    MediaType.APPLICATION_JSON
            ));

    OrderResponse response = adapter.create(new CreateOrderRequest("SKU-1", 2));

    assertThat(response).isEqualTo(new OrderResponse(101L, "CREATED"));
    server.verify();
}
```

The `content().json(...)` expectation compares JSON structure. It avoids coupling the test to whitespace or property ordering in the JSON string. If ordering or exact byte formatting is genuinely part of the contract to verify, a stricter body matcher can be used.

## 5. Checking Error Statuses and How the Adapter Handles Exceptions

An HTTP adapter must do more than read successful responses. It also needs clear behavior when the external service returns `4xx` or `5xx`, times out, or returns an error body violating the schema.

By default, `RestClient.retrieve()` converts error-range response statuses into exceptions such as `HttpClientErrorException` or `HttpServerErrorException`. The adapter may let the exception propagate, or register `onStatus(...)` to map it to a business domain exception.

Example of an adapter mapping 404 to a custom exception:

```java
public class InventoryItemNotFoundException extends RuntimeException {
    public InventoryItemNotFoundException(String sku) {
        super("Inventory item not found: " + sku);
    }
}

public class InventoryHttpAdapter implements InventoryGateway {

    private final RestClient restClient;

    public InventoryHttpAdapter(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public InventoryItem findBySku(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .onStatus(status -> status.value() == 404, (request, response) -> {
                    throw new InventoryItemNotFoundException(sku);
                })
                .body(InventoryItem.class);
    }
}
```

The mock server can return 404 and the test asserts the exception:

```java
server.expect(requestTo("https://inventory.example/api/inventory/MISSING"))
        .andRespond(withStatus(HttpStatus.NOT_FOUND));

assertThatThrownBy(() -> adapter.findBySku("MISSING"))
        .isInstanceOf(InventoryItemNotFoundException.class)
        .hasMessage("Inventory item not found: MISSING");

server.verify();
```

This test verifies that the adapter reacts properly to the actual HTTP status returned by the mock server. If the adapter has no custom error-mapping logic, you can assert `RestClient`'s default exception.

## 6. Testing `RestTemplate` with the Same Approach

`RestTemplate` is Spring's long-standing synchronous HTTP client. `MockRestServiceServer` supports binding directly to a `RestTemplate` instance:

```java
RestTemplate restTemplate = new RestTemplate();
MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();

server.expect(requestTo("https://catalog.example/api/products/42"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"id":42,"name":"Keyboard"}
                """,
                MediaType.APPLICATION_JSON
        ));

Product product = restTemplate.getForObject(
        "https://catalog.example/api/products/{id}",
        Product.class,
        42
);

assertThat(product).isEqualTo(new Product(42L, "Keyboard"));
server.verify();
```

The core principle stays the same as with `RestClient`: the test uses a real `RestTemplate` and mocks the server at the HTTP layer. There is no need to mock internal client components.

## 7. Testing `WebClient` with a Mock HTTP Server

`WebClient` has a fluent and reactive API. It returns `Mono` or `Flux`, so deep stubbing is often even more complicated. For an adapter using `WebClient`, a mock HTTP server such as OkHttp `MockWebServer` or WireMock lets requests travel through `WebClient`'s real HTTP stack.

Example adapter:

```java
public class ReactiveInventoryClient {

    private final WebClient webClient;

    public ReactiveInventoryClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<InventoryItem> findBySku(String sku) {
        return webClient.get()
                .uri("/api/inventory/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(InventoryItem.class);
    }
}
```

Test with `MockWebServer`:

```java
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import reactor.test.StepVerifier;

class ReactiveInventoryClientTest {

    private MockWebServer server;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void shouldCallInventoryEndpointAndDecodeResponse() throws Exception {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""
                        {"sku":"SKU-1","availableQuantity":12}
                        """));

        WebClient webClient = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();
        ReactiveInventoryClient client = new ReactiveInventoryClient(webClient);

        StepVerifier.create(client.findBySku("SKU-1"))
                .expectNext(new InventoryItem("SKU-1", 12))
                .verifyComplete();

        RecordedRequest request = server.takeRequest();
        assertThat(request.getMethod()).isEqualTo("GET");
        assertThat(request.getPath()).isEqualTo("/api/inventory/SKU-1");
        assertThat(request.getHeader("Accept")).contains("application/json");
    }
}
```

`MockWebServer` opens an ephemeral loopback port and returns enqueued responses. `WebClient` sends the request through its normal HTTP connector; `StepVerifier` subscribes to the `Mono`, waits for the outcome, and verifies the emitted item. The test then inspects `RecordedRequest` to verify the method, path, and headers sent.

Tests need the appropriate test dependencies, typically OkHttp MockWebServer and `reactor-test`. Use versions compatible with Java and the project's dependency management.

### Testing Error Responses in WebClient

`WebClient`'s `retrieve()` produces `WebClientResponseException` for error statuses by default. You can enqueue a 404 response and verify the error with Reactor Test:

```java
server.enqueue(new MockResponse().setResponseCode(404));

StepVerifier.create(client.findBySku("MISSING"))
        .expectError(WebClientResponseException.NotFound.class)
        .verify();
```

If the adapter uses `onStatus(...)` to map exceptions, tests can assert the corresponding domain exception. This genuinely exercises `WebClient`'s status handling rather than stubbing a `Mono.error(...)` in the middle of a fluent chain.

## 8. When to Mock an Interface vs. When to Mock HTTP?

The two types of tests answer two different questions:

| Test goal | How to replace dependency | What the test verifies |
| --- | --- | --- |
| Unit test business service | Mock interface such as `InventoryGateway`. | Business rules and how the service reacts to data/results from the gateway. |
| Test HTTP adapter using `RestClient` | `MockRestServiceServer` bound to `RestClient.Builder`. | Method, URL, headers, request body, response status, and deserialization. |
| Test HTTP adapter using `RestTemplate` | `MockRestServiceServer` bound to `RestTemplate`. | Request/response via synchronous HTTP client. |
| Test HTTP adapter using `WebClient` | `MockWebServer` or WireMock. | Real request through HTTP connector, reactive body, and status handling. |
| Integration test with real service | Test environment or service container. | Interoperability with a real server and inter-service contracts in a near-real environment. |

An easy rule to apply: mock at boundaries owned by the application; use a mock server at HTTP boundaries. Avoid deep-mocking intermediate fluent objects of the framework.

## 9. Using Spring Boot `@RestClientTest` When Appropriate

If the project uses Spring Boot, `@RestClientTest` provides a test slice for REST-calling components. It can configure the needed client components and `MockRestServiceServer` to test the adapter without loading the full application.

General example:

```java
@RestClientTest(InventoryHttpAdapter.class)
class InventoryHttpAdapterBootTest {

    @Autowired
    private InventoryHttpAdapter inventoryHttpAdapter;

    @Autowired
    private MockRestServiceServer server;

    @Test
    void shouldReadInventoryItem() {
        server.expect(requestTo("https://inventory.example/api/inventory/SKU-1"))
                .andRespond(withSuccess(
                        """
                        {"sku":"SKU-1","availableQuantity":12}
                        """,
                        MediaType.APPLICATION_JSON
                ));

        assertThat(inventoryHttpAdapter.findBySku("SKU-1"))
                .isEqualTo(new InventoryItem("SKU-1", 12));

        server.verify();
    }
}
```

`@RestClientTest` is a Spring Boot feature, not a core Spring Framework annotation. Auto-configuration and server binding capabilities depend on the Boot version and client type used. On Boot versions supporting `RestClient`, you can use this test slice to configure the builder and mock server; if your project uses another version, check that exact version's documentation or configure the builder/server explicitly as in the earlier example.

## 10. What Mock HTTP Servers Verify and Their Limitations

A mock HTTP server verifies many important behaviors at the client boundary:

- The HTTP method and URL sent by the adapter.
- Path variables, query parameters, and encoding.
- Request headers such as `Accept`, `Content-Type`, authorization, or correlation ID.
- Serialized JSON request bodies or other payloads.
- Response status, response headers, and body.
- JSON mapping, error handling, and how the adapter converts data into domain types.

However, a mock server does not prove the external service is up or that its contract has not changed. Nor does it replace testing networking, TLS, DNS, load balancers, real infrastructure timeouts, or interactions with a stateful live system.

When those behaviors matter, integration tests using containers or the service's test environment can supplement unit/adapter tests. There is no need to turn every unit test into an end-to-end test; pick test levels according to risk and the contract to verify.

## 11. Common Test Design Mistakes

**Mocking the entire fluent chain of `RestClient` or `WebClient`.**

Tests become coupled to method call order and fail to verify real requests. Mock a business interface for services, or use a mock HTTP server for adapters.

**Using `RETURNS_DEEP_STUBS` to avoid creating intermediate mocks.**

Deep stubs make tests shorter but no more meaningful if the entire HTTP exchange is faked. They hide URL, header, serialization, and status-handling bugs.

**Mocking `RestClient` in unit tests and concluding the adapter sent the right request.**

Mocking a client object only confirms stubbed interactions. To verify HTTP requests, use `MockRestServiceServer` or an equivalent mock server.

**Forgetting to call `server.verify()`.**

Without `verify`, unfulfilled expectations might go unreported in the way the test intends. Call `verify()` to confirm expected requests occurred.

**Binding the mock server after building the client.**

For `RestClient`, bind `MockRestServiceServer` to the builder before calling `builder.build()`. If the client was already built with another request factory, the mock server may not sit on the client's request path.

**Skipping request header or body checks.**

A right mock response does not prove the request was right. Set expectations on headers, method, URL, and body belonging to the outbound contract.

**Using `MockRestServiceServer` for every client type.**

`MockRestServiceServer` fits `RestClient` and `RestTemplate`. For `WebClient`, typically use MockWebServer or WireMock to verify requests through the HTTP connector.

**Testing only success responses.**

Clients must handle 404, 4xx, 5xx, malformed bodies, and network errors per the contract. Add tests for important failure scenarios.

## 12. Workflow for Choosing a Testing Strategy

When a service uses an HTTP client, classify what needs verification first:

1. If testing business decisions, define an interface at the application boundary and mock that interface.
2. If testing an adapter making HTTP calls, keep the real HTTP client and connect it to a mock HTTP server.
3. For `RestClient` or `RestTemplate`, consider `MockRestServiceServer`.
4. For `WebClient`, use MockWebServer or WireMock and verify reactive outcomes with `StepVerifier` as needed.
5. Set expectations for request method, URL, query, headers, and body.
6. Return mock responses representing both success and error scenarios.
7. Assert the DTO, exception, or domain result returned by the adapter.
8. Call `verify()` or inspect recorded requests to ensure requests were sent properly.
9. Use a real server or service container only when verifying behavior that a mock server cannot prove.

## Conclusion

Deeply mocking an HTTP client's fluent chain usually ties tests to implementation details and skips the very HTTP behavior needing verification. For business logic, mock a narrow interface owned by the application. For HTTP adapters, use the real client connected to a mock HTTP server to verify method, URL, headers, body, status, and data conversion.

`MockRestServiceServer` is the right fit for `RestClient` and `RestTemplate`; `MockWebServer` or WireMock fits `WebClient`. Dividing boundaries this way keeps tests focused on the contract each layer owns and makes them resilient when internal fluent chains change.
