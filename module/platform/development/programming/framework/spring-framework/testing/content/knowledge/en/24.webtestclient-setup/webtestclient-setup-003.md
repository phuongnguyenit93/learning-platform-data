# `bindToRouterFunction` for Functional Endpoints

Spring WebFlux supports building HTTP endpoints in two main styles: annotated controllers with `@RestController`, or functional endpoints with `RouterFunction` and `HandlerFunction`. When an application uses functional endpoints, `WebTestClient.bindToRouterFunction(...)` allows testing the router directly using simulated in-memory requests and responses.

This approach is suitable when you want to verify routes, HTTP methods, request predicates, handlers, body codecs, and responses without starting a real HTTP server. Tests use an API close to an HTTP client: build a request, call `exchange()`, and assert status, headers, and body.

## 1. Functional Endpoints Consist of Routers and Handlers

In WebFlux's functional model, a `RouterFunction` decides which request is routed to which handler. A `HandlerFunction` receives a `ServerRequest` and returns a `Mono<ServerResponse>`.

```text
WebTestClient request
        |
        v
RouterFunction<ServerResponse>
        |
        | request predicate matches?
        v
HandlerFunction<ServerResponse>
        |
        | process ServerRequest
        v
Mono<ServerResponse>
        |
        v
WebTestClient assertions
```

A router can be declared directly using `RouterFunctions.route(...)` or via a builder to group multiple routes. A handler can be a lambda or a method reference to a dedicated request-handling class.

Example greeting endpoint:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

class GreetingHandler {

    Mono<ServerResponse> greet(ServerRequest request) {
        String name = request.pathVariable("name");
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello, " + name);
    }
}

@Configuration(proxyBeanMethods = false)
class GreetingRoutes {

    @Bean
    GreetingHandler greetingHandler() {
        return new GreetingHandler();
    }

    @Bean
    RouterFunction<ServerResponse> greetingRouter(GreetingHandler handler) {
        return route(GET("/greetings/{name}"), handler::greet);
    }
}
```

`GET("/greetings/{name}")` is a request predicate. When the method and path match, the router forwards the `ServerRequest` to `handler.greet(...)`. The handler reads the path variable, builds a response, and returns a reactive publisher `Mono<ServerResponse>`.

In a complete application, `GreetingHandler` also needs to be registered as a bean, for example via `@Component` or a `@Bean` method in configuration. The example above focuses on the relationship between the router and the handler.

## 2. What Test Environment Does `bindToRouterFunction` Create?

`WebTestClient.bindToRouterFunction(routerFunction)` accepts a `RouterFunction<?>` and builds a test client attached directly to that router:

```java
WebTestClient client = WebTestClient
        .bindToRouterFunction(greetingRouter)
        .build();
```

When `exchange()` is called, the client routes the request through the in-memory WebFlux processing infrastructure, the router selects the handler, the handler produces a response, and the client collects the response for assertions. No TCP port needs to be opened and Netty/Tomcat does not need to be started.

This keeps the test focused on the functional endpoint. The passed-in router is the primary input of the test; the test does not need to spin up the full application context just to check a route.

`bindToRouterFunction` differs from other `WebTestClient` binding modes:

| Binding Mode | Components Tested | When Appropriate |
|---|---|---|
| `bindToRouterFunction(router)` | The provided router function and the handlers it routes to | Testing an isolated group of functional endpoints |
| `bindToApplicationContext(context)` | The configured WebFlux application context | Needing to test multiple beans, routers, `WebFilter`, codecs, and configurations loaded together in the context |
| `bindToServer()` | A running server over real HTTP | Needing to test networking, server connector, or deployment integration |

With `bindToRouterFunction`, components provided through the application context are not automatically included merely because they exist in the application. If the test needs a security filter chain, `WebFilter`, custom codecs, or application-wide configuration, consider binding to the application context or explicitly setting up the required infrastructure for the test.

## 3. Testing a Basic Route

You can create the router directly in the test to keep the example small and avoid starting a Spring context:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.test.web.reactive.server.WebTestClient.bindToRouterFunction;
import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;
import static org.springframework.web.reactive.function.server.ServerResponse.ok;
import static org.springframework.http.MediaType.TEXT_PLAIN;

class GreetingRouterTests {

    private final RouterFunction<ServerResponse> router =
            route(GET("/greetings/{name}"), request ->
                    ok()
                            .contentType(TEXT_PLAIN)
                            .bodyValue("Hello, " + request.pathVariable("name")));

    private final WebTestClient client = bindToRouterFunction(router).build();

    @Test
    void returnsGreetingForPathVariable() {
        client.get()
                .uri("/greetings/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(TEXT_PLAIN)
                .expectBody(String.class)
                .isEqualTo("Hello, Ada");
    }
}
```

