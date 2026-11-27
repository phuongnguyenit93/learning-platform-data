# Testing Reactive and Asynchronous Documentation

## Learning Objectives

In the **SPRING_REST_DOCS** module, an endpoint can process requests using Spring WebFlux's reactive model or return asynchronous results in Spring MVC. Documentation tests must wait until the response actually completes, assert status/headers/body, and only then hand the exchange to Spring REST Docs to generate snippets.

Two common models:

- **Reactive WebFlux:** controller returns `Mono`, `Flux`, or another reactive type; use `WebTestClient` to send requests and verify results.
- **Servlet MVC async:** controller returns `Callable`, `DeferredResult`, or `WebAsyncTask`; with MockMvc, the test initiates the async request, waits for the result, and performs a second dispatch using `asyncDispatch`.

Spring MVC also supports reactive return types in certain cases. Identify the application stack and how the endpoint actually executes to choose the right test client.

After this lesson, you will be able to:

- Distinguish reactive WebFlux from async requests in Spring MVC.
- Use `WebTestClient` to test and document reactive endpoints.
- Use MockMvc with `asyncDispatch` for MVC async endpoints.
- Control timeouts, completion, and test data to avoid flaky tests.
- Document finite responses and understand limitations with streaming responses.

## 1. Distinguishing Reactive and Servlet MVC Async

| Aspect | Spring WebFlux | Spring MVC async |
| --- | --- | --- |
| Typical runtime | Reactive stack, commonly based on Reactor Netty | Servlet container |
| Common return types | Mono, Flux | Callable, DeferredResult, WebAsyncTask; also supports reactive types |
| Test client | WebTestClient | MockMvc or appropriate integrated client |
| How response is awaited | Consume publisher via exchange | Async dispatch after request enters async mode |
| Key consideration | Publisher must complete or be bounded | Must wait for async result before dispatching |

`WebTestClient` can test WebFlux directly or connect to a running server. It can also be configured to test Spring MVC. The test client's name alone does not determine the application stack.

## 2. Testing WebFlux Endpoints with WebTestClient

Suppose a controller returns a product using `Mono`:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    @GetMapping("/{id}")
    Mono<ProductResponse> getById(@PathVariable long id) {
        return this.productService.findById(id);
    }
}
```

WebTestClient test:

```java
this.webTestClient.get()
    .uri("/api/products/{id}", 501)
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(501)
    .jsonPath("$.name").isEqualTo("Keyboard")
    .consumeWith(document("products-get",
        responseFields(
            fieldWithPath("id").description("Product ID."),
            fieldWithPath("name").description("Product name.")
        )));
```

`WebTestClient` performs the exchange, awaits the response body according to the chosen test style, runs expectations, and then forwards the result to REST Docs via `consumeWith(document(...))`.

### 2.1. Checking the Response Body as an Object

You can deserialize the body into a DTO:

```java
this.webTestClient.get()
    .uri("/api/products/{id}", 501)
    .exchange()
    .expectStatus().isOk()
    .expectBody(ProductResponse.class)
    .value(product -> {
        assertThat(product.id()).isEqualTo(501);
        assertThat(product.name()).isEqualTo("Keyboard");
    });
```

When you need to document the same exchange, use `consumeWith(document(...))` on the body spec instead of making a second request solely to generate snippets. Do not send two separate requests if the endpoint has side effects or data changes between calls.

### 2.2. Testing with Delayed Publishers

A service might return a `Mono` that completes after a short delay:

```java
Mono<ProductResponse> findById(long id) {
    return Mono.delay(Duration.ofMillis(20))
            .map(ignored -> repository.findResponse(id));
}
```

`WebTestClient` waits for the exchange to complete within a configured timeout. Set a finite timeout large enough for CI:

```java
this.webTestClient = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .responseTimeout(Duration.ofSeconds(3))
        .build();
```

Do not use `Thread.sleep` to guess when a publisher completes. Await completion through the reactive test client or Reactor `StepVerifier` for publisher-layer tests.

## 3. Testing Finite Flux Streams

An endpoint can return a list via `Flux`:

```java
@GetMapping
Flux<ProductResponse> list() {
    return this.productService.findAll();
}
```

If the publisher completes after a finite number of items, you can assert a JSON array:

```java
this.webTestClient.get()
    .uri("/api/products")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .json("""
            [
              {"id": 501, "name": "Keyboard"},
              {"id": 502, "name": "Mouse"}
            ]
            """)
    .consumeWith(document("products-list",
        responseFields(
            fieldWithPath("[].id").description("Product ID."),
            fieldWithPath("[].name").description("Product name.")
        )));
```

This example shows a response serialized as a finite JSON array. The JSON structure and field paths must match the application's real output and the REST Docs version in use.

For list data, fixtures should be fixed, and ordering should only be asserted if the API guarantees ordering. If the API does not guarantee order, verify contents as a set of values or sort data deterministically in the test setup.

## 4. Testing Continuous Streams and SSE

Not every `Flux` completes. Example of server-sent events:

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<ServerSentEvent<Notification>> events() {
    return notificationService.stream();
}
```

