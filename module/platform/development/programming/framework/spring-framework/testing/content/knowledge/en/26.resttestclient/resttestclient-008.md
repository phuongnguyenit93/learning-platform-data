# Choosing RestTestClient, WebTestClient, or MockMvc by Version and Model

Spring provides multiple ways to send requests and verify responses when testing web applications. Three commonly considered APIs are `MockMvc`, `WebTestClient`, and `RestTestClient`. They share similar syntax in some areas, yet are designed for different application models and testing needs.

`MockMvc` is a tool for testing the Spring MVC layer directly on a simulated Servlet API. `WebTestClient` is an asynchronous HTTP client best suited for Spring WebFlux, and can also connect to a real server or use an adapter for Spring MVC. `RestTestClient` is a newer synchronous HTTP client based on `RestClient` that can test Spring MVC via MockMvc or send requests to a running server.

Choosing among them requires looking at two factors: whether the application uses Spring MVC or WebFlux, and whether tests should run at the mock layer or over real HTTP. The Spring version also matters because `RestTestClient` is only available starting in Spring Framework 7.0.

## 1. Three Tools Solving Different Needs

### MockMvc

`MockMvc` belongs to Spring MVC Test in the `spring-test` module. It executes requests through `DispatcherServlet` and Spring MVC components, using mock Servlet requests/responses instead of opening an HTTP port.

MockMvc fits when the application uses Spring MVC and tests need to inspect Servlet/MVC-layer details such as:

- Request mapping and selected handler method.
- Binding of `@PathVariable`, `@RequestParam`, `@RequestBody`, and validation.
- Message converters, formatters, interceptors, and controller advice.
- Model, view, flash attributes, and exception resolution.
- Servlet filters registered in MockMvc.
- Async requests via `MvcResult` and `asyncDispatch(...)`.

Example:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsOrder() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 42)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42));
    }
}
```

MockMvc offers rich matchers such as `status()`, `header()`, `content()`, `jsonPath()`, `handler()`, `model()`, and `view()`. Tests can obtain `MvcResult` to inspect the handler, resolved exception, request, response, or async details.

MockMvc does not test TCP connections, TLS, connectors, reverse proxies, or application deployment on a Servlet container. It verifies the Spring MVC processing flow in a mock environment.

### WebTestClient

`WebTestClient` belongs to Spring WebFlux and was introduced in Spring Framework 5.0. It is an asynchronous HTTP client built on `WebClient`, featuring an expectation-chain API for response testing.

With WebFlux, WebTestClient can bind directly to a controller, application context, or router function to run tests without a server. It can also connect to a running server for end-to-end tests.

Example testing WebFlux with an application context:

```java
@SpringJUnitConfig(WebFluxConfig.class)
class ReactiveOrderControllerTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(ApplicationContext context) {
        client = WebTestClient.bindToApplicationContext(context).build();
    }

    @Test
    void returnsOrder() {
        client.get()
                .uri("/api/orders/{id}", 42)
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo(42);
    }
}
```

WebTestClient can also be used with Spring MVC. In that case, use `MockMvcWebTestClient` to create a client backed by MockMvc:

```java
WebTestClient client = MockMvcWebTestClient
        .bindToApplicationContext(webApplicationContext)
        .build();
```

This is an adapter allowing WebTestClient's client API to be used in MVC tests. Requests are still processed by MockMvc and mock Servlets; there is no real HTTP socket.

WebTestClient is useful when you want a consistent test API for WebFlux and real HTTP, or when testing reactive streams, SSE, and asynchronous scenarios. It requires the corresponding WebFlux/Reactor libraries on the classpath.

### RestTestClient

`RestTestClient` was introduced in Spring Framework 7.0. It is a synchronous HTTP client built on Spring `RestClient`, adding a response-testing facade.

RestTestClient can bind to a controller, Spring application context, or router function to test with mock requests/responses. It can also connect to a running server via `bindToServer()`.

Example binding to an MVC application context:

```java
@SpringJUnitConfig(WebMvcConfig.class)
class OrderRestTestClientTest {