The steps in the test correspond to an HTTP exchange:

1. `client.get()` creates a GET request.
2. `.uri(...)` sets the URI and path.
3. `.exchange()` sends the request through the router.
4. `expectStatus()` verifies the status.
5. `expectHeader()` verifies response headers.
6. `expectBody(String.class)` decodes the response body into the expected type.

This test proves that the router accepts the path, the handler reads the path variable accurately, and the response contains the body and content type required by the contract.

## 4. Grouping Multiple Routes with RouterFunctions Builder

Applications often have multiple endpoints belonging to the same group. You can use the builder to group routes and reuse handlers:

```java
RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
    return RouterFunctions.route()
            .GET("/orders/{id}", handler::findById)
            .POST("/orders", handler::create)
            .GET("/orders", handler::search)
            .build();
}
```

Or group routes under a path prefix:

```java
RouterFunction<ServerResponse> apiRoutes(OrderHandler orderHandler,
                                          CustomerHandler customerHandler) {
    return RouterFunctions.route()
            .path("/api", builder -> builder
                    .GET("/orders/{id}", orderHandler::findById)
                    .POST("/orders", orderHandler::create)
                    .GET("/customers/{id}", customerHandler::findById))
            .build();
}
```

Tests should bind the actual grouped router to verify that routes are genuinely wired into the routing tree:

```java
WebTestClient client = WebTestClient
        .bindToRouterFunction(apiRoutes(orderHandler, customerHandler))
        .build();
```

If a test only builds a simplified router different from the production router, it may miss configuration errors when composing routes, prefixes, or filters. For critical routes, use the same `RouterFunction` bean registered by the application or import the corresponding router configuration.

## 5. Testing Request Body and JSON Response

Functional handlers read the body through `ServerRequest`. Example of creating an order:

```java
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

record CreateOrderRequest(
        @jakarta.validation.constraints.NotBlank String productCode,
        @jakarta.validation.constraints.Min(1) int quantity) {
}

record OrderReceipt(String orderId, String productCode, int quantity) {
}

class OrderHandler {

    Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateOrderRequest.class)
                .flatMap(body -> {
                    OrderReceipt receipt = new OrderReceipt(
                            "ORD-100", body.productCode(), body.quantity());

                    return ServerResponse.accepted()
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(receipt);
                });
    }
}
```

Test sending a JSON body and verifying the response:

```java
@Test
void createsOrderFromJsonBody() {
    client.post()
            .uri("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("BOOK-01", 2))
            .exchange()
            .expectStatus().isAccepted()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.orderId").isEqualTo("ORD-100")
            .jsonPath("$.productCode").isEqualTo("BOOK-01")
            .jsonPath("$.quantity").isEqualTo(2);
}
```

`bodyValue(...)` relies on the client's codec to serialize the object into the request body. On the handler side, `bodyToMono(...)` uses WebFlux's codec to deserialize the body into a DTO. Such a test checks both conversion directions in the functional endpoint flow.

If you want to send raw JSON to test a malformed body case, you can use `.bodyValue("{invalid-json")` along with `contentType(APPLICATION_JSON)`. In that case, the handler typically receives a decode error as a reactive error; the test should verify how the router or error handler maps that error.

## 6. Testing Query Parameters, Path Variables, and Headers

`ServerRequest` provides APIs to read request data:

- `pathVariable("id")` reads a variable declared in the route path.
- `queryParam("q")` returns an `Optional<String>` for a query parameter.
- `headers()` accesses the headers that were sent.
- `bodyToMono(...)` or `bodyToFlux(...)` reads the request body as a reactive type.

Example search handler:

```java
class SearchHandler {

    Mono<ServerResponse> search(ServerRequest request) {
        String keyword = request.queryParam("q").orElse("");
        String language = request.headers()
                .firstHeader("Accept-Language");

        SearchResult result = new SearchResult(keyword, language);
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(result);
    }
}

record SearchResult(String keyword, String language) {
}
```

Test constructing query parameters and headers:

```java
client.get()
        .uri(uriBuilder -> uriBuilder
                .path("/search")
                .queryParam("q", "spring webflux")
                .build())
        .header("Accept-Language", "vi-VN")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.keyword").isEqualTo("spring webflux")
        .jsonPath("$.language").isEqualTo("vi-VN");
```

When query parameters contain special characters, use `uriBuilder` or a URI template to encode values properly. Avoid manually concatenating URL strings because spaces, `&`, `?`, and Unicode can make the request differ from what was intended.

## 7. Testing Unmatched Routes and Request Predicates

The router only invokes a handler when the request predicate matches. Predicates can inspect HTTP method, path, query parameters, headers, or content type.

Example route accepting only GET:

```java
RouterFunction<ServerResponse> router = route(
        GET("/status"),
        request -> ServerResponse.ok().bodyValue("ready"));
```

Test matching route:

```java
client.get()
        .uri("/status")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("ready");
```

Test non-existent path:

```java
client.get()
        .uri("/missing")
        .exchange()
        .expectStatus().isNotFound();
```

When a request matches no router, no functional handler is called and WebFlux returns a not-found result according to its default handling or the application's configuration. If the application defines a custom not-found handler, the test should verify that handler's response.

For predicates checking headers or query parameters, write at least one matching test and one non-matching test. If a router has multiple routes sharing a prefix, tests should also verify that requests are dispatched to the right handler when multiple predicates might match.

## 8. Attaching Filters to RouterFunction and Testing Their Effect

Functional endpoints can apply `HandlerFilterFunction` to execute logic before or after a handler. Filters can be used for logging, timing, checking request metadata, or transforming errors within the scope of the router.

```java
import org.springframework.web.reactive.function.server.HandlerFilterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;

HandlerFilterFunction<ServerResponse, ServerResponse> errorFilter =
        (request, next) -> next.handle(request)
                .onErrorResume(OrderNotFoundException.class, ex ->
                        ServerResponse.status(HttpStatus.NOT_FOUND)
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError("ORDER_NOT_FOUND")));

record ApiError(String code) {
}

class OrderNotFoundException extends RuntimeException {
}

class FailingOrderHandler {
    Mono<ServerResponse> findById(ServerRequest request) {
        return Mono.error(new OrderNotFoundException());
    }
}
```

Apply the filter to the router:

```java
RouterFunction<ServerResponse> router = route(
        GET("/orders/{id}"),
        new FailingOrderHandler()::findById)
        .filter(errorFilter);
```

The test needs to trigger the exact error and verify that the filter converted it into the public response:

```java
client.get()
        .uri("/orders/404")
        .exchange()
        .expectStatus().isNotFound()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND");
```

This example assumes `orderHandler.findById(...)` returns an error `Mono` with `OrderNotFoundException` when an order is not found. A filter only handles errors within the handler flow it wraps. A WebFlux-level `WebExceptionHandler` has a broader scope and handles errors at the web handler layer; choose the right mechanism for the scope you need to test.

`HandlerFilterFunction` is not the same as `WebFilter`. A handler filter attaches to a `RouterFunction` and the handlers it selects. A `WebFilter` belongs to the WebFlux application filter chain and is typically tested with an application context or a `WebTestClient` configured with a context.

## 9. Testing Validation in Functional Endpoints

Functional endpoints do not use Spring-bound method parameters like annotated controllers. A handler receives `ServerRequest` and explicitly calls `bodyToMono(...)`; therefore, you should not assume that `@Valid` on a record or annotations on a handler method will run automatically like `@RequestBody` in a `@RestController`.

