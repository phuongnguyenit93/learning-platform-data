# `bindToApplicationContext` with WebFlux Configuration

`WebTestClient.bindToApplicationContext(...)` creates an HTTP test client attached directly to a Spring `ApplicationContext`. For WebFlux applications, this allows sending simulated requests through the reactive web infrastructure configured by the context: `DispatcherHandler`, handler mappings, controllers or functional routes, `WebFilter`s, exception handlers, and data converters.

This is a suitable option when you want to test multiple WebFlux components working together in a context without starting Netty or a real HTTP server. Unlike binding only to a single controller, `bindToApplicationContext` uses the web configuration registered in the context, so tests can also verify shared application components.

## 1. WebTestClient and Binding Modes

`WebTestClient` has an API very similar to `WebClient`: specify the method, URI, headers, and body of a request, call `exchange()`, and assert the status, response headers, and body. The difference is that it adds assertions designed for testing.

There are several ways to create a `WebTestClient`, each fitting a different scope:

| Binding Mode | Scope Built | When to Use |
|---|---|---|
| `bindToController(...)` | Specified controller(s) and minimal required infrastructure | Testing a single controller or a small group of controllers in isolation. |
| `bindToRouterFunction(...)` | Specified functional endpoint | Testing a `RouterFunction` and its corresponding handlers. |
| `bindToApplicationContext(context)` | WebFlux infrastructure and web beans discovered in the Spring context | Testing overall WebFlux configuration, filters, advice, codecs, and multiple endpoints. |
| `bindToServer()` | Connection to a running HTTP server | Testing requests through a real server, connector, and HTTP transport. |

`bindToApplicationContext` sits between component tests and real-server tests. It retains broader Spring WebFlux configuration than binding directly to a controller, while still running in an in-memory mock environment.

## 2. The Context Must Have WebFlux Configuration

`bindToApplicationContext` accepts a refreshed Spring `ApplicationContext`. The context must provide a `WebHandler` and the required WebFlux beans. With plain Java configuration, `@EnableWebFlux` registers the Spring WebFlux infrastructure, including `DispatcherHandler` along with mapping and adapter components.

Minimal configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
class WebFluxTestConfiguration {

    @Bean
    GreetingController greetingController() {
        return new GreetingController();
    }
}
```

Controller returning a reactive type:

```java
import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
class GreetingController {

    @GetMapping("/{name}")
    Mono<Greeting> greet(@PathVariable String name) {
        return Mono.just(new Greeting("Hello, " + name));
    }
}

record Greeting(String message) {
}
```

`@EnableWebFlux` creates the foundational WebFlux configuration; the controller bean is discovered and registered in the same context. Once the context is refreshed, `WebTestClient` can build a mock server handler from that context.

## 3. Creating a Client with `bindToApplicationContext`

With a plain Java context, you can create the context in the test and bind the client directly:

```java
import static org.springframework.test.web.reactive.server.WebTestClient.bindToApplicationContext;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

class GreetingWebFluxTest {

