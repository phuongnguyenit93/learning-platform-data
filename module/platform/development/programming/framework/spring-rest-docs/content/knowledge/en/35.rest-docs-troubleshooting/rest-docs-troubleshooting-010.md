# Behavioral Differences Between MockMvc and WebTestClient

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, we generate verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests and verify responses, while Spring REST Docs produces snippets for requests, responses, payloads, parameters, and headers. These snippets are assembled with Asciidoctor/Markdown and integrated into the build and CI pipeline.

Both MockMvc and WebTestClient can test Spring MVC, yet they simulate requests through two different models. MockMvc invokes Spring MVC directly via a mocked Servlet API; WebTestClient uses a reactive client API and can either bind to an application in memory or send HTTP requests to a running server. Because of this, the same endpoint can exhibit differences in initialization, async handling, filters, codecs, URIs, and how responses are observed.

This lesson helps diagnose differences between the two tools and choose the right configuration for Spring REST Docs. After this lesson, you will be able to:

- Distinguish the execution models of MockMvc and WebTestClient.
- Choose the appropriate binding mode for Spring MVC, WebFlux, or a real server.
- Understand differences in Servlet filters, WebFilters, message converters, and codecs.
- Handle async responses and reactive publishers properly.
- Configure REST Docs for both clients and compare their generated snippets.
- Diagnose why status, headers, body, or URI differ between two tests.

## 2. Core Differences in Execution Models

### 2.1. MockMvc

MockMvc tests a Spring MVC application without starting a real HTTP server. It constructs mock Servlet request/response objects and invokes the Spring MVC infrastructure inside the test process.

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42));
~~~

MockMvc is well-suited for verifying controller mappings, argument binding, validation, exception handling, response serialization, Servlet filters, and Spring MVC interceptors in a test setup. MockMvc does not test TCP connections, reverse proxies, TLS termination, or production server network configuration.

### 2.2. WebTestClient

WebTestClient provides a WebClient-style fluent API for sending requests and asserting responses. It supports several binding modes:

- `bindToController(...)`: sets up WebFlux or controller configuration in memory.
- `bindToApplicationContext(...)`: binds to an application context.
- `bindToRouterFunction(...)`: binds directly to a WebFlux `RouterFunction`.
- `bindToServer()`: sends HTTP requests to a running server.
- `bindToServer().baseUrl(...)`: configures a real server address.

Example binding to a controller:

~~~java
WebTestClient client = WebTestClient
    .bindToController(new OrderController(orderService))
    .build();

client.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo(42);
~~~

WebTestClient is not synonymous with WebFlux. It can also test Spring MVC via a mock server adapter or send HTTP requests to a running Servlet server. Check the specific binding mode before concluding which stack a test is exercising.

## 3. Quick Comparison Table

| Aspect | MockMvc | WebTestClient |
| --- | --- | --- |
| Test API | Servlet MVC test API | Fluent client API, based on WebClient |
| App invocation | Directly via mock Servlet infrastructure | In-memory binding or real HTTP server |
| Spring MVC | Direct support | Can test via mock server adapter or real server |
| Spring WebFlux | Not intended for WebFlux | Native support |
| HTTP server/network | Starts no real server/network | Only when using `bindToServer` or a real server |
| Async/reactive | Supports Servlet async via MockMvc mechanism | Supports reactive responses and publisher assertions |
| Request body | Servlet request builder | Body inserters and client API |
| Response body | MockMvc result matchers | `expectBody`, `returnResult`, and WebTestClient matchers |
| REST Docs | `MockMvcRestDocumentation` | `WebTestClientRestDocumentation` |
| Best suited for | Spring MVC apps needing fast MVC-layer tests | WebFlux, shared fluent API, or testing over real HTTP |

Do not choose a tool based solely on syntax. Choose according to the layer you need to verify: controller/MVC behavior, reactive pipeline, or HTTP server and network boundary.

## 4. Choosing the Right WebTestClient Binding Mode

### 4.1. `bindToController`

This binding creates a client attached to the controller and WebFlux components configured for the test:

~~~java
WebTestClient client = WebTestClient
    .bindToController(new GreetingController())
    .build();
~~~

Suitable for small, isolated controller tests. If the controller depends on services, validators, converters, or exception advice, supply the relevant components or use an application context to test a fuller configuration.

### 4.2. `bindToApplicationContext`

Binding to a context uses the loaded Spring Web configuration:

~~~java
@Autowired
WebApplicationContext context;

WebTestClient client = MockMvcWebTestClient
    .bindToApplicationContext(context)
    .build();
~~~

The snippet above uses Spring Test's `MockMvcWebTestClient` to use the WebTestClient API on top of the Spring MVC mock infrastructure. It still does not start a real server.

For a WebFlux application context, bind WebTestClient using the corresponding WebFlux test setup:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .build();
~~~

The context type and configuration must match the application stack. Do not use a Servlet `WebApplicationContext` setup for a WebFlux reactive context.

### 4.3. `bindToServer`

When you need to test a real HTTP server:

~~~java
WebTestClient client = WebTestClient
    .bindToServer()
    .baseUrl("http://localhost:8080")
    .build();
~~~

The client sends requests over HTTP to the server. This exercises the embedded server, Servlet/WebFlux runtime, local network stack, and real filter/container configurations. It also ties tests to the server lifecycle, port, and startup time.

If you need to verify TLS, a reverse proxy, or a gateway, tests must traverse that boundary; `bindToServer` against `localhost` does not verify a production proxy on its own.

## 5. Why Can the Same Endpoint Produce Different Results?

Two tests may differ because they do not travel through the same pipeline:

~~~mermaid
flowchart TD
    A["Test request"] --> B{"Client / binding"}
    B --> C["MockMvc"]
    B --> D["WebTestClient in-memory"]
    B --> E["WebTestClient HTTP server"]
    C --> F["Mock Servlet request"]
    D --> G["Mock WebHandler / MVC adapter"]
    E --> H["HTTP connector + server runtime"]
    F --> I["Controller / MVC pipeline"]
    G --> I
    H --> I
    I --> J["Response"]
~~~

Components that can cause differences:

- Servlet filters and Servlet container behavior.
- WebFlux `WebFilter`s and reactive handler chains.
- MVC `HttpMessageConverter` vs. WebFlux `HttpMessageReader`/`HttpMessageWriter`.
- Content negotiation and default media types.
- Async dispatch, deferred results, and reactive publisher completion.
- Context path, servlet path, base URL, and proxy forwarding headers.
- Security configuration and filter ordering.
- Exception resolvers/advice loaded in a test slice vs. the full context.

When results diverge, identify which layer introduced the difference before changing assertions or documentation.

## 6. Differences Between Servlet Filters and WebFilters

Spring MVC typically uses Servlet `Filter`s, `HandlerInterceptor`s, and the Spring Security filter chain. WebFlux uses `WebFilter` and the reactive security chain. A filter registered in a Servlet container does not automatically run in a WebFlux pipeline.

Examples:

- A MockMvc test runs through Servlet filters if the test setup registers those filters.
- A WebTestClient bound to a WebFlux context runs through `WebFilter`s.
- A WebTestClient using `bindToServer` runs through the filter/handler chain of the running server.

If an `X-Request-Id` header appears in MockMvc's response but is missing in WebTestClient, check what produces that header: a Servlet filter, `WebFilter`, controller advice, or gateway.

Do not manually inject headers in tests just to make snippets match if the real application does not guarantee that header. Decide whether the header belongs to the API contract or is merely an environment detail.

## 7. Message Converters and Codecs

Spring MVC uses `HttpMessageConverter` to read request bodies and write response bodies. WebFlux uses codecs (`HttpMessageReader`/`HttpMessageWriter`) on the reactive stack.

Configurations that may differ:

- Jackson `ObjectMapper` and registered modules.
- Java time serialization and date formats.
- Naming strategies or property inclusion rules.
- `Content-Type` and `Accept` negotiation.
- Handling of empty bodies, `null`, and streaming media types.

For example, a date field in a response can be formatted differently if two application contexts use differently configured `ObjectMapper` beans. Before changing snippets, compare the actual converter/codec configurations.