    private RestTestClient client;

    @BeforeEach
    void setUp(WebApplicationContext context) {
        client = RestTestClient.bindToApplicationContext(context).build();
    }

    @Test
    void returnsOrder() {
        client.get()
                .uri("/api/orders/{id}", 42)
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody(OrderResponse.class)
                .consumeWith(result -> assertThat(
                        result.getResponseBody().getId()).isEqualTo(42));
    }
}
```

RestTestClient's request API matches `RestClient` up to `exchange()`. After that, tests use expectations such as `expectStatus()`, `expectHeader()`, and `expectBody()`. Spring also provides `RestTestClientResponse` for AssertJ-style assertions.

RestTestClient is a natural choice for synchronous MVC applications when the team wants an API resembling a real HTTP client and wants the same test style for both mock setups and live servers. It is not a reactive client like WebTestClient.

## 2. Version Milestones to Remember

| Tool | Spring Framework version | Notes |
| --- | --- | --- |
| MockMvc | Available since Spring Framework 3.2 | Tests Spring MVC via simulated Servlet API |
| WebTestClient | Available since Spring Framework 5.0 | Asynchronous client; primarily for WebFlux, usable with MVC via `MockMvcWebTestClient` |
| RestTestClient | Available since Spring Framework 7.0 | Synchronous client based on `RestClient`; supports mock MVC setup and real server |

From this we can deduce:

- Spring Framework 5.x or 6.x projects can use MockMvc and WebTestClient, but do not yet have `RestTestClient`.
- Spring Framework 7.x projects can consider all three tools.
- Spring Boot 3.x manages Spring Framework 6.x, so it does not provide `RestTestClient` from Spring Framework.
- Spring Boot 4.x manages Spring Framework 7.x, so it can use `RestTestClient` and its corresponding test configurations.

Do not add a separate newer `spring-test` version into a project using older Spring modules. Let Spring Boot dependency management or a single BOM align versions across all Spring modules.

## 3. Choosing by Application Model

### Spring MVC Applications

Spring MVC runs on the Servlet API. Synchronous controllers are commonly tested directly with MockMvc.

Choose MockMvc when:

- You need Spring MVC-specific matchers such as handler, model, view, flash attributes, or async results.
- You need to inspect `DispatcherServlet`, Servlet request attributes, filters, or exception resolvers.
- You want fast MVC slice tests with `@WebMvcTest`.
- The project does not yet use Spring Framework 7.0.

Choose RestTestClient when:

- The project already uses Spring Framework 7.0 or later.
- You want to write tests with a synchronous API similar to `RestClient`.
- You want the same request/expectation style to work with MockMvc setups and real servers.
- Most tests do not need access to `MvcResult`-specific internals.

Choose WebTestClient for MVC when:

- The team has standardized tests on the WebTestClient API.
- You need to share test style between MVC and WebFlux.
- You want to leverage the asynchronous client API and switch from mock MVC to a live server.

When using WebTestClient with MVC, remember to use `MockMvcWebTestClient` for mock setups. Do not call `WebTestClient.bindToApplicationContext(...)` with an MVC context the WebFlux way.

### Spring WebFlux Applications

WebFlux uses a reactive model with `WebHandler`, Reactor, and types like `Mono`/`Flux`. MockMvc is not a WebFlux testing tool because it is based on the Servlet API and Spring MVC.

WebTestClient is the appropriate default choice for WebFlux because:

- It can bind to controllers, application contexts, or router functions.
- It can verify `Mono`, `Flux`, streaming responses, and SSE.
- It supports serverless tests or connecting to a running server.
- Its request/response API is designed for asynchronous HTTP flows.

RestTestClient is a synchronous client. Although it can send requests to a running HTTP server, it does not replace WebTestClient when reactive behavior, backpressure, or reactive streaming needs verification.

### Applications with Both Spring MVC and WebFlux on the Classpath

Spring Boot usually prefers Spring MVC if both Spring MVC and WebFlux appear on the classpath. Therefore, do not infer the application context type solely from the presence of the `spring-webflux` dependency.

Explicitly determine the web application type and test the right model:

- MVC: use MockMvc, RestTestClient bound to MockMvc, or WebTestClient via `MockMvcWebTestClient`.
- WebFlux: use WebTestClient with a WebFlux application context or live server.

If you need to test WebFlux in a project containing both stacks, configure the reactive web application type for the test context or separate the appropriate test configuration.

## 4. Choosing by Test Scope: Mock vs. Real HTTP

Another important factor is how far the test needs to execute.

| Scope | MockMvc | WebTestClient | RestTestClient |
| --- | --- | --- | --- |
| Standalone controller without starting server | Yes | Yes; MVC via `MockMvcWebTestClient` | Yes from Framework 7.0 |
| Spring application context with mock request/response | Yes | Yes; MVC via adapter or direct WebFlux context | Yes from Framework 7.0 |
| WebFlux reactive controller | No | Yes | Not the right choice for checking reactive semantics |
| Router function | Not the primary API for WebFlux routers | Yes for WebFlux routers | Has router function binding via RestTestClient API |
| HTTP over a real network port | No | Yes via `bindToServer()` | Yes via `bindToServer()` |
| Servlet container, TLS, connector, and network behavior | No | Yes when connecting to a live server | Yes when connecting to a live server |

### Mock Setup

A mock setup invokes the framework's processing infrastructure directly with mock requests/responses. It is usually faster and easier to isolate. However, tests do not verify connectors, TLS, real server context paths, proxies, or container-dependent behavior.

MockMvc example:

```java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
```

RestTestClient example:

```java
RestTestClient client = RestTestClient
        .bindToApplicationContext(webApplicationContext)
        .build();
