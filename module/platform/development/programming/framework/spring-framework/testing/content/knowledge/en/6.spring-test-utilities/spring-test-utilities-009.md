# Differences Between Mock API Objects and a Real HTTP Server

When testing Spring applications, you can either simulate requests and responses using objects provided by Spring Test, or start a real HTTP server and send requests over the network. These two approaches test different boundaries of the application. Choosing the right one keeps tests fast and stable while still catching bugs in the infrastructure layer that needs protection.

Mock objects such as `MockHttpServletRequest`, `MockHttpServletResponse`, `MockServerHttpRequest`, `MockServerHttpResponse`, and `MockServerWebExchange` simulate Servlet or WebFlux contracts in memory. `MockMvc` and `WebTestClient` can use these mock objects to exercise part or most of Spring's web pipeline without opening an HTTP port. When you need to test connectors, sockets, the HTTP protocol, or real server configuration, you must send requests to a running server.

## 1. Two testing approaches sit at different boundaries

**Mock API objects** construct objects representing a request, response, session, or exchange. The test passes them directly to the component under test. No client connects over a socket and no server connector processes the request.

**A real HTTP server** starts a server such as Tomcat, Jetty, Undertow, or Reactor Netty, and then uses an HTTP client to send requests to the port the server is listening on. Requests traverse the connector and the application's actual web pipeline.

| Aspect | Mock API objects / mock web environment | Real HTTP server |
|---|---|---|
| Invocation | Calls component with mock objects or uses an in-memory bound test client | HTTP client sends requests to host and port |
| Sockets and network | No real network connection | Real HTTP connection, typically over loopback in local tests |
| Server connector | Does not test the server connector | Tests the connector and request intake process |
| HTTP parsing/framing | Represented by mock objects and test framework | Handled by the server connector |
| Spring MVC/WebFlux pipeline | Can be tested directly or via a mock server adapter | Runs through the pipeline inside a live server |
| Speed | Typically fast with fewer environment dependencies | Slower due to server startup and HTTP communication |
| Isolation | Easy to set up request and dependencies per test | Requires managing ports, resources, data, and server lifecycle |
| Bugs best caught | Controller/filter/handler logic, binding, validation, and responses within mock scope | Server integration, connector, port, protocol, and runtime configuration bugs |

Mock API objects are not business mocks in the Mockito sense. They are test implementations of web contracts provided by Spring so components can be tested without a real container.

## 2. Web testing levels in Spring

Not all tests using mock objects share the same scope. They can be grouped into these levels:

```text
Component unit test
  Mock request/response/exchange
  Directly calls interceptor, filter, or handler
          |
          v
In-memory Spring web test
  MockMvc or WebTestClient bound to controller/context
  Runs Spring web pipeline without opening an HTTP server
          |
          v
Integration test with a real server
  Starts embedded server
  Sends HTTP requests through client and connector
```

Each level adds a layer of infrastructure to the test scope. When a test fails, a narrower scope usually makes the cause easier to pinpoint. When you need to verify multiple infrastructure layers working together, pick a broader test level.

## 3. Mock API objects in Spring MVC

Spring Test provides several mock objects for the Servlet API in the `org.springframework.mock.web` package, such as:

- `MockHttpServletRequest`: simulates request method, URI, parameters, headers, body, session, and attributes.
- `MockHttpServletResponse`: captures response status, headers, cookies, redirects, and body content.
- `MockHttpSession`: simulates a server-side session.
- `MockServletContext`: simulates ServletContext.
- `MockFilterChain`: supports testing Servlet Filters.
- `MockServletConfig`: simulates servlet configuration.

These objects are useful when calling a component that depends directly on the Servlet API, such as a `HandlerInterceptor`, `Filter`, adapter, or a request-reading utility class.

### 3.1. Calling a component directly with mock request/response

Example of an interceptor that reads a header and adds a response header:

```java
public class RequestIdInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        String requestId = request.getHeader("X-Request-Id");
        if (requestId == null || requestId.isBlank()) {
            response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            return false;
        }

        response.setHeader("X-Request-Id", requestId);
        return true;
    }
}
```

A unit test can construct the request and response in memory:

