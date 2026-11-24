# Comparing Mocked Results with HTTP Through a Real Server

## 1. Why Test at Both Levels?

In Spring, an endpoint can be tested using MockMvc or WebTestClient bound to mock infrastructure. This approach sends requests through Spring web components and checks status, headers, and bodies without starting a server listening on a network port.

An HTTP integration test, by contrast, starts a real server—typically via Spring Boot on a random port—and sends requests over HTTP. Requests travel through the connector, socket, and servlet/reactive server before reaching the application.

The two testing levels answer different questions:

- **Mocked testing** verifies routing, binding, validation, controllers, exception handling, and response contracts inside the web infrastructure configured by the test.
- **HTTP testing through a real server** verifies that those components work when actual HTTP requests arrive at the server, while also exercising the connector, port, filter chain, and how clients receive responses.

A passing mocked test does not prove the application binds a port or that the HTTP connector works. Nor does a passing HTTP test replace all mocked tests: starting a server is typically slower and makes isolating small branches harder.

A strong test suite uses each level for its right purpose, then compares the same API contract to surface meaningful discrepancies.

## 2. Distinguishing MockMvc, WebTestClient, and a Real HTTP Client

### MockMvc

**MockMvc** is part of Spring Test and tests Spring MVC using mock servlet requests and responses. Requests are dispatched through MVC components such as DispatcherServlet, handler mappings, controllers, argument resolvers, message converters, and exception resolvers.

MockMvc does not open a TCP socket and does not require Tomcat, Jetty, or a servlet container listening on a port. It can still test many Spring MVC components, including filters if those filters are registered in the test configuration.

~~~java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42));
~~~

### WebTestClient

**WebTestClient** can run in several modes:

- Bound directly to a controller or RouterFunction.
- Bound to a mock ApplicationContext.
- Bound to a running server over real HTTP.

Therefore, merely seeing WebTestClient in source code is not enough to conclude whether a test uses sockets. Check how the client is constructed:

~~~java
WebTestClient.bindToApplicationContext(context)
        .build();
~~~

This is mock web infrastructure.

~~~java
WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

This is an HTTP client connecting to a running server.

### HTTP Client Through a Real Server

With Spring Boot, a test can start an embedded server on a random port:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {
}
~~~

Then use TestRestTemplate, RestTestClient (when supported by the Spring version), or WebTestClient bound to the server to send requests.

| Testing Approach | Server Listening on Port? | Real HTTP Socket? | Main Target Verified |
|---|---:|---:|---|
| MockMvc | No | No | Spring MVC request processing |
| WebTestClient bound to controller/context | No | No | WebFlux/MVC mock infrastructure |
| WebTestClient bound to server | Yes | Yes | HTTP through a running server |
| TestRestTemplate / RestTestClient bound to server | Yes | Yes | HTTP through a running server |
| Client calling staging through proxy | Yes | Yes | Application plus infrastructure layers on the request path |

## 3. Using the Same Endpoint for a Fair Comparison

Suppose the application provides an endpoint to read an order:

~~~java
public record OrderResponse(
        Long id,
        String orderNumber,
        String status
) {
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public OrderResponse getOrder(@PathVariable Long id) {
        return orderService.findById(id);
    }
}
~~~

The service returns the order or throws an exception if not found:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderResponse findById(Long id) {
        Order order = repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        return new OrderResponse(
                order.getId(),
                order.getOrderNumber(),
                order.getStatus()
        );
    }
}
~~~

To compare results across the two levels, control the inputs. For example, both tests create an order with order number ORD-42 and status PAID, then call GET /api/orders/{id}.

Do not compare a MockMvc test that mocks OrderService against an HTTP test hitting a real database and conclude any difference is caused by transport. Those two tests use different configurations and dependencies. If you want to isolate the effect of transport, keep the controller, service, repository, configuration, and fixtures identical; change only how the request is sent.

## 4. Organizing Two Tests Sharing the Same Application Logic

You can use two Spring Boot test styles:

- **webEnvironment = MOCK** combined with **@AutoConfigureMockMvc** to test via MockMvc.
- **webEnvironment = RANDOM_PORT** to start an embedded server and send real HTTP.