```

WebTestClient example for WebFlux:

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .build();
```

### Live Server Setup

If real HTTP needs testing, the application must be started and the client must send requests over the network. Both WebTestClient and RestTestClient can bind to a running server:

```java
WebTestClient webClient = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

RestTestClient restClient = RestTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

With Spring Boot, you can start the server on a random port:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureRestTestClient
class OrderHttpIntegrationTest {

    @Test
    void servesOrderOverHttp(@Autowired RestTestClient client) {
        client.get()
                .uri("/api/orders/{id}", 42)
                .exchange()
                .expectStatus().isOk()
                .expectBody(OrderResponse.class)
                .consumeWith(result -> assertThat(
                        result.getResponseBody().getId()).isEqualTo(42));
    }
}
```

In Spring Boot 4, you can use `@AutoConfigureRestTestClient` to configure RestTestClient for tests. For WebTestClient, use `@AutoConfigureWebTestClient` and ensure the appropriate WebFlux dependency is on the classpath. Boot annotations and packages can change across major versions; consult the documentation for the exact version you manage.

MockMvc has no live server mode. If real HTTP is needed for an MVC application, use RestTestClient or WebTestClient against a running server.

## 5. Comparing Request and Assertion APIs

| Task | MockMvc | WebTestClient | RestTestClient |
| --- | --- | --- | --- |
| Build GET request | `perform(get("/path"))` | `get().uri("/path")` | `get().uri("/path")` |
| Execute request | `perform(...)` | `exchange()` | `exchange()` |
| Check status | `andExpect(status().isOk())` | `expectStatus().isOk()` | `expectStatus().isOk()` |
| Check headers | `andExpect(header()...)` | `expectHeader()...` | `expectHeader()...` |
| Check JSON | `jsonPath(...)` | `expectBody().jsonPath(...)` | `expectBody().jsonPath(...)` |
| Read object | Deserialize from response or `jsonPath` | `expectBody(Type.class)` | `expectBody(Type.class)` |
| Client type | Servlet MVC test API | Reactive/non-blocking | Synchronous/blocking |
| Access MVC result details | Directly via `MvcResult` | Via MockMvc adapter if needed | Depends on API; can use client's response result |