    @Test
    void returnsGreetingFromTheConfiguredWebFluxContext() {
        try (var context = new AnnotationConfigApplicationContext(
                WebFluxTestConfiguration.class)) {

            WebTestClient client = bindToApplicationContext(context)
                    .configureClient()
                    .baseUrl("http://localhost")
                    .build();

            client.get()
                    .uri("/api/greetings/{name}", "Lan")
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                    .expectBody(Greeting.class)
                    .isEqualTo(new Greeting("Hello, Lan"));
        }
    }
}
```

`bindToApplicationContext(context)` reads the web configuration from the context and builds an `HttpHandler` for the mock server. `configureClient()` switches to client-side configuration, such as base URL, default headers, or client-side filters. `build()` finalizes the `WebTestClient`.

In the example, `AnnotationConfigApplicationContext` automatically refreshes after receiving the configuration class. If you construct a context using the no-arg constructor and register beans manually, you must call `refresh()` before binding the client. Once the context is closed, the client no longer has a web environment to handle requests.

Common imports for the test above:

```java
import org.springframework.http.MediaType;
```

## 4. Using the Spring Boot Test Context

In a Spring Boot WebFlux application, the context is typically already configured by `@SpringBootApplication` and auto-configurations. You can obtain that context and create the client:

```java
import static org.springframework.test.web.reactive.server.WebTestClient.bindToApplicationContext;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ApplicationWebFluxContextTest {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = bindToApplicationContext(applicationContext)
                .configureClient()
                .baseUrl("http://localhost")
                .build();
    }

    @Test
    void returnsApplicationResponse() {
        client.get()
                .uri("/api/health")
                .exchange()
                .expectStatus().isOk();
    }
}
```

`webEnvironment = MOCK` does not start an embedded HTTP server. The test sends requests through a mock WebFlux handler built from the context. This is suitable for loading all application beans, configurations, filters, and exception handlers while avoiding the overhead of opening a network port.

Spring Boot can also auto-configure a `WebTestClient` to inject into tests when using `@AutoConfigureWebTestClient` with an appropriate web environment. If you use the auto-configured client, you do not need to call `bindToApplicationContext` again. When the goal is to clearly understand context binding or to apply custom client configuration, manual creation as in the example above makes the configuration source explicit.

## 5. WebFlux Components Covered by the Test

Unlike `bindToController`, binding to an application context lets requests pass through the web components provided by the context. Typical components present include:

- `DispatcherHandler` and `HandlerMapping`s that select the matching endpoint.
- `HandlerAdapter`s that invoke annotated controllers or functional handlers.
- `WebFilter`s that apply cross-cutting logic before and after handlers.
- `WebExceptionHandler`s that handle exceptions thrown in the WebFlux pipeline.
- `ServerCodecConfigurer` and `HttpMessageReader`/`HttpMessageWriter` that handle request/response bodies.
- `WebSessionManager`, `LocaleContextResolver`, and other web infrastructure components if configured.

These beans must actually exist in the context. If a test registers only a controller without WebFlux configuration, `WebTestClient` cannot infer how the rest of the application is supposed to run.

### Testing `WebFilter`

Example filter adding a header to the response:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.WebFilter;

@Configuration
class TraceFilterConfiguration {

    @Bean
    WebFilter traceHeaderFilter() {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders()
                    .add("X-Trace-Source", "webflux-filter");
            return chain.filter(exchange);
        };
    }
}
```

Because the filter is a bean in the application context, a client bound to the context can assert the header added by the filter:

```java
client.get()
        .uri("/api/greetings/Lan")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals("X-Trace-Source", "webflux-filter");
```

The filter sets the header before calling `chain.filter(exchange)`, so the header is present before the handler writes the body and commits the response. If you need to modify the response after downstream processing completes, account for the fact that the response may already be committed and headers may no longer be modifiable.

### Testing Global Exception Handlers

WebFlux can register a `WebExceptionHandler` or use `@RestControllerAdvice` with `@ExceptionHandler`. When bound to an application context, tests can verify that exceptions are converted into responses according to the global configuration.

```java
@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ApiError> handleInvalidArgument(IllegalArgumentException exception) {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_ARGUMENT", exception.getMessage()));
    }
}

record ApiError(String code, String message) {
}
```

If a controller throws `IllegalArgumentException`, the test can verify the status and body:

```java
client.get()
        .uri("/api/items/invalid")
        .exchange()
        .expectStatus().isBadRequest()
        .expectBody(ApiError.class)
        .value(error -> assertThat(error.code()).isEqualTo("INVALID_ARGUMENT"));
```

`assertThat` in the example comes from AssertJ. This test is meaningful when the advice is registered in the application context; if you only bind directly to a controller without including the advice in the configuration, the result may differ.

## 6. Functional Endpoints Also Belong to the Application Context

WebFlux supports functional routing with `RouterFunction` and `HandlerFunction`. When routes are registered as beans in a context configured with WebFlux, `bindToApplicationContext` can test them alongside other controllers and filters.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration
class GreetingRoutes {