Check the response content type:

~~~java
// MockMvc
mockMvc.perform(get("/api/orders/42"))
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON));
~~~

~~~java
// WebTestClient
client.get()
    .uri("/api/orders/42")
    .exchange()
    .expectHeader()
    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON);
~~~

If bodies differ while statuses match, compare raw responses, content types, and serialization configurations before troubleshooting REST Docs.

## 8. Async and Reactive Responses

### 8.1. Servlet Async with MockMvc

Spring MVC can return asynchronous results via `Callable`, `DeferredResult`, or `WebAsyncTask`. MockMvc provides async dispatch support:

~~~java
MvcResult result = mockMvc.perform(get("/api/report"))
    .andExpect(request().asyncStarted())
    .andReturn();

mockMvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andDo(document("reports/get"));
~~~

If you document the operation before async dispatch completes, the snippet may not represent the final response. Wait for the async result and perform the dispatch properly.

### 8.2. Reactive Responses with WebTestClient

WebTestClient awaits the exchange and can assert bodies on publishers:

~~~java
client.get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk()
    .expectBodyList(OrderResponse.class)
    .hasSize(2);
~~~

For streaming endpoints such as Server-Sent Events or unbounded `Flux` streams, do not collect an infinite body. Test a bounded number of items with timeouts and check the appropriate media type/stream events.

### 8.3. Do Not Confuse Async with Reactive

Servlet async still runs on Servlet MVC; returning a reactive publisher does not automatically turn an endpoint into WebFlux. Verify the controller's return type, dispatcher, and runtime before choosing how to test it.

## 9. Request URI, Context Path, and Base URL

MockMvc requests typically simulate internal paths:

~~~java
mockMvc.perform(get("/api/orders/42")
        .contextPath("/store"))
    .andExpect(status().isOk());
~~~

WebTestClient server binding uses the server address:

~~~java
WebTestClient client = WebTestClient
    .bindToServer()
    .baseUrl("http://localhost:8080/store")
    .build();
~~~

Do not include the same prefix in both `baseUrl` and the request URI if it produces `/store/store/api/orders`. Distinguish:

- Public base URL: scheme, host, port, and prefix used by clients.
- Context path: root of the web application in the Servlet container.
- Servlet path: path mapped to the servlet.
- Endpoint path: controller or router path mapping.

To keep snippets consistent, configure REST Docs URI documentation separately from the URI the test client actually sends. Do not use the documented URI modifier to fix test request routing.

## 10. Configuring Spring REST Docs for MockMvc

Use `MockMvcRestDocumentation.documentationConfiguration(...)` in the MockMvc builder:

~~~java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
        .apply(documentationConfiguration(restDocumentation))
        .build();
}
~~~

Documenting an operation:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42))
    .andExpect(status().isOk())
    .andDo(document("orders/get"));
~~~

Spring REST Docs records snippets from the mock request/response produced by MockMvc. Configure the documented host/scheme/port via the URI configurer if needed:

~~~java
documentationConfiguration(restDocumentation).uris()
    .withScheme("https")
    .withHost("api.example.com")
    .withPort(443);
~~~

## 11. Configuring Spring REST Docs for WebTestClient

Use `WebTestClientRestDocumentation.documentationConfiguration(...)`:

~~~java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.webTestClient = WebTestClient
        .bindToApplicationContext(this.applicationContext)
        .configureClient()
        .filter(documentationConfiguration(restDocumentation))
        .build();
}
~~~

Required static and class imports:

~~~java
import org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation;
import org.springframework.restdocs.RestDocumentationContextProvider;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;
~~~

Then document the operation:

~~~java
webTestClient.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get"));
~~~

API names and overloads may vary by Spring REST Docs version; use your project's dependency version as the reference. The key point is applying the WebTestClient REST Docs filter to the client before calling `exchange()` and attaching `document(...)` to the response operation.

## 12. `MockMvcWebTestClient`: Using the WebTestClient API with Spring MVC

Spring Test includes `MockMvcWebTestClient`, which lets you use the fluent WebTestClient API to test Spring MVC via MockMvc infrastructure:

~~~java
WebTestClient client = MockMvcWebTestClient
    .bindToApplicationContext(context)
    .build();
~~~

After the exchange, you can obtain the `MvcResult` if you need Servlet-layer assertions:

~~~java
EntityExchangeResult<byte[]> result = client.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .returnResult();

MockMvcWebTestClient.resultActionsFor(result)
    .andExpect(handler().handlerType(OrderController.class));
~~~

This is a useful bridge when you want fluent client assertions while still verifying MVC handler details. It does not convert the application into WebFlux and does not start a real HTTP server.

When combining with Spring REST Docs, pick the integration matching the active client/API and verify snippet output. Never apply two REST Docs filters simultaneously to the same operation.

## 13. Comparing Snippets from Both Clients

When documenting the same endpoint with both MockMvc and WebTestClient, you may use the same operation identifier in two separate test suites, but avoid concurrent snippet overwrites or nondeterministic output.

Compare:

| Snippet | What to cross-check |
| --- | --- |
| `http-request` | Method, URI, query parameters, headers, and body. |
| `http-response` | Status, headers, media type, and body. |
| `request-fields` | Field paths, types, optional/ignored flags, and descriptions. |
| `response-fields` | JSON schema, nullability, and nested paths. |
| `path-parameters` | Parameter names, positions, and descriptions. |
| `response-headers` | Actual headers and contract semantics. |

If both tests model the same public contract, differences in snippets usually signal something worth investigating. However, not every byte must match: request host, port, runtime headers, or formatting can vary due to binding mode.

## 14. Diagnostic Table for Common Differences

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| MockMvc returns 200, WebTestClient returns 404 | Different URI/base path, context path, or router mapping | Print request URI; confirm binding mode and controller mapping. |
| MockMvc has security header, WebTestClient does not | Servlet Filter vs. WebFilter difference, or filter unregistered in test | Identify the header-producing component and check each stack's security chain. |
| JSON body has different formatting | Different `ObjectMapper`/converter/codec config | Compare application contexts, converters, and codec customizers. |
| MockMvc test times out on async | Async result not dispatched or timeout configured too short | Use `asyncStarted`, `asyncDispatch`, and appropriate timeouts. |
| WebTestClient body is empty | Publisher never emitted, handler returned empty, or wrong body extractor chosen | Check status, content type, publisher, and `expectBody`/`expectBodyList`. |
| Snippet URI has duplicated prefix | Prefix configured in both `baseUrl` and request URI | Separate public base URL, context path, and endpoint path. |
| Response headers differ only under `bindToServer` | Server filter/container/gateway adds or strips headers | Compare in-memory binding against the real HTTP server. |
| Exception bodies differ | Advice not loaded or different handlers across contexts | Check `@ControllerAdvice` scan/import and exception types. |
| REST Docs snippets not generated | Filter/`documentationConfiguration` not attached or document consumer not called | Check client setup, exchange chain, and output directory. |
| Individual test passes, suite fails | Shared state, port, generated snippets, or test ordering | Use context/test isolation and unique operation identifiers. |

## 15. Systematic Investigation Workflow

When the two clients yield different results, follow this order:

1. **Confirm the runtime:** Is the app Spring MVC or WebFlux? Is WebTestClient bound in-memory or to an HTTP server?
2. **Compare the requests:** Are method, URI, context path, headers, content type, and body identical?
3. **Compare the pipelines:** Which Servlet filters, WebFilters, interceptors, security chains, and exception advice ran?
4. **Compare serialization:** Are converters/codecs, `ObjectMapper`, and content negotiation identical?
5. **Check async behavior:** Has the response completed, and has the publisher emitted and completed?
6. **Inspect raw responses:** Check status, headers, and body before REST Docs preprocessing.
7. **Inspect snippets:** Verify the REST Docs filter applied properly and no operation overwrote another.
8. **Pick the right test boundary:** Mock tests for controller contracts, server-bound tests for HTTP runtime, external integration tests for proxies/gateways.