```java
@Test
void copiesRequestIdToResponse() throws Exception {
    var request = new MockHttpServletRequest("GET", "/orders");
    var response = new MockHttpServletResponse();
    request.addHeader("X-Request-Id", "req-42");

    boolean proceed = new RequestIdInterceptor()
            .preHandle(request, response, new Object());

    assertTrue(proceed);
    assertEquals("req-42", response.getHeader("X-Request-Id"));
}
```

This test checks the interceptor's logic and how it interacts with the Servlet API. It does not prove that the interceptor is registered in `HandlerInterceptorRegistry`, attached to the right URL pattern, or invoked during a real request. Those concerns belong to MVC configuration tests.

### 3.2. MockMvc: running the Spring MVC pipeline without a real server

`MockMvc` provides a fluent API to send requests and verify responses. It runs `DispatcherServlet` and MVC components in a mock Servlet environment without starting Tomcat, Jetty, or another Servlet server.

Example:

```java
mockMvc.perform(get("/api/orders/42")
        .header("X-Request-Id", "req-42"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.id").value(42));
```

There are two common ways to build `MockMvc`:

```java
// Quick setup with controller and minimal MVC infrastructure
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController(orderService))
        .build();

// Use the application's Spring WebApplicationContext
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
```

`standaloneSetup` suits focused controller tests where you explicitly supply the controller and required components. `webAppContextSetup` uses the Spring MVC configuration in `WebApplicationContext`, making it suitable when you need to test mappings, converters, formatters, validators, controller advice, or MVC configuration registered in the context. Filters can be added to MockMvc through the appropriate builder configuration.

In Spring Boot, `@WebMvcTest` is commonly used to load an MVC slice and provide `MockMvc`:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void returnsOrderWhenItExists() throws Exception {
        when(orderService.findById(42L))
                .thenReturn(new OrderResponse(42L, "PENDING"));

        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.status").value("PENDING"));
    }
}
```

The example uses hypothetical application classes `OrderController`, `OrderService`, and `OrderResponse`. `@WebMvcTest` is a Spring Boot Test annotation; in plain Spring Framework, you can build `MockMvc` with `MockMvcBuilders`.

MockMvc exercises many parts of Spring MVC such as handler mappings, argument resolvers, data binding, validation, exception resolvers, message converters, and response status. However, it does not test a real Servlet container, sockets, TLS, HTTP framing, or connector behavior.

## 4. Mock API objects in Spring WebFlux

WebFlux has its own reactive server contract, so Servlet mocks are not used to test components accepting `ServerWebExchange`.

Common mock objects include:

- `MockServerHttpRequest`: creates a reactive request in memory.
- `MockServerHttpResponse`: captures status, headers, cookies, and body written via `DataBuffer`.
- `MockServerWebExchange`: bundles request, response, session, and context of an exchange.

Example testing a `WebFilter` directly:

```java
var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/orders")
                .header("X-Tenant-Id", "tenant-a")
                .build());

WebFilterChain chain = nextExchange -> {
    nextExchange.getResponse().setStatusCode(HttpStatus.OK);
    return nextExchange.getResponse().setComplete();
};

filter.filter(exchange, chain).block();

assertEquals(HttpStatus.OK, exchange.getResponse().getStatusCode());
```

This is a unit test for the filter and exchange. `block()` is used only at the synchronous test boundary to await publisher completion. In production WebFlux code, compose `Mono`/`Flux` and keep the flow reactive.

### 4.1. WebTestClient can run in memory or against a real server

`WebTestClient` is an HTTP client for testing Spring web applications. It offers a consistent API for crafting requests and asserting responses, while its execution scope depends on how it is bound:

| Binding method | Scope |
|---|---|
| `bindToController(...)` | Controller and minimal mock infrastructure |
| `bindToApplicationContext(...)` | WebFlux application context in a mock environment |
| `bindToRouterFunction(...)` | Router function and corresponding handlers |
| `bindToServer()` | Connects to a running HTTP server over the network |

Example binding to a controller:

```java
WebTestClient client = WebTestClient
        .bindToController(new OrderController(orderService))
        .build();