Example of the same goal with all three APIs:

```java
// MockMvc
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42));

// WebTestClient
webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);

// RestTestClient
restTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
```

WebTestClient and RestTestClient look quite similar in syntax. The key difference lies in execution model: WebTestClient is a reactive client, whereas RestTestClient is a synchronous client.

## 6. Dependencies and Configuration by Version

### Spring Boot 3.x Projects

Spring Boot 3.x uses Spring Framework 6.x. Projects can use MockMvc and WebTestClient, but cannot yet use `RestTestClient` because that class does not exist in Spring Framework 6.x.

For MVC tests, `spring-boot-starter-test` provides common testing libraries, including Spring Test. MVC projects need the corresponding web starter. If you want to use WebTestClient, add the Spring WebFlux dependency and configure the appropriate client/adapter.

### Spring Boot 4.x Projects

Spring Boot 4.x uses Spring Framework 7.x, so RestTestClient can be used. Boot provides dedicated auto-configuration for test clients. For MVC slice tests, check the appropriate annotation for mock transport; for full `@SpringBootTest`, `@AutoConfigureRestTestClient` can configure the corresponding client.

Boot 4 splits some test modules and packages compared to Boot 3. Do not copy Boot 3 imports into Boot 4 if packages have moved. Let the Boot BOM manage versions and check the dependencies/starters for the major version.

### Non-Boot Spring Framework Projects