An infinite stream cannot be processed like a complete JSON array. If a test waits for the body to complete, it can time out because the publisher never terminates.

Options:

- Use a finite publisher in the test fixture, such as emitting two events and then completing.
- Use `take(n)` in the test source or configure a mock service to bound the number of events.
- Verify media type, event format, and the first few events using an appropriate streaming mechanism.
- Document the event format, event names, data schema, and reconnect policy with intentional examples.

Do not use an actual infinite stream as the snippet source in documentation tests. A test needs a deterministic completion point to finish assertions and write artifacts.

Example finite publisher:

```java
when(notificationService.stream())
    .thenReturn(Flux.just(
            new Notification("created", 501),
            new Notification("updated", 501)
    ));
```

The publisher completes after two events, allowing the test to verify the data and finish. How SSE bodies are asserted/documented depends on the adapter and how `WebTestClient` consumes streaming responses; do not apply JSON payload snippets to an event stream when the actual representation is `text/event-stream`.

## 5. Spring MVC Async with MockMvc

Spring MVC can return asynchronous results via `Callable`:

```java
@GetMapping("/report")
Callable<ReportResponse> report() {
    return reportService::generate;
}
```

MockMvc handles this request style in two phases:

1. Perform the initial request and verify the async-started state.
2. Wait for the async result, then perform a second dispatch to assert the final response.

Example:

```java
MvcResult mvcResult = this.mockMvc.perform(get("/api/report"))
    .andExpect(request().asyncStarted())
    .andReturn();

mvcResult.getAsyncResult(3_000);

this.mockMvc.perform(asyncDispatch(mvcResult))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.status").value("READY"))
    .andDo(document("report-get",
        responseFields(
            fieldWithPath("status").description("Report status."),
            fieldWithPath("downloadUrl").description("Report download URL.")
        )));
```

`asyncDispatch(mvcResult)` is the critical step: it dispatches the completed async result through the MVC pipeline so assertions and REST Docs see the final response.

Do not call `document(...)` right after the initial request if the response has not completed yet. At that point, the exchange may not yet have the final status/body that documentation needs to record.

### 5.1. Setting Timeouts for Async Requests

MockMvc supports configuring async request timeouts. Tests should use an appropriate bound and verify timeout behavior when that is part of the contract:

```java
MvcResult mvcResult = this.mockMvc.perform(get("/api/report"))
    .andExpect(request().asyncStarted())
    .andReturn();

mvcResult.getAsyncResult(3_000);

this.mockMvc.perform(asyncDispatch(mvcResult))
    .andExpect(status().isOk())
    .andDo(document("report-get"));
```

`getAsyncResult` waits up to the specified milliseconds and throws an error if no result arrives within that window. Do not raise the timeout excessively to hide a deadlock or a non-completing publisher.

### 5.2. DeferredResult and WebAsyncTask

Controllers using `DeferredResult` or `WebAsyncTask` can also be tested with the async dispatch pattern when the request is processed asynchronously by Spring MVC:

```java
MvcResult result = this.mockMvc.perform(get("/api/summary"))
    .andExpect(request().asyncStarted())
    .andReturn();

this.mockMvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andDo(document("summary-get"));
```

With `DeferredResult`, the test must trigger the completion callback or use a controlled mock service that completes. Otherwise, the request stays pending until timeout.

## 6. Distinguishing Timeouts from Error Responses

An asynchronous task timeout does not necessarily map to one fixed status across every application. The outcome depends on the configured timeout, exception handlers, and how the framework translates errors into HTTP responses.

If timeout behavior is part of the API contract to publish:

- Fix the timeout value in the test.
- Cause the test task not to complete within that chosen limit.
- Assert the status and error body according to actual exception handling.
- Use a dedicated operation ID, such as `report-get-timeout`.
- Do not let timeout tests depend on machine load or random sleeps.

If a timeout is just a test-infrastructure issue, fix why the publisher/task failed to complete rather than documenting it as a valid response.

## 7. Combining Assertions and REST Docs

Whether an endpoint is reactive or async, the principle remains:

1. Send the request using the appropriate client.
2. Wait for the response to complete according to its lifecycle.
3. Assert status, headers, and body.
4. Pass the completed exchange to REST Docs.
5. Use descriptors to document the request/response.

WebTestClient example:

```java
this.webTestClient.get()
    .uri("/api/products/{id}", 501)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(501)
    .consumeWith(document("products-get",
        responseFields(
            fieldWithPath("id").description("Product ID."),
            fieldWithPath("name").description("Product name.")
        )));
```

MockMvc async example:

```java
MvcResult result = this.mockMvc.perform(get("/api/report"))
    .andExpect(request().asyncStarted())
    .andReturn();

this.mockMvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.status").value("READY"))
    .andDo(document("report-get"));
```

Do not generate snippets from an initial request without the final response, and do not treat an assertion that only checks `asyncStarted` as proof that the endpoint completed successfully.

## 8. Testing Errors in Reactive/Async Endpoints