client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
```

This example uses in-memory test infrastructure. Even though the API looks like an HTTP client, it does not open a socket to a real server.

For Spring MVC, `MockMvcWebTestClient` also lets you use `WebTestClient`'s fluent API on top of MockMvc. Therefore, inspect how the client is bound rather than looking only at the class name to tell whether a test uses the network.

## 5. Testing with a real HTTP server

A test using a real server must start the application or server first, obtain the listening address/port, and send requests with an HTTP client. In Spring Boot, `@SpringBootTest` provides web environment modes to control server startup.

| `webEnvironment` | Behavior |
|---|---|
| `MOCK` | Creates a mock web application context; does not start an embedded server |
| `RANDOM_PORT` | Starts an embedded server on a random port |
| `DEFINED_PORT` | Starts an embedded server on the configured port, typically `server.port` |
| `NONE` | Creates a non-web ApplicationContext |

`MOCK` usually fits MockMvc or context tests. `RANDOM_PORT` fits when you need to test requests through a real connector without depending on a fixed port. `DEFINED_PORT` can be used when a test requires a known port, though it can easily collide with other processes on a machine or in CI.

### 5.1. Spring MVC with an embedded server and TestRestTemplate

For Spring Boot MVC applications, you can use `RANDOM_PORT` and `TestRestTemplate`:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @Autowired
    private TestRestTemplate http;

    @Test
    void returnsOrderThroughRealHttpServer() {
        ResponseEntity<OrderResponse> response = http.getForEntity(
                "/api/orders/42", OrderResponse.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(42L, response.getBody().id());
    }
}
```

`TestRestTemplate` is provided by Spring Boot for testing web applications. With `RANDOM_PORT`, Boot configures the client to send requests to the running embedded server. Requests travel through the server connector and application pipeline like real HTTP requests.

### 5.2. WebFlux with an embedded server and WebTestClient