    @Bean
    RouterFunction<ServerResponse> greetingRoute() {
        return route(GET("/functional/greeting"), request ->
                ServerResponse.ok().bodyValue(new Greeting("Hello from route")));
    }
}
```

The test calls the route through the same client:

```java
client.get()
        .uri("/functional/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Greeting.class)
        .isEqualTo(new Greeting("Hello from route"));
```

Endpoints configured in multiple styles can be tested within the same WebFlux pipeline.

## 7. Testing Codecs and Content Negotiation

WebFlux uses codecs to read request bodies and write response bodies. When bound to an application context, tests use the codecs configured in the context rather than relying solely on the default configuration of a single standalone controller.

Example controller accepting JSON:

```java
@PostMapping("/api/messages")
Mono<MessageView> create(@RequestBody Mono<CreateMessage> request) {
    return request.map(value -> new MessageView(value.text(), "ACCEPTED"));
}

record CreateMessage(String text) {
}

record MessageView(String text, String status) {
}
```

Test verifying that JSON request is read and JSON response is written:

```java
client.post()
        .uri("/api/messages")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateMessage("Reactive testing"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(MessageView.class)
        .isEqualTo(new MessageView("Reactive testing", "ACCEPTED"));
```

If the application registers custom codecs, `maxInMemorySize` settings, a custom JSON mapper, or custom readers/writers, binding to the context ensures the test uses that exact configuration. This is one reason to use an application context rather than creating a client around an isolated handler when you need to verify application-wide serialization configuration.

## 8. Configuring the Client After Binding

`configureClient()` allows setting client-side options after the server side has been built. Some common options:

```java
WebTestClient client = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .baseUrl("http://localhost")
        .defaultHeader("X-Test-Client", "webflux-context-test")
        .build();
```

You can use default headers to pass shared data across requests, such as a test tenant or correlation ID. Avoid putting sensitive credentials or shared tokens into test configuration unnecessarily; each test should explicitly control request identity and permissions.

The client also supports `WebClient`-style filters:

```java
WebTestClient client = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .filter((request, next) -> next.exchange(request))
        .build();
```

A client filter sits on the request-sending side of the test. It differs from a `WebFilter`, which runs inside the WebFlux application. When debugging, identify whether an assertion or log is observing the client layer or the server layer.

## 9. Testing Reactive Bodies and Streams

WebTestClient can assert single bodies, lists, JSON paths, or streams. For finite responses, `expectBody(...)` is usually sufficient:

```java
client.get()
        .uri("/api/items")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(ItemView.class)
        .hasSize(2);
```

For streaming endpoints such as Server-Sent Events, you can obtain a `FluxExchangeResult` and use Reactor Test to verify items over time:

```java
FluxExchangeResult<ServerSentEvent<String>> result = client.get()
        .uri("/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(new ParameterizedTypeReference<ServerSentEvent<String>>() {});

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event -> "ready".equals(event.data()))
        .thenCancel()
        .verify();
```

To test a stream, ensure the publisher emits data in a way the test can observe. For infinite streams, `thenCancel()` terminates the subscription after the events to verify. Do not use `expectBody()` for a stream that never completes, because the test will wait for the body to finish.

## 10. Distinguishing Mock WebFlux Context from a Real Server

`bindToApplicationContext` creates an in-memory mock server handler. Requests do not travel over TCP sockets, Netty channels, or a real HTTP connector. Therefore, tests can verify the WebFlux pipeline but do not verify server/network-level behaviors.

| Behavior | `bindToApplicationContext` | Real Server (`bindToServer` or Boot `RANDOM_PORT`) |
|---|---|---|
| Controller and functional route mapping | Yes | Yes |
| `WebFilter`, advice, and codecs in context | Yes | Yes |
| Binding, validation, content negotiation | Yes | Yes |
| Reactive publishers and response bodies | Yes, in mock exchange | Yes, over real transport |
| Netty channels, TCP, TLS, HTTP connector | No | Yes |
| Server request/response limits and network timeouts | Incomplete | Testable |
| Client disconnect and transport-level backpressure | Not fully simulated | Testable |

When you need to test a real embedded server, you can start the application with `RANDOM_PORT` and connect WebTestClient to the server:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebFluxServerIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void servesRequestThroughTheRunningServer() {
        webTestClient.get()
                .uri("/api/health")
                .exchange()
                .expectStatus().isOk();
    }
}
```

In this configuration, Spring Boot can auto-configure `WebTestClient` to send requests to the running server port. This is an integration test over HTTP transport, distinct from manually calling `bindToApplicationContext`.

## 11. Common Pitfalls When Using `bindToApplicationContext`

### Context has not been refreshed

`WebTestClient` requires a context that has completed bean initialization. If you create a context manually with the no-arg constructor, register the configuration and call `refresh()` before binding. Do not create the client before the web infrastructure has been registered.

### Context is not configured for WebFlux

If the context lacks a `WebHandler` bean or is not configured with `@EnableWebFlux`/Spring Boot WebFlux auto-configuration, `bindToApplicationContext` lacks the infrastructure to handle requests. Check whether the application is running WebFlux or Spring MVC. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot may choose MVC as the application type based on classpath conditions; when a reactive application is intended, configure the appropriate dependencies and application type.

### Confusing WebFilter with Servlet Filter

WebFlux uses `org.springframework.web.server.WebFilter`; Spring MVC/Servlet uses `jakarta.servlet.Filter`. A Servlet Filter does not automatically become a `WebFilter` merely by being a bean. Check the right filter type for the active stack.

### Expecting context binding to start Netty

`bindToApplicationContext` does not start a Netty server. If the test needs connectors, ports, TLS, or transport behavior, use a real server and connect with an HTTP client.

### Registering only a controller while omitting shared configuration

If the test depends on global filters, advice, custom codecs, or router beans, they must be present in the application context. Binding a controller directly does not automatically bring missing beans into the pipeline.

### Using the client after the context has been closed

A client built from a context depends on components inside that context. Keep the context alive for the entire duration of tests using the client and close the context after tests finish.

### Testing streams without a termination condition

`expectBody()` waits for the body to complete. For infinite publishers or SSE, use `returnResult()` and Reactor Test to assert a number of events and then cancel the subscription.

## 12. When to Choose Each Binding Mode?

| Need | Choice |
|---|---|
| Test a standalone controller with minimal configuration | `bindToController(...)`. |
| Test an individual functional route | `bindToRouterFunction(...)`. |
| Test multiple controllers, routers, filters, advice, and codecs together | `bindToApplicationContext(...)`. |
| Test full WebFlux configuration in a Spring Boot application without opening a port | `@SpringBootTest(MOCK)` and bind the application context, or auto-configure WebTestClient for the mock environment. |
| Test Netty, TCP, TLS, timeouts, and requests over real HTTP | `RANDOM_PORT` with configured WebTestClient, or `bindToServer()` against a running server. |

When choosing a binding mode, start from the scope you need to verify. If the test only needs to verify the logic of a single controller, loading the entire application context can make the test heavier and harder to isolate. If the test needs to verify global `WebFilter`s, custom codecs, or multiple cooperating routes, binding to the context provides the exact configuration under test.

## 13. Checklist for WebFlux Context Tests

- [ ] Application context has been refreshed before binding the client.
- [ ] Context has WebFlux configuration and an appropriate `WebHandler` bean.
- [ ] Test uses `WebFilter` rather than confusing it with Servlet `Filter`.
- [ ] Controllers, functional routes, advice, and filters under test are all present in the context.
- [ ] Client is created using `WebTestClient.bindToApplicationContext(context)`.
- [ ] Assertions verify status, headers, and body against the endpoint contract.
- [ ] If custom codecs or content negotiation are needed, the test uses a context with the exact codec configuration.
- [ ] For non-terminating streams, the test uses `returnResult()` and manages subscription cancellation.
- [ ] Mock context tests are not treated as proof for Netty, TCP, TLS, or connectors.
- [ ] If real HTTP transport is needed, a separate server test uses `RANDOM_PORT` or `bindToServer()`.

`bindToApplicationContext` supports testing WebFlux at the application context scope: requests pass through routes, controllers, filters, exception handlers, and codecs configured together. It is a useful option for fast, clearly scoped reactive web integration tests; when you need to verify Netty or network behavior, add tests connecting to a real server.