Both load the Spring Boot application. The key difference lies in the web environment and the client used to send requests.

### Mocked Test with MockMvc

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class OrderMockMvcIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderRepository orderRepository;

    private Long orderId;

    @Test
    void shouldReturnTheStoredOrder() throws Exception {
        Order saved = orderRepository.save(
                new Order("ORD-42", "PAID")
        );
        orderId = saved.getId();

        mockMvc.perform(get("/api/orders/{id}", orderId)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(saved.getId()))
                .andExpect(jsonPath("$.orderNumber").value("ORD-42"))
                .andExpect(jsonPath("$.status").value("PAID"));
    }

    @AfterEach
    void cleanUp() {
        if (orderId != null) {
            orderRepository.deleteById(orderId);
        }
    }
}
~~~

This test loads the application and calls through Spring MVC infrastructure. It verifies routing the request to the controller, querying the service/repository, converting the DTO to JSON, and building the response.

It does not test embedded server port binding, TCP connections, or the HTTP connector.

### Test Over Real HTTP

With Spring Boot, you can use TestRestTemplate:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderRepository orderRepository;

    private Long orderId;

    @Test
    void shouldReturnTheStoredOrderOverHttp() {
        Order saved = orderRepository.save(
                new Order("ORD-42", "PAID")
        );
        orderId = saved.getId();

        ResponseEntity<OrderResponse> response = http.getForEntity(
                "/api/orders/{id}",
                OrderResponse.class,
                orderId
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getHeaders().getContentType())
                .isCompatibleWith(MediaType.APPLICATION_JSON);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().id()).isEqualTo(saved.getId());
        assertThat(response.getBody().orderNumber()).isEqualTo("ORD-42");
        assertThat(response.getBody().status()).isEqualTo("PAID");
    }

    @AfterEach
    void cleanUp() {
        if (orderId != null) {
            orderRepository.deleteById(orderId);
        }
    }
}
~~~

Here, Spring Boot starts an embedded server on a random port and configures TestRestTemplate to call that server. Requests pass through the HTTP connector before reaching DispatcherServlet.

If the project uses Spring Framework 7 and the corresponding Spring Boot version, you can use RestTestClient:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderRestTestClientIntegrationTest {

    @Autowired
    RestTestClient client;

    @Test
    void shouldReturnAnOrderOverHttp() {
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo(42)
                .jsonPath("$.status").isEqualTo("PAID");
    }
}
~~~

RestTestClient must be connected to a real server. If the client is created with a mock binding instead, the test no longer tests HTTP sockets.

## 5. Comparing the Same Response Contract

Compare the parts of the contract that the API guarantees to clients:

| Response Part | What to Verify |
|---|---|
| Status | HTTP code matches business outcome |
| Content-Type | Appropriate media type, e.g., application/json |
| Business headers | Location, ETag, Cache-Control, or headers published by the API |
| Body | Correct fields, data types, and values |
| Error response | Consistent status and error schema |
| Cookie/session | Proper behavior if the API uses cookies or sessions |
| Security | Unauthenticated or unauthorized requests handled properly |
| Encoding | Content decoded properly according to contract |

Every header does not have to be identical across both environments. For instance, headers related to framing, body length, connections, or server implementation may differ due to how responses are written on the transport.

Headers such as Transfer-Encoding, Content-Length, Connection, Date, or container-specific headers should not be compared as part of the API contract unless the product explicitly requires them.

Similarly, do not compare raw JSON strings when property order or whitespace is not part of the contract. Use JSONPath or structural JSON assertions to inspect the content.

## 6. Creating Shared Assertions for the Same Response Contract

If multiple test clients need to assert the same schema, you can extract assertions into a helper. Example with AssertJ:

~~~java
static void assertOrderResponse(
        OrderResponse actual,
        Long expectedId,
        String expectedNumber,
        String expectedStatus
) {
    assertThat(actual).isNotNull();
    assertThat(actual.id()).isEqualTo(expectedId);
    assertThat(actual.orderNumber()).isEqualTo(expectedNumber);
    assertThat(actual.status()).isEqualTo(expectedStatus);
}
~~~

The HTTP test can call the helper after receiving the DTO. MockMvc can inspect JSONPath directly. If you want to reuse the same helper for both, parse the JSON response into a DTO before comparing, though there is no need to do so if extra parsing adds no value.