For reactive applications, you can bind `WebTestClient` to the running server:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveOrderHttpIntegrationTest {

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
    void returnsOrderThroughRealHttpServer() {
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo(42);
    }
}
```

The example uses Spring Boot Test's `@LocalServerPort` and `WebTestClient.bindToServer()`. Depending on the Spring version or application setup, you can use Spring Boot's auto-configured WebTestClient; what matters is confirming the client is bound to the real server address. If `bindToApplicationContext` is used, the test runs in memory and does not exercise the connector.

### 5.3. What gets tested when going through a real server

Requests sent through a real server can verify parts that mock environments do not fully cover:

- Server connector accepting connections, managing ports, and handling request lines/headers/bodies.
- HTTP protocol, header/body size limits, and certain framing behaviors.
- TLS/HTTPS when tests are configured with corresponding certificates and connectors.
- Compression, connection handling, timeouts, and server configuration.
- Context path, forwarded headers, or proxy configuration when set up.
- Coordination across the server, Spring application context, filter chain, controller/handler, and serialization.

Coverage depends on the server and configuration started in the test. For example, a local HTTP test does not verify TLS unless the connector enables HTTPS; an embedded server test also does not prove that a production reverse proxy or load balancer works properly.

## 6. Differences in reliability and cost

Mock tests usually run fast because no server is started and no socket communication takes place. Input data is built directly, making tests repeatable and easy to isolate to a single logic branch. This fits many controller, filter, interceptor, converter, and handler tests.

Server integration tests carry a higher cost because they must start infrastructure and wait on HTTP clients. In exchange, they catch bugs that only appear when requests pass through a connector, such as port settings, protocol behavior, header parsing, body size limits, codecs, or server-specific behavior. They also verify that the application can start under the chosen deployment configuration.

Do not judge test quality solely by whether a real server is used. A real-server test that only hits one simple endpoint may protect few business rules; a well-designed mock unit test can verify dozens of logic branches at high speed. Identify each test's goal and choose the smallest boundary capable of proving that behavior.

## 7. Transactions and data in real-server tests

One common source of confusion is test transactions.

In tests using Spring TestContext and `@Transactional`, a transaction is typically opened around the test method and rolled back when the test finishes. This works well for persistence tests running on the same thread and transaction context.

When a test sends HTTP requests to an embedded server, the request is handled on a server thread and business transactions are opened on the request-handling side. That transaction is independent of the test method's transaction. Consequently, annotating the test method with `@Transactional` does not automatically roll back database changes committed by server requests.

For example, if a test calls `POST /orders` via `TestRestTemplate`, the request may commit the order on the server. When the test ends, the test method's transaction does not wrap the server transaction. The test must clean up data via APIs, repositories, or appropriate fixture cleanup, or use an isolated database/schema per the project's strategy.

In both mock and server tests, prepare data with unique identifiers, avoid execution-order dependencies, and ensure cleanup does not delete another test's data.

## 8. What mock tests can and cannot prove

| Question | Mock object / MockMvc / in-memory WebTestClient | Real HTTP server |
|---|---|---|
| Does the controller return the right status and body? | Yes, along the constructed mock pipeline | Yes |
| Are Spring MVC validation and exception handling correct? | Yes, when using the matching MVC configuration | Yes |
| Does the WebFilter or WebHandler handle the exchange properly? | Yes, when called directly or bound to a WebFlux context | Yes |
| Are converters/formatters registered in the context? | Yes, if the test uses the corresponding application context | Yes |
| Are filters/interceptors registered in the application? | Possibly, if the test loads full application configuration | Yes |
| Are the port and connector actually listening? | No | Yes |
| Server TLS handshake and HTTP framing? | No | Yes, if configured for the test |
| Do client and server communicate over sockets? | No | Yes |
| Production proxy/load balancer behavior? | No | Only if the test goes through that infrastructure |

Mock tests can still use a real Spring application context. Here "mock" refers to the simulated request/response or web environment, not that every bean in the application is a mock. Conversely, a server integration test can still mock a business dependency if the goal is solely to test the server and HTTP pipeline.

## 9. Choosing the right tool for each goal

| Test goal | Tool to consider | Reason |
|---|---|---|
| Standalone interceptor/filter logic | `MockHttpServletRequest`/`MockHttpServletResponse` or `MockServerWebExchange` | Invokes component directly with mock request/response |
| Spring MVC mappings, binding, validation, and responses | `MockMvc` | Runs `DispatcherServlet` and MVC infrastructure in memory |
| Spring WebFlux controllers, routers, or filter chains | `WebTestClient` bound to controller/application context; mock exchange for lower-level components | Tests reactive web pipeline at the needed scope |
| Application starts and listens on a port properly | `@SpringBootTest(RANDOM_PORT)` with an HTTP client | Requires a real running embedded server |
| Server connector, HTTPS, HTTP limits, or server configuration | HTTP client sending to a real server | These behaviors lie outside mock APIs |
| Integration flows across multiple services and external infrastructure | Integration test with server and appropriate test dependencies | Verifies the relevant integration boundaries |

A balanced test suite usually contains many unit tests and mock web tests, a set of context or database integration tests, and a small number of real-server tests for behaviors that depend on connectors or deployment configuration. The exact ratio varies by application; no single number fits every module.

## 10. Workflow for deciding test scope

Before writing a test, answer these questions:

1. Does the component under test accept the Servlet API, the WebFlux API, or plain Java data?
2. Is the goal a single component's logic, the Spring web pipeline, or HTTP communication through a server?
3. Do you need to verify `DispatcherServlet`, WebFlux handler chains, converters, validators, or filter registration?
4. Do you need to check connectors, ports, TLS, HTTP framing, timeouts, or server-specific configuration?
5. Does the test depend on a database, session, security context, locale, or external state?
6. If sending requests through a real server, which thread/transaction commits data and how will it be cleaned up?
7. Which ports, JDK, and dependencies does the test require in local/CI runs?

If you are only testing a request-handling rule, mock objects or in-memory bound MockMvc/WebTestClient are usually enough. If you need to protect how Spring configures and wires components, use an application context test. If the behavior to verify lives in the server connector or real HTTP transport, start a server and send requests with a real client.

When these boundaries are clearly separated, each test shows exactly what it protects. Mock API objects keep web logic testing fast and controllable; a real HTTP server verifies that the application works through real connectors and protocols. Combining them purposefully yields a Spring test suite that is fast in daily development and reliable enough for integration and deployment.