Do not edit documentation to hide unexplained differences. Snippets must reflect verified responses; if two runtimes have different contracts, documentation must describe the variants accurately or the system should unify the contract.

## 16. Asciidoctor and CI Integration

Asciidoctor includes snippets generated by tests:

~~~asciidoc
== Get Order

=== HTTP request
include::{snippets}/orders/get/http-request.adoc[]

=== HTTP response
include::{snippets}/orders/get/http-response.adoc[]

=== Response fields
include::{snippets}/orders/get/response-fields.adoc[]
~~~

A Gradle task configuration can wire tests and Asciidoctor:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

Run:

~~~bash
./gradlew clean test asciidoctor
~~~

If two test suites generate snippets for the same operation, configure separate output directories or designate one suite as the primary snippet source. Prevent parallel tests from overwriting the same files.

## 17. Common Errors and Fixes

| Error | Cause | Fix |
| --- | --- | --- |
| Using WebTestClient and assuming tests hit real HTTP | Client is bound via `bindToApplicationContext` or `bindToController` | Switch to `bindToServer` when a server boundary is needed. |
| Using MockMvc to test TLS/proxy | MockMvc does not open network/TLS connections | Run tests against a real HTTP server/gateway. |
| WebTestClient does not run Servlet filters | Test uses WebFlux pipeline or filter is unregistered | Confirm runtime and register filters on the right stack. |
| Confusing `MockMvcWebTestClient` with WebFlux | It is an adapter over Spring MVC mock infrastructure | Use a WebFlux context/client when testing the reactive stack. |
| Response snippets differ due to codecs | Inconsistent serializer configuration | Share configuration or document intentional differences. |
| Async snippet captures incomplete response | Final result was not dispatched or consumed | Complete the async flow before documenting the operation. |
| REST Docs snippets not found | Filter unconfigured or `document(...)` missing | Apply `documentationConfiguration` and consumer properly. |
| Snippets overwritten across suites | Shared operation identifier/output path | Separate outputs or serialize snippet-generating suites. |

## 18. Hands-On Practice

1. Create a simple GET endpoint in Spring MVC and document it with MockMvc.
2. Test the same controller with `MockMvcWebTestClient` and compare fluent assertions.
3. Create a WebFlux handler and document it with WebTestClient bound to the application context.
4. Run a local server and use `bindToServer()` to test the HTTP boundary.
5. Compare response headers and JSON serialization across binding modes.
6. Create one Servlet Filter and one WebFilter that add a correlation ID; observe which tests pass through each filter.
7. Create an MVC async endpoint and test it with `asyncDispatch`.
8. Create a reactive endpoint returning a finite `Flux` and verify the body with WebTestClient.
9. Generate snippets into separate directories per suite, then assemble the chosen snippet set into Asciidoctor.
10. Run Gradle/CI and confirm tests and documentation do not overwrite each other's outputs.

## 19. Key Takeaways

- MockMvc tests Spring MVC via mock Servlet infrastructure without starting a real HTTP server.
- WebTestClient is a fluent HTTP test client; its binding mode determines whether it tests in-memory or against a real server.
- `MockMvcWebTestClient` lets you use the WebTestClient API on top of Spring MVC mock infrastructure; it is not a WebFlux runtime.
- Servlet Filters and WebFlux WebFilters belong to two separate pipelines.
- MVC converters and WebFlux codecs can introduce serialization and content-negotiation differences.
- Complete Servlet async dispatch or reactive exchanges before documenting the response.
- Configure REST Docs independently for MockMvc and WebTestClient; avoid having two suites overwrite the same snippets.
- Use mock tests for controller contracts and server-bound tests when verifying HTTP runtime and network boundaries.

## 20. References

- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): testing Spring MVC with mock Servlet APIs.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): binding modes and testing WebFlux/MVC via WebTestClient.
- [Spring REST Docs — MockMvc](https://docs.spring.io/spring-restdocs/reference/working-with-mockmvc.html): integrating REST Docs with MockMvc.
- [Spring REST Docs — WebTestClient](https://docs.spring.io/spring-restdocs/reference/working-with-webtestclient.html): integrating REST Docs with WebTestClient.