Another option is creating a helper that accepts ResultActions or ResponseEntity, but avoid premature abstraction. The two clients have different assertion APIs; keeping the request part explicit often makes tests easier to read.

What matters is that expected values come from fixtures or a shared contract—never compute expected values by calling the very production method under test.

## 7. Comparing Status Codes and Business Errors

Consider a missing-order endpoint. The application can use @ControllerAdvice to convert OrderNotFoundException into HTTP 404:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception
    ) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        exception.getMessage()
                ));
    }
}

public record ApiError(String code, String message) {
}
~~~

MockMvc test:

~~~java
mockMvc.perform(get("/api/orders/999999"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
~~~

HTTP test:

~~~java
ResponseEntity<ApiError> response = http.getForEntity(
        "/api/orders/999999",
        ApiError.class
);

assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
assertThat(response.getBody()).isNotNull();
assertThat(response.getBody().code()).isEqualTo("ORDER_NOT_FOUND");
~~~

Both tests should verify the same status and error code. If MockMvc returns 404 while real HTTP returns 500, check differences in exception resolver configuration, filters, servlet container, or the application configuration loaded in each test.

With TestRestTemplate, 4xx/5xx responses are typically returned inside ResponseEntity in a way that lets tests assert status and body. With RestClient/RestTestClient, status-handling APIs may differ; configure an error handler or use the corresponding expectation API.

## 8. Validation and Request Body

A mocked test can verify that Spring binds JSON to the DTO and runs Bean Validation:

~~~java
public record CreateOrderRequest(
        @NotBlank String orderNumber,
        @NotBlank String status
) {
}
~~~

Controller:

~~~java
@PostMapping("/api/orders")
ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request
) {
    OrderResponse created = orderService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

MockMvc test:

~~~java
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "orderNumber": "",
                          "status": "PAID"
                        }
                        """))
        .andExpect(status().isBadRequest());
~~~

HTTP test sending JSON through the connector:

~~~java
ResponseEntity<ApiError> response = http.postForEntity(
        "/api/orders",
        new CreateOrderRequest("", "PAID"),
        ApiError.class
);

assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
~~~

MockMvc verifies binding/validation inside Spring MVC. The HTTP test also verifies the request body traveling through the HTTP client, connector, and server before Spring processes it. If a request uses special encoding, content length, or chunked transfer, the HTTP test can uncover differences that mocked requests do not simulate.

## 9. Filters, Security, and Web Configuration

MockMvc can run filters and the Spring Security filter chain if they are configured in the test context. However, test configuration can differ from running server configuration if a slice test omits filters or security auto-configuration.

Therefore, when comparing:

- Check whether MockMvc registers the necessary filters.
- Confirm security configuration is loaded in both tests.
- Use the same user, roles, token, or cookies in both requests.
- Verify 401/403 statuses and error bodies against the API contract.
- Check CORS, CSRF, or forwarded headers when they are part of the endpoint's requirements.

For example, MockMvc with Spring Security can attach a user to a request using a post-processor:

~~~java
mockMvc.perform(get("/api/profile").with(user("alice").roles("USER")))
        .andExpect(status().isOk());
~~~

The HTTP test needs to send the credentials a real client would use, such as a bearer token:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);

HttpEntity<Void> request = new HttpEntity<>(headers);

ResponseEntity<ProfileResponse> response = http.exchange(
        "/api/profile",
        HttpMethod.GET,
        request,
        ProfileResponse.class
);

assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
~~~

MockMvc's user(...) post-processor simulates a principal in the test security context. It does not test token parsing or JWT signature verification. An HTTP test with a bearer token goes through the authentication filter and exercises more of the security pipeline.

If you want to test a real JWT decoder or identity provider, configure the test accordingly or use a test environment with a suitable issuer. A localhost request with a fake token does not prove production identity provider integration.

## 10. Differences Caused by the Server and Connector

When an HTTP request reaches a real server, behaviors appear that mock infrastructure cannot fully verify:

- The server actually binds a port and accepts connections.
- The HTTP connector reads the request line, headers, and body from the socket.
- The server enforces the connector's header/body size limits.
- Connections are closed or reused according to server policy.
- The client receives the response over the HTTP stack and decodes the body.
- Compression, chunked transfer, or HTTP versions are handled by the connector if configured.

A few examples of bugs that only appear at the HTTP level:

- Application works fine in MockMvc, yet the server fails to start due to wrong port or connector configuration.
- Overly large headers are rejected by the connector before the request ever reaches the controller.
- Multipart requests behave differently due to upload limits.
- Response streaming gets buffered in the connector or proxy.
- Connections drop when the client disconnects mid-body.
- HTTP/2 or TLS is not enabled as expected in the deployment configuration.

An HTTP integration test with an embedded server can catch bugs in the test server's connector. It does not yet test reverse proxies, ingress, TLS termination, or network policies when requests go straight to localhost.

## 11. Transactions and Test Data Can Cause Different Results

A major difference between MockMvc and real HTTP is the request execution boundary.

MockMvc dispatches requests in the same test process. For synchronous requests, some thread-bound context may exist on the same thread; however, do not assume every async dispatch shares the test's transaction.

With RANDOM_PORT, requests are handled by the server on separate threads or reactive pipelines. The test method's transaction does not automatically cross the HTTP boundary. Consequently, @Transactional on the test will not automatically roll back data written to the database by the endpoint.

To compare both results, use fixtures with explicit lifecycles:

1. Create test records with dedicated IDs or namespaces.
2. Send the request.
3. Assert status and response.
4. Check persistence if that is part of the contract.
5. Delete the exact created records during cleanup.

Do not call deleteAll() in cleanup when other tests may run in parallel against the same database. If two tests need the same data, create the fixture at the start of each test rather than depending on an earlier test.

## 12. Comparing Responses Does Not Mean Raw Bytes Must Match

Mocked responses and responses from a real server can differ in non-contractual details:

| Observable Difference | Why It Can Differ | How to Compare |
|---|---|---|
| JSON has different whitespace or property order | Serializer or rendering path | Parse JSON and compare structure |
| Content-Length differs or is absent | Framing and how response is written | Assert only if explicitly required by API |
| Transfer-Encoding appears | HTTP/1.1 streaming/chunked response | Do not assert as a general business contract |
| Date or Server header differs | Container and execution timestamp | Ignore unless required by specifications |
| Cookie has different attributes | Session/security configuration or domain/path | Assert required security attributes |
| URL in Location differs | Base URL, context path, or proxy headers | Check target URI per contract |
| Error message differs | Exception mapping or environment | Prefer asserting stable error code/schema |
| Charset/encoding differs | Message converter or HTTP headers | Assert media type and decoded content |

If the API guarantees a specific header, test it at both levels. If a header is merely a container-generated detail, forcing both tests to match identically makes tests brittle and fails to reflect the actual contract.

## 13. Testing Multipart, Cookies, and Sessions

MockMvc has an API to construct multipart requests in memory:

~~~java
MockMultipartFile file = new MockMultipartFile(
        "file",
        "report.txt",
        "text/plain",
        "hello".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/files").file(file))
        .andExpect(status().isCreated());
~~~

An HTTP test sends multipart payloads through a real client, exercising multipart framing and server upload limits. If the application accepts large files or uses streaming uploads, testing through a real server is more valuable.

For cookies/sessions, MockMvc can create a session and set attributes directly. An HTTP client must send cookies from a prior response to simulate a client maintaining a session. The two are not completely equivalent: MockMvc can set internal session state, whereas HTTP tests verify cookies emitted and returned over the protocol.

## 14. Async Requests and Streaming

MockMvc supports async requests and can use asyncDispatch to check the response once processing finishes. This is useful for verifying the async lifecycle and final body.

However, MockMvc does not prove the client receives chunks incrementally while the stream stays open, nor does it verify flush timing over a socket.

For SSE or StreamingResponseBody, an HTTP test must read the response while the server is running and verify events/chunks against the contract. Do not compare HTTP chunk boundaries because chunk framing depends on the protocol; check SSE event boundaries or byte contents published by the API.

If an endpoint streams over a long duration, the test must control the server to send the first event, hold the connection open, and only then send the next event or complete. Avoid using Thread.sleep() to guess when events arrive.

## 15. A Test Matrix to Catch Discrepancies

Tests can be organized using the following matrix:

| Scenario | MockMvc / mock-bound client | HTTP through real server |
|---|---|---|
| Successful GET and JSON response | Should have | Should have for critical flows |
| POST creating a resource | Should have | Should have to verify connector and serialization |
| Validation errors | Should have | Include for key contracts |
| Error mapping 404/409/500 | Should have | Should have for critical error paths |
| Security principal/role | Should have | Should have to verify authentication over HTTP |
| Multipart upload | Can check mapping | Needed when upload/connector limits matter |
| Cookie/session | Check MVC/security logic | Needed when verifying cookies over HTTP |
| Async completion | Available via asyncDispatch | Needed when timing/transport matters |
| Incremental streaming/SSE | Only partially testable | Needed |
| TLS, HTTP/2, proxy, network | No | Needs corresponding environment |

You do not need to duplicate every test. Pick a representative set of HTTP integration tests for flows where transport or full application configuration can have an impact. Detailed logic cases can still be tested quickly with MockMvc or WebTestClient mock binding.

## 16. Diagnosing When the Two Test Levels Disagree

If MockMvc passes while the HTTP test fails, determine which layer the request reached:

1. **Server fails to start or connection refused:** check port, server lifecycle, profiles, and connector configuration.
2. **Different HTTP status before reaching controller:** check filters, security, context path, CORS, and connector limits.
3. **Controller is invoked yet body differs:** check message converters, content negotiation, serialization, and request headers.
4. **Only persisted data differs:** check transaction boundaries, fixture setup, cleanup, and shared databases.
5. **Only async/streaming differs:** check timeouts, flushing, buffering, client disconnects, and how the test reads the response.

If the HTTP test passes while MockMvc fails, check whether the MockMvc test loaded the same controller advice, filters, security configuration, message converters, and bean configuration. Slice tests intentionally load only part of the context; that difference may be the cause.

If both tests use the same application context and the same fixtures yet still differ, focus on request/response handling and transport. Record the method, URI, headers, status, content type, and received body to compare them.

## 17. Avoiding Misleading Comparisons or Duplicate Tests

Several practices easily lead to false conclusions:

- **Mocking the service on one side while using a real database on the other:** differences may come from the service/fixture rather than HTTP.
- **Using different auto-generated IDs and comparing full JSON:** differing outputs are normal; compare business fields or use the same fixtures.
- **Comparing raw JSON strings:** field order, whitespace, or formatting can differ even for equivalent JSON.
- **Asserting every header:** container/connector-generated headers can vary across environments.
- **Checking only status:** a 200 status does not prove the body is complete or the schema is right.
- **Running the full suite against a shared database with overly broad cleanup:** tests can interfere with each other.
- **Duplicating every test at both levels:** slows down the suite without a proportional increase in value.

Use a broad mocked test suite for logic branches and response contracts. Then choose a few representative real HTTP flows for features with risk in connectors, filters, security, serialization, persistence, or async transport.

## 18. Choosing the Testing Level

| Question to Answer | Appropriate Testing Level |
|---|---|
| Does the controller map the URI and method correctly? | MockMvc or WebTestClient mock binding |
| Is the DTO validated and serialized properly? | MockMvc/WebTestClient; add HTTP tests for critical contracts |
| Does controller advice return the right error schema? | MockMvc and select HTTP integration tests |
| Does the real security filter chain accept bearer tokens? | HTTP test through a real server; MockMvc complements role branches |
| Does the server bind a port and accept requests? | RANDOM_PORT and HTTP client |
| How does the connector handle multipart/header/body limits? | HTTP test through a real server |
| Does SSE/streaming send data while the connection stays open? | HTTP client reading the stream through a real server |
| Do TLS, ingress, reverse proxy, or DNS work? | Tests through an environment containing those infrastructure layers |

MockMvc and mock-bound WebTestClient verify the behavior of the Spring web layer in a controlled environment. HTTP tests through a real server add evidence that requests and responses pass through the connector just as real clients experience. When comparing, keep the same API contract and fixtures, varying only the transport level under test. That way, a discrepancy in tests points to the part of the system needing investigation rather than an accidental difference between two configurations.