Declare the required modules with the same Spring version:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.springframework:spring-webmvc")
    testImplementation("org.springframework:spring-webflux")
}
```

This configuration snippet only illustrates the relevant Spring modules. Add `spring-webflux` only if tests use WebTestClient; pure MVC applications do not need WebFlux just to use MockMvc or RestTestClient. Use dependency management/BOM or declare consistent versions across modules.

On Framework 6.x, you cannot make `RestTestClient` available by adding `spring-test` 7.x alone to the project. Upgrade Spring Framework consistently to 7.x if you want to use the new client.

## 7. Integrating Spring Security and Filters

All three clients can send requests through security configuration depending on how they are bound.

With MockMvc, when building from `WebApplicationContext` manually, add the Spring Security filter chain if authorization needs testing:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

With WebTestClient using the MockMvc adapter, ensure the underlying MockMvc is configured with the filter chain. With RestTestClient bound to an application context, use the actual MVC/security configuration loaded in the context. With a live server, requests pass through the filter chain running in the server.

In every case, merely attaching a mock user to a request does not prove the filter chain participated. Tests must exercise the actual security path the application uses.

## 8. Quick Selection Criteria

| Scenario | Preferred choice | Reason |
| --- | --- | --- |
| Spring MVC, needing mapping, model, view, handler, or `MvcResult` checks | MockMvc | Deeply tailored API for Servlet MVC |
| Spring MVC, wanting a synchronous HTTP-client-like API, Spring 7+ | RestTestClient | RestClient-based API, bindable to MockMvc or server |
| Spring MVC, wanting a shared API with WebFlux | WebTestClient via `MockMvcWebTestClient` | Shared client API while MVC still runs through MockMvc |
| Spring WebFlux reactive | WebTestClient | Fits Reactor, async, and streaming |
| Spring MVC on Spring Framework 6.x | MockMvc or WebTestClient adapter | RestTestClient does not exist in Framework 6.x |
| Spring MVC on Spring Framework 7.x | MockMvc or RestTestClient; WebTestClient when needed | Choose by MVC depth vs. HTTP client style |
| Testing over real HTTP port with synchronous client | RestTestClient (7.0+) | Real HTTP communication with synchronous API |
| Testing over real HTTP port with reactive client | WebTestClient | Asynchronous client suited for streaming |
| Testing Servlet container or TLS | RestTestClient/WebTestClient bound to server | Requires a real server; MockMvc does not open sockets |

## 9. Common Misconceptions

### Thinking WebTestClient Is Only for WebFlux

WebTestClient is designed primarily for WebFlux but can be used with Spring MVC via `MockMvcWebTestClient`. When using the adapter, requests are still handled by MockMvc. This helps share test APIs without turning an MVC application into WebFlux.

### Thinking MockMvc Tests Real HTTP

MockMvc calls `DispatcherServlet` in the same process with mock Servlets. It does not send requests over TCP. To test server, connector, TLS, or proxy behavior, start a server and use an HTTP client.

### Thinking RestTestClient Exists in Spring Boot 3.4 Because MockMvcTester Exists

`MockMvcTester` was introduced in Spring Framework 6.2, whereas `RestTestClient` was introduced in Spring Framework 7.0. These are two different APIs. Spring Boot 3.4 may support MockMvcTester yet still use Framework 6.2 without RestTestClient.

### Using RestTestClient Instead of WebTestClient for Every Reactive Application

RestTestClient is a synchronous client. It does not offer the same reactive model as WebTestClient. For WebFlux, streaming, SSE, or verifying reactive behavior, WebTestClient is generally more suitable.

### Using MockMvc for WebFlux Controllers

MockMvc is based on the Servlet API and Spring MVC. WebFlux uses `WebHandler` and the reactive stack. Use WebTestClient for WebFlux instead of trying to fit WebFlux controllers into MockMvc.

### Assuming Mock Binding and Live Server Are Equivalent

A client may support both mock binding and live server, yet their test scopes differ. Mock binding does not test networking or containers. Live server tests are slower and require managing ports, environment, data, and transactions properly.

## 10. Combining Tools in a Project

A project does not need to pick only one tool for all tests. You can layer them:

1. Use MockMvc for most MVC slice tests verifying mapping, binding, validation, and exception handling.
2. Use RestTestClient if a Spring Framework 7+ project wants to test MVC with a synchronous HTTP API and reuse client configuration.
3. Use WebTestClient for WebFlux controllers, reactive flows, streaming, or when the team wants one shared client API across the reactive stack and real servers.
4. Use a handful of live server tests with RestTestClient or WebTestClient to verify HTTP ports, real filters, containers, and deployment configuration.

There is no need to migrate all MockMvc tests to another client just because a new API appeared. Keep the tool best matched to the behavior being verified and upgrade along with the Spring version chosen by the project.

## 11. Decision Workflow

Before choosing a tool, answer in order:

1. Is the application Spring MVC or Spring WebFlux?
2. Does the test need to verify MVC/Servlet details or just send an HTTP request and assert the response?
3. Does the test need mock requests/responses or a connection to a running server?
4. Is the current Spring Framework version 6.x or 7.x?
5. Does the team need a synchronous client like RestClient or a reactive client like WebClient?
6. Does the test need access to `MvcResult`, handler, model, view, or async dispatch?

If it is MVC and needs Servlet details, prefer MockMvc. If it is WebFlux, prefer WebTestClient. If it is synchronous MVC on Framework 7+ and you want an HTTP client facade able to switch between mock and live servers, consider RestTestClient. When real HTTP is needed, choose RestTestClient or WebTestClient bound to a running server.

## 12. References

- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Framework — RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)

## 13. Conclusion

MockMvc is a specialized tool for Spring MVC and simulated Servlet requests. WebTestClient is a reactive client best suited for WebFlux, though it can also test MVC via `MockMvcWebTestClient`. RestTestClient is the new synchronous client from Spring Framework 7.0, suited for MVC and bindable to either a mock context or a real server.

Choose according to application model, test scope, and Spring version in use. Use MockMvc for MVC needing `MvcResult` details; use WebTestClient for WebFlux and reactive streaming; consider RestTestClient for synchronous MVC on Spring 7+ wanting an HTTP client API. For any requirement involving networking or a real Servlet container, use a server-bound client rather than mock-only tests.