An explicit approach is to inject a Jakarta `Validator` and invoke it after decoding the DTO:

```java
import jakarta.validation.Validator;
import java.util.Set;

class CreateOrderHandler {

    private final Validator validator;

    CreateOrderHandler(Validator validator) {
        this.validator = validator;
    }

    Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateOrderRequest.class)
                .flatMap(body -> {
                    Set<jakarta.validation.ConstraintViolation<CreateOrderRequest>> violations =
                            validator.validate(body);

                    if (!violations.isEmpty()) {
                        return ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError("VALIDATION_FAILED"));
                    }

                    return ServerResponse.accepted().build();
                });
    }
}
```

The test sends a DTO that violates a constraint and verifies the error response:

```java
client.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateOrderRequest("BOOK-01", 0))
        .exchange()
        .expectStatus().isBadRequest()
        .expectBody()
        .jsonPath("$.code").isEqualTo("VALIDATION_FAILED");
```

In this example, the DTO, `ApiError`, handler, and validator must be provided to the test with the appropriate configuration. You can use a real validator to check constraints or mock other business dependencies. If you want to test validation as an independent component, test the validator in a unit test and use WebTestClient to verify the mapping from violations to the response.

## 10. Testing Empty Bodies, Decode Errors, and Error Responses

A handler reading the body via `bodyToMono(...)` can encounter decode errors when the body is invalid. How the error is represented depends on the codec and where the application catches the error.

For example, if the handler converts a decode error into a `400` response using `onErrorResume`, the test can send malformed JSON:

```java
client.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{ invalid json")
        .exchange()
        .expectStatus().isBadRequest();
```

This test is only meaningful if the router or handler has defined how decode exceptions are mapped. Without error mapping, the error may reach the default `WebExceptionHandler` and produce a different response. Check the status, content type, and body against the actual configuration.

For optional request bodies, a handler might handle `Mono.empty()` or use `switchIfEmpty(...)`. Distinguish between a body with no data and a JSON body containing `null`; these two cases can pass through the codec differently.

## 11. Testing Reactive and Streaming Responses

`ServerResponse.bodyValue(...)` works for a single object or value. When a handler returns a `Flux<T>`, the response can emit multiple elements as a stream or be encoded into a collection depending on how it is configured.

For finite responses, `expectBodyList(...)` helps verify the entire collected list:

```java
client.get()
        .uri("/orders")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(OrderView.class)
        .hasSize(2);
```

If you need to inspect order or individual elements, you can extract the body into a `List<OrderView>` and run assertions on the list.

For streams where reactive signals need to be verified, use `returnResult(...)` and Reactor Test `StepVerifier`:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

record EventView(String type) {
}

Flux<EventView> responseBody = client.get()
        .uri("/events")
        .exchange()
        .expectStatus().isOk()
        .returnResult(EventView.class)
        .getResponseBody();

StepVerifier.create(responseBody)
        .expectNextMatches(event -> event.type().equals("CREATED"))
        .expectNextMatches(event -> event.type().equals("UPDATED"))
        .verifyComplete();
```

For infinite streams such as server-sent events, do not call `verifyComplete()` because the stream is designed not to terminate. Verify the required number of elements or conditions and then call `thenCancel()` to cancel the subscription. Streaming tests need attention to timeouts to avoid waiting forever when the handler does not emit data.

## 12. When Is `bindToRouterFunction` Not Enough?

`bindToRouterFunction` is suitable for verifying the passed-in router and handlers within their scope. However, it does not by itself prove that the entire application is configured properly.

| Testing Requirement | Appropriate Binding Mode |
|---|---|
| Predicates, paths, handlers, and responses of a RouterFunction | `bindToRouterFunction(router)` |
| Multiple routers registered via application configuration | `bindToApplicationContext(context)` |
| `WebFilter`, security configuration, or codec beans loaded in context | Usually `bindToApplicationContext(context)` |
| Real HTTP server, connector, TLS, network, and ports | `bindToServer()` |
| Business handler behavior with mock dependencies | `bindToRouterFunction(...)` with a handler created by a test fixture |
| Full application route mapping after composition | Bind the final router bean or application context |

If custom codecs or filters are registered in the application context, an isolated router test can bypass them. If that is what needs to be verified, use a context-based test. For requirements involving networking, server connectors, or TLS, a real server and `bindToServer()` are needed.

## 13. Organizing Tests to Keep Routers and Handlers Maintainable

A commonly readable structure splits into three parts:

```text
orders/
  OrderHandler.java       handles ServerRequest and builds ServerResponse
  OrderRouter.java        declares RouterFunction and request predicates
  OrderHandlerTests.java  tests the handler via WebTestClient