Reactive publishers can emit errors via `Mono.error` or `Flux.error`. Spring WebFlux processes errors through the corresponding exception handler.

Example:

```java
when(productService.findById(9999))
    .thenReturn(Mono.error(new ProductNotFoundException(9999)));

this.webTestClient.get()
    .uri("/api/products/{id}", 9999)
    .exchange()
    .expectStatus().isNotFound()
    .expectBody()
    .jsonPath("$.code").isEqualTo("PRODUCT_NOT_FOUND")
    .consumeWith(document("products-get-not-found",
        responseFields(
            fieldWithPath("code").description("Error code."),
            fieldWithPath("message").description("Error message.")
        )));
```

This is an illustrative example; exception types and error responses must match the application. With MVC async, exceptions from `Callable`/`DeferredResult` must also be checked after async dispatch and through actual exception handling.

## 9. Deterministic and Independent Tests

Asynchrony increases the risk of flaky tests if tests depend on timing or execution order.

Do:

- Use finite publishers in documentation tests.
- Use controllable schedulers/test executors when needed.
- Avoid `Thread.sleep` to wait for task completion.
- Set finite, reasonable timeouts for CI environments.
- Use fixed fixtures and mock dependencies at the right boundary.
- Avoid sharing the same operation ID between success and timeout/error responses.
- Reset state between tests and avoid depending on execution order.
- Only include snippets after the final response has been asserted.

With Reactor, `StepVerifier` is ideal for testing publishers at the service layer. However, `StepVerifier` does not replace HTTP-level documentation tests: REST Docs requires an actual HTTP exchange through a test client/REST Docs integration.

## 10. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| MockMvc test only sees async started | `asyncDispatch` was not called | Wait for result, then perform second dispatch |
| `asyncDispatch` times out | `Callable`/`DeferredResult` never completes or timeout is too short | Check executor/callback and timeout |
| `WebTestClient` test hangs | `Mono`/`Flux` never completes or response is an infinite stream | Use finite fixtures or bounded streaming checks |
| Empty snippet body | Documented before response completed or endpoint returns no body | Place `document` after expectations/async dispatch |
| Flaky tests on CI | Using sleep, schedulers, or machine-dependent timing | Synchronize on completion with reasonable timeouts |
| SSE parsed as JSON | `Content-Type`/representation is not `application/json` | Assert `text/event-stream` and verify events per protocol |
| Timeout assumed to be status 504 | Framework/application not configured to return 504 | Assert actual response produced by exception handling |
| Reactive test passes yet production endpoint fails | Only tested publisher/service without HTTP layer | Add `WebTestClient` documentation tests |
| Operation snippets overwritten | Success and error share an operation ID | Separate operation IDs |

## 11. Hands-On Exercise

1. Create a WebFlux endpoint `GET /api/products/{id}` returning `Mono<ProductResponse>`.
2. Write a `WebTestClient` test asserting status, `Content-Type`, and JSON body; create operation `products-get`.
3. Create a list endpoint returning a finite `Flux<ProductResponse>`; assert the JSON array and document fields.
4. Create a reactive error test with `Mono.error`; assert 404 and document the error body with a separate operation ID.
5. Create a Spring MVC endpoint returning `Callable<ReportResponse>`.
6. Write a MockMvc test confirming async started, waiting for the async result, and using `asyncDispatch` before documenting.
7. Create a controlled timeout test if timeouts are part of the contract; assert the actual status/error response.
8. Try a finite SSE stream; choose an appropriate representation and event assertion instead of using a JSON array snippet.

**Self-Assessment Questions**

1. How does reactive WebFlux differ from Spring MVC async?
2. Why does MockMvc require `asyncDispatch` for async requests?
3. How does `WebTestClient` wait for `Mono`/`Flux` completion in standard response tests?
4. Why is an infinite publisher unsuitable for generating a complete body snippet?
5. When is `StepVerifier` useful, and why does it not replace HTTP documentation tests?
6. How does a test infrastructure timeout differ from an API-documented timeout response?
7. Why do reactive success and error cases need separate operation IDs?
8. How do you keep async documentation tests stable in CI?

## Official References

- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing WebFlux and HTTP exchanges.
- [Spring Framework — WebFlux Testing](https://docs.spring.io/spring-framework/reference/web/webflux-test.html): testing controllers and the reactive web layer.
- [Spring Framework — MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): testing async requests and async dispatch.
- [Spring REST Docs — WebTestClient](https://docs.spring.io/spring-restdocs/reference/getting-started/documentation-snippets.html): integrating REST Docs with WebTestClient.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` and testing publishers.
- [Spring Framework — MVC Async](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): `Callable`, `DeferredResult`, and asynchronous request processing.

**Practical Takeaway:** With WebFlux, use `WebTestClient` to await and verify the reactive exchange; with Spring MVC async, await the async result and call `asyncDispatch` before documenting. Use finite publishers, deterministic timeouts, and distinct operation IDs for differing response branches. For continuous streams such as SSE, document the protocol and sample events appropriately rather than waiting for an infinite body to finish like regular JSON.