```

The handler focuses on reading the request, invoking business logic, and building the response. The router focuses on paths, methods, predicates, and filters. Tests bind the production router or a router fixture built from the test handler.

For example, a test fixture can construct a router directly from the handler:

```java
OrderHandler handler = new OrderHandler();

RouterFunction<ServerResponse> router = RouterFunctions.route()
        .POST("/orders", handler::create)
        .build();

WebTestClient client = WebTestClient.bindToRouterFunction(router).build();
```

If the test manually recreates paths and predicates instead of using the production router, it only proves that the fixture works. When route mapping matters, bind the real router bean or import the configuration that builds the router.

## 14. Common Mistakes When Using `bindToRouterFunction`

| Practice | Issue | Better Approach |
|---|---|---|
| Using `bindToRouterFunction` while expecting every bean in the application context to appear | Router binding does not automatically load the entire application context | Bind to the application context when global configuration is needed |
| Testing a router fixture different from the production router | May miss route composition or prefix mistakes | Bind the final router bean or import the route configuration |
| Checking only the status | Does not verify the body and headers against the contract | Verify status, content type, and response fields |
| Calling `.exchange()` and assuming the handler already returned synchronously | A reactive handler may not have completed initially | Use body assertions or `StepVerifier` to consume the publisher |
| Using `verifyComplete()` with an infinite stream | The test will wait until it times out | Verify a set number of elements and then `thenCancel()` |
| Expecting `@Valid` to run automatically on a DTO in a handler function | Functional handlers read the body themselves and lack annotated controller argument resolvers | Call `Validator` or use an explicit validation mechanism |
| Expecting `@RestControllerAdvice` to handle all errors from RouterFunction | Functional handlers and annotated controllers have different processing paths | Use filters or a `WebExceptionHandler` appropriate for the router |
| Using a router test to conclude that server/TLS works properly | No real network connector is involved | Add tests against a running server |

## 15. Workflow for Writing a Functional Endpoint Test

1. Identify the actual `RouterFunction` to test and the handlers it references.
2. Choose the scope: standalone router, full application context, or real HTTP server.
3. Build `WebTestClient.bindToRouterFunction(router).build()` when only the router and handlers are needed.
4. Send requests with the method, URI, headers, query parameters, and body matching a real client.
5. Call `exchange()` and assert the status, response headers, and body.
6. For route predicates, test both matching and non-matching cases.
7. For handler filters or error mapping, trigger the exact scenario to observe the filter's effect.
8. For reactive streams, use `expectBodyList`, `returnResult`, or `StepVerifier` depending on the response type.
9. Switch to context/server binding when the test requires components absent from an isolated router.

## 16. References

- [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): how to set up the client and send test requests.
- [Spring Framework Reference — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): RouterFunction, HandlerFunction, ServerRequest, and ServerResponse.
- [Spring Framework Reference — RouterFunction](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html#webflux-fn): how to declare and compose functional routes.
- [Spring Framework Javadoc — `WebTestClient`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html): binding methods and request/response assertion APIs.
- [Reactor Test — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): testing signals of reactive publishers.

`bindToRouterFunction` creates a clean testing boundary for functional endpoints: requests pass through the selected router and handlers, and responses are collected for verification with `WebTestClient`. Bind the production router when protecting real mappings, verify body and headers against the contract, and use context/server binding when requirements go beyond the scope of a single RouterFunction.
