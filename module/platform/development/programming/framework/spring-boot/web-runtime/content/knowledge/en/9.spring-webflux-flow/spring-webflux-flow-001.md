# Request Flow Through the Reactive Server, HttpHandler, and WebHandler in Spring WebFlux

## 1. Objectives and Key Takeaways

An HTTP request entering a **Spring WebFlux** application does not go directly from Reactor Netty to an `@GetMapping` method. It passes through multiple layers of adaptation and dispatching, among which two interfaces are especially important:

- **HttpHandler** (org.springframework.http.server.reactive.HttpHandler) is the minimal contract for handling HTTP requests and responses at an abstract level, without depending directly on types specific to Reactor Netty, Tomcat, or Jetty.
- **WebHandler** (org.springframework.web.server.WebHandler) is the web-application-level contract that receives a **ServerWebExchange**. It can be wrapped with `WebFilter` and `WebExceptionHandler`; in a default WebFlux application, the central `WebHandler` is typically **DispatcherHandler**.

With the standard **Spring Boot 3.3.x + spring-boot-starter-webflux + Reactor Netty** configuration, the high-level flow is:

~~~text
Client TCP/TLS/HTTP
  -> Reactor Netty HttpServer
  -> ReactorHttpHandlerAdapter
  -> Spring HttpHandler (typically HttpWebHandlerAdapter)
  -> ServerWebExchange
  -> WebExceptionHandler/WebFilter chain
  -> Main WebHandler (DispatcherHandler)
  -> HandlerMapping -> HandlerAdapter -> HandlerResultHandler
  -> write response via reactive ServerHttpResponse
  -> Reactor Netty sends bytes to client
~~~

This is a **logical flow** model, not a linear stack trace or a claim that every request reaches `DispatcherHandler`: a `WebFilter` can short-circuit, a `WebExceptionHandler` can handle errors, observability/codec components can participate, and parts of the pipeline can execute asynchronously. **Each HTTP request is not assigned its own dedicated Java thread by default**; execution depends on Reactor, schedulers, the event loop, subscription, and whether blocking or non-blocking APIs are called.

This lesson helps you:

1. Distinguish the HTTP server, runtime adapter, `HttpHandler`, `WebHandler`, and `DispatcherHandler`.
2. Understand how `ServerHttpRequest`/`ServerHttpResponse` differ from `ServerWebExchange`.
3. Know how `WebHttpHandlerBuilder` assembles filters and exception handlers into the pipeline.
4. Trace how annotated controllers and functional routes are discovered and invoked.
5. Explain the role of `Mono<Void>`, request body `Flux<DataBuffer>`, and response commit.
6. Write and test a Java 17+ Spring WebFlux application containing an annotated controller, a functional route, and a `WebFilter`.
7. Diagnose 404s, body parsing issues, filters, 500 errors, event-loop blocking, and WebFlux vs. MVC confusion.

## 2. Prerequisite: The Application Must Actually Run a WebFlux Server

Minimal Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

This starter typically provides Spring WebFlux and Reactor Netty. When Spring MVC is not present on the classpath to override detection and no special custom configuration is applied, Spring Boot infers **WebApplicationType.REACTIVE**, creates a reactive web `ApplicationContext`, auto-configures a `ReactiveWebServerFactory`, and builds the appropriate `HttpHandler`.

**A common pitfall:** if both `spring-boot-starter-web` and `spring-boot-starter-webflux` are placed on the classpath together, Spring Boot **defaults to prioritizing Spring MVC/Servlet**. You can still use `WebClient`, `Mono`, or `Flux` in MVC, but HTTP requests will not automatically flow through the WebFlux `DispatcherHandler` because of that.

When you genuinely need a reactive server in an application that has both starters, you can explicitly set:

~~~properties
spring.main.web-application-type=reactive
~~~

This changes the web `ApplicationContext` type Boot selects; it does not automatically make blocking dependencies non-blocking. For a pure WebFlux application as in this lesson's examples, this property is not needed.

### WebFlux Does Not Automatically Mean Reactor Netty Is Required

Spring WebFlux is designed to work with multiple supported HTTP runtimes. **HttpHandler** is the abstraction boundary so the web framework layer does not need separate controller implementations for each server. Reactor Netty is the common default choice of `starter-webflux`; the server-layer adapter path can differ when using another server.

You should distinguish:

| Component | What is it? | Role in a request |
| --- | --- | --- |
| Reactor Netty HttpServer | Reactive HTTP server runtime | Manages network channels, HTTP parsing/encoding, I/O, and event loops |
| NettyReactiveWebServerFactory | Spring Boot factory | Starts the embedded Reactor Netty server during the Spring Boot lifecycle |
| ReactorHttpHandlerAdapter | Adapter between Reactor Netty and Spring HTTP abstraction | Converts Reactor Netty request/response into an `HttpHandler` invocation |
| HttpHandler | Low-level Spring HTTP interface | Receives `ServerHttpRequest`/`ServerHttpResponse`, returns `Mono<Void>` |
| HttpWebHandlerAdapter | `HttpHandler` implementation for the `WebHandler` stack | Creates `ServerWebExchange` and invokes the `WebHandler` chain |
| WebHandler | Higher-level web request handling interface | Receives `ServerWebExchange`, returns `Mono<Void>` |
| WebFilter | Reactive filter in the WebFlux model | Wraps the `WebHandler` chain; can continue or short-circuit |
| WebExceptionHandler | Error handling in the `WebHandler` chain | Converts error signals into responses when possible |
| DispatcherHandler | Front controller of Spring WebFlux | Selects a handler, invokes the adapter, and handles the result |
| HandlerMapping/HandlerAdapter/HandlerResultHandler | Dispatch strategies | Maps routes, executes handlers, writes/renders results |

**`NettyReactiveWebServerFactory` is not a request handler.** It is used during startup to create the server. After the server has started, each request passes through the runtime adapter/handler; the factory is not instantiated per request.

## 3. Layer 1: Reactor Netty Accepts Connections and HTTP Requests

Reactor Netty runs on top of Netty event loops. For a typical HTTP/1.1 request, work at this layer includes:

1. The OS and channel accept the TCP connection; the TLS handshake is handled if HTTPS is configured.
2. Netty reads bytes asynchronously and processes the HTTP protocol according to server configuration.
3. Reactor Netty provides `HttpServerRequest` and `HttpServerResponse` objects to the registered handler function.
4. Spring's adapter is invoked and returns a **reactive completion publisher** representing response processing.
5. The server runtime manages the subscription, I/O, and byte transmission according to the transport flow.

Steps one through five are a general description. TCP keep-alive can serve multiple requests over one connection; HTTP/2 has multiplexing; a proxy may terminate TLS in front of the application. You cannot equate "one request" with "one new socket" or "one new thread."

### What Does Event Loop Mean?

Netty uses a relatively small number of event-loop threads to handle many connections. This is efficient when most work is non-blocking. If a controller or service calls `Thread.sleep`, blocking JDBC, or `.block()` on the Netty event loop, the thread can be held up and increase latency for other requests.

Reactive APIs enable non-blocking and asynchronous processing; **they do not automatically turn blocking code into non-blocking code**. When forced to use blocking APIs, explicitly design boundaries and an appropriate scheduler, and measure resource usage and throughput.

## 4. Layer 2: ReactorHttpHandlerAdapter Connects Netty and HttpHandler

**org.springframework.http.server.reactive.ReactorHttpHandlerAdapter** is the adapter for Reactor Netty. Its API effectively has the following shape:

~~~java
public class ReactorHttpHandlerAdapter
        implements java.util.function.BiFunction<
                reactor.netty.http.server.HttpServerRequest,
                reactor.netty.http.server.HttpServerResponse,
                reactor.core.publisher.Mono<Void>> {

    // Illustrative signature; not the full actual source code:
    public reactor.core.publisher.Mono<Void> apply(
            reactor.netty.http.server.HttpServerRequest request,
            reactor.netty.http.server.HttpServerResponse response) {
        // ...
        return null;
    }
}
~~~

This is an **API signature sketch**, not standalone runnable code. The adapter's actual job is to convert server-specific types into Spring's HTTP abstractions and then delegate to the configured `HttpHandler`.

More precisely, with Reactor Netty:

~~~text
Reactor Netty HttpServerRequest
     -> Spring ReactorServerHttpRequest
Reactor Netty HttpServerResponse
     -> Spring ReactorServerHttpResponse
     -> HttpHandler.handle(ServerHttpRequest, ServerHttpResponse)
~~~

As a result, Spring WebFlux code above this layer uses Spring interfaces rather than forcing controllers to understand Reactor Netty objects.

### Why Is This Adapter Useful?

- Decouples the network runtime from the web-handling framework.
- Reduces server-specific dependencies in `HandlerMapping`/controllers.
- Allows WebFlux to support multiple reactive HTTP runtimes integrated by Spring.
- Makes it possible to test the `HttpHandler`/`WebHandler` layer without having to open a socket in some cases.

**You should not manually instantiate `ReactorHttpHandlerAdapter` and call `apply` inside a controller.** Spring Boot and WebFlux already configure the adapter for use at the server boundary.

## 5. Layer 3: HttpHandler — The Low-Level HTTP Contract

Spring defines the interface:

~~~java
package org.springframework.http.server.reactive;

import reactor.core.publisher.Mono;

@FunctionalInterface
public interface HttpHandler {
    Mono<Void> handle(
            ServerHttpRequest request,
            ServerHttpResponse response);
}
~~~

This is the core contract structure in Spring Framework 6.x (omitting any additional annotations if present in a specific Javadoc version).

Explanation:

- `ServerHttpRequest` represents an HTTP request under Spring's abstraction: path, method, headers, cookies, body `Publisher`.
- `ServerHttpResponse` represents status, headers, cookies, and the ability to write the response body.
- `Mono<Void>` describes completion or error of processing, **not the HTTP body**, nor a boolean confirming "200 was returned."
- `HttpHandler` does not yet include all web-application concepts such as session, localized context, form data, request attributes, or security principal in a unified exchange object.

A custom `HttpHandler` can return a fixed body, but if you arbitrarily replace it as the default server bean, you may bypass `WebFilter`, `WebExceptionHandler`, `DispatcherHandler`, codecs, and integrations provided by Spring Boot. For typical APIs, write a controller, router function, or `WebFilter` instead of replacing the entire `HttpHandler`.

### Illustrative API Example

~~~java
// Illustrates API usage; do not use to replace the default HttpHandler:
HttpHandler handler = (request, response) -> {
    response.setStatusCode(org.springframework.http.HttpStatus.NO_CONTENT);
    return response.setComplete();
};
~~~

This snippet is valid in meaning when placed in Java code with the necessary imports, but it **does not declare a server by itself** and is not a standalone Spring Boot application.

When you see `Mono<Void>` in `HttpHandler`, think "when does the processing chain finish or signal an error?" rather than "the data value the client receives is Void."

## 6. Layer 4: HttpWebHandlerAdapter Creates ServerWebExchange

The `WebHandler` interface uses:

~~~java
package org.springframework.web.server;

import reactor.core.publisher.Mono;

@FunctionalInterface
public interface WebHandler {
    Mono<Void> handle(ServerWebExchange exchange);
}
~~~

`HttpHandler` only receives two objects, request and response; `WebHandler` receives **ServerWebExchange**, which bundles web-level information and utility capabilities.

**HttpWebHandlerAdapter** is the bridge that implements the `HttpHandler` contract by creating a `ServerWebExchange` and then invoking the assembled `WebHandler` chain. It is a distinct class from `ReactorHttpHandlerAdapter`:

~~~text
ReactorHttpHandlerAdapter:
  Reactor Netty objects
    -> Spring ServerHttpRequest / ServerHttpResponse
    -> invokes HttpHandler

HttpWebHandlerAdapter:
  ServerHttpRequest / ServerHttpResponse
    -> ServerWebExchange
    -> invokes WebHandler chain
~~~

The two classes have easily confused names, but sit at **two different boundaries**. It is not the case that "`HttpHandler` extends `WebHandler`" or "`DispatcherHandler` directly implements `HttpHandler`": Spring WebFlux uses adapters to connect the contracts.

### What Does ServerWebExchange Carry?

Commonly used data and APIs:

- `exchange.getRequest()`: the request normalized under Spring's abstraction.
- `exchange.getResponse()`: the response allowing status/header/body updates before commit.
- `exchange.getAttributes()`: a per-request attribute map, useful for logging, tracing, and intermediate data.
- `exchange.getSession()`: `Mono<WebSession>` following WebFlux's session design.
- `exchange.getPrincipal()`: `Mono<Principal>` if a principal is available from security/runtime.
- `exchange.getFormData()`: reads form data according to framework semantics.
- `exchange.getMultipartData()`: supports multipart data.
- `exchange.getLocaleContext()`: the locale context.
- `exchange.getLogPrefix()`: a per-request prefix for logging.
- `exchange.mutate()`: creates an appropriate exchange decorator/builder to forward a mutated request.

Several APIs return **Mono** because not all data is immediately ready or synchronous. For example, you should not call `.block()` to retrieve the session directly on the Netty event loop.

### Exchange Is Not a Database Transaction

The name `ServerWebExchange` only refers to the web request/response exchange model. It does not automatically start a database transaction, does not authenticate the request, and does not guarantee that the entire asynchronous flow stays on the same thread.

## 7. How Does WebHttpHandlerBuilder Assemble the WebHandler Chain?

**org.springframework.web.server.adapter.WebHttpHandlerBuilder** is an infrastructure tool that builds an `HttpHandler` from WebFlux components. Given the application's `ApplicationContext`, it can look up specific beans:

- A bean named **webHandler** as the main `WebHandler`; in standard annotation/functional WebFlux dispatch, this is `DispatcherHandler`.
- Registered **WebFilter** beans.
- Registered **WebExceptionHandler** beans.
- Supporting components such as `WebSessionManager`, `ServerCodecConfigurer`, `LocaleContextResolver`, and others depending on version and configuration.

Conceptually:

~~~java
HttpHandler httpHandler =
        WebHttpHandlerBuilder.applicationContext(applicationContext)
                .build();
~~~

This illustrates code inside an application that already has a Spring `ApplicationContext`; it is **not a standalone program** and you do not need to call it manually in a standard Spring Boot application.

The builder performs two tasks:

1. Assembles the **WebHandler chain**: the main `WebHandler` is wrapped by `WebFilter`s, and then the exception-handling layer on the outside.
2. Uses **HttpWebHandlerAdapter** to adapt that chain into an `HttpHandler` usable at the HTTP server boundary.

The diagram below shows the logical wrapping:

~~~mermaid
flowchart TD
    A["HttpHandler: HttpWebHandlerAdapter"] --> B["ServerWebExchange"]
    B --> C["ExceptionHandlingWebHandler"]
    C --> D["FilteringWebHandler"]
    D --> E["WebFilter 1"]
    E --> F["WebFilter 2 / Security WebFilters if present"]
    F --> G["DispatcherHandler (Main WebHandler)"]
    G --> H["Mapping / invocation / result handling"]
    H --> I["Reactive response write"]
    I --> J["Mono<Void> completion or error"]
    J -. "error propagates upstream" .-> C
~~~

**Diagram note:** Arrows indicate the inbound processing order. With Reactor, it is the assembled and subscribed `Publisher` chain that drives execution; completion/error callbacks can run in the reverse order of the wrapping layers. Do not treat the diagram as an exact line-by-line stack trace order.

### Order of WebExceptionHandler and WebFilter

In the default `WebHandler` chain built by `WebHttpHandlerBuilder`, `WebExceptionHandler` is positioned to handle error signals emitted from inner `WebFilter`s and the inner `WebHandler`. This allows errors from a controller or from a filter to be converted into a response if it has not been committed yet.

A `WebFilter` **is not automatically an exception handler**. If a filter needs custom error handling, it can use appropriate reactive operators, while application-wide errors should consider `WebExceptionHandler` or framework exception handling.

## 8. WebFilter: Reactive Middleware Around WebHandler

The interface:

~~~java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
~~~

For a normal request, a filter calls:

~~~java
return chain.filter(exchange);
~~~

If a filter **does not call `chain.filter`**, the request can stop at the filter and the filter completes the response itself—for example, an access-denial mechanism. This is a middleware short-circuit, unlike simply adding a header.

A filter can handle:

- Correlation IDs and logging/observability.
- CORS in appropriate configurations.
- Authentication/authorization via reactive Spring Security.
- Common headers before the response commits.
- Timing and statistics for completion, error, and cancellation.
- Decorating the request/response when a middleware feature requires it.

### Safe and Simple WebFilter Example

~~~java
package com.example.flow;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class FlowHeaderFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().getHeaders()
                .set("X-Flow", "webfilter");

        return chain.filter(exchange);
    }
}
~~~

This is a complete class usable in the Spring Boot example in Section 15. When a request passes through the filter, the response will carry the `X-Flow: webfilter` header unless another component actively modifies or removes it before commit.

**Do not write:**

~~~java
// Wrong in a normal WebFilter:
chain.filter(exchange).subscribe();
return Mono.empty();
~~~

Because the server runtime manages subscription, calling `subscribe()` manually detaches the lifecycle flow, making error handling, completion, and response commit hard to control; it can cause races or send the response too early. A filter must **return** the chain `Publisher`.

### Filter Order

`WebFilter`s can be ordered using `@Order` or `Ordered`. When multiple filters exist (especially security), their order affects headers, tracing, authentication, and exception handling. Do not guess the order when multiple libraries are involved: inspect the actual bean order and test security policies.

Do not confuse `WebFilter` with **jakarta.servlet.Filter**. The WebFlux reactive stack uses `WebFilter`, while the Servlet/MVC pipeline uses Servlet `Filter`. Having both APIs imported does not mean they run on the same request.

## 9. DispatcherHandler: WebFlux's Main WebHandler

In WebFlux applications using annotated controllers or functional routes, Spring configures **DispatcherHandler** as the web dispatcher. It implements `WebHandler`, meaning its handling method accepts `ServerWebExchange` and returns `Mono<Void>`.

Logical path inside `DispatcherHandler`:

1. Ask each **HandlerMapping** in order to find a matching handler.
2. Once a handler is found, find a **HandlerAdapter** that supports that handler type.
3. The adapter executes the handler according to its mechanism and returns a **HandlerResult**.
4. Choose a **HandlerResultHandler** that supports the result to write the response directly or render a view.
5. Complete the `Publisher`; exceptions are handled by the appropriate error-handling branch when possible.

Diagram:

~~~mermaid
flowchart TD
    A["DispatcherHandler.handle(exchange)"] --> B["HandlerMapping"]
    B --> C{"Matching handler found?"}
    C -->|No| D["No handler found -> appropriate not-found error"]
    C -->|Yes| E["HandlerAdapter supporting handler"]
    E --> F["Execute handler: Mono<HandlerResult>"]
    F --> G["HandlerResultHandler"]
    G --> H["Write body or render view"]
    H --> I["Mono<Void> completes"]
~~~

**`DispatcherHandler` is not Servlet `DispatcherServlet`.** They play analogous front-controller roles but live on two different stacks. Annotations like `@GetMapping` may look identical without meaning the underlying machinery is the same.

## 10. Annotated Controllers and Functional Routes Share the Infrastructure

### 10.1 Annotated Controller

Example:

~~~java
@RestController
class GreetingController {

    @GetMapping("/api/greet/{name}")
    public Mono<String> greet(@PathVariable String name) {
        return Mono.just("Hello, " + name);
    }
}
~~~

The snippet above only illustrates the method/class, not a standalone file with imports.

In this flow:

- **RequestMappingHandlerMapping** finds the `HandlerMethod` annotated with `@GetMapping`.
- **RequestMappingHandlerAdapter** in the **reactive package** resolves arguments and invokes the method.
- **HandlerResult** wraps the return type, reactive value, and metadata.
- **ResponseBodyResultHandler** supports `@ResponseBody`/`@RestController`; codecs (`HttpMessageWriter`) write the body according to the media type.

A `Mono<String>` is not an HTTP response that has already been sent the instant the controller returns. It is a `Publisher` that the framework subscribes to, processes in context, and writes the body from as request processing progresses.

### 10.2 Functional Endpoints

Spring WebFlux also supports `RouterFunction<ServerResponse>`:

~~~java
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route(
            RequestPredicates.GET("/functional/ping"),
            request -> ServerResponse.ok().bodyValue("pong"));
}
~~~

This snippet illustrates a `@Bean` method; the complete file appears in Section 15.

The corresponding flow:

- **RouterFunctionMapping** uses route predicates to find a `HandlerFunction`.
- **HandlerFunctionAdapter** invokes the `HandlerFunction` with a `ServerRequest`.
- **ServerResponseResultHandler** processes the `ServerResponse` and writes the HTTP response.

There is no second `DispatcherHandler` dedicated to functional routing. Both styles use the WebFlux dispatch infrastructure appropriate to the handler type.

### 10.3 Comparison Table

| Step | Annotated controller | Functional route |
| --- | --- | --- |
| Mapping | `RequestMappingHandlerMapping` | `RouterFunctionMapping` |
| Handler found | `HandlerMethod` | `HandlerFunction` |
| Adapter | `RequestMappingHandlerAdapter` (WebFlux) | `HandlerFunctionAdapter` |
| Result | `HandlerResult` for controller return value | `HandlerResult` containing `ServerResponse` |
| Typical result handler | `ResponseBodyResultHandler`, `ResponseEntityResultHandler`, ... | `ServerResponseResultHandler` |
| HTTP entry point | Same `HttpHandler`/`WebHandler` chain | Same `HttpHandler`/`WebHandler` chain |

Mapping order can affect which handler is selected when patterns overlap. Avoid defining the same route/method in both annotated and functional styles and hoping the framework picks the one you want.

## 11. Request Body and HTTP Codecs in the Reactive Flow

At the HTTP abstraction layer:

~~~java
Flux<DataBuffer> body = exchange.getRequest().getBody();
~~~

This snippet assumes an existing `ServerWebExchange`; you need to import `reactor.core.publisher.Flux` and `org.springframework.core.io.buffer.DataBuffer` when using it in a class.

The body can arrive in multiple chunks rather than requiring the application to receive the entire request body as a single `byte[]` in one read. The framework uses **HttpMessageReader**, **HttpMessageWriter**, **ServerCodecConfigurer**, and appropriate codecs to convert between data buffers and Java objects.

Example in a WebFlux controller:

~~~java
@PostMapping(path = "/api/echo",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<Payload> echo(@RequestBody Mono<Payload> payload) {
    return payload;
}
~~~

This is an illustrative method; the complete file with DTO and imports is in Section 15. With `Content-Type: application/json` and the Jackson codec supported by the starter, JSON is deserialized into `Payload` when the pipeline is subscribed.

**Do not confuse WebFlux codecs with Spring MVC's `HttpMessageConverter`.** They serve a similar message-conversion purpose, but belong to different APIs and pipelines.

### Backpressure and DataBuffer

Reactive Streams backpressure lets downstream control demand toward publishers that support demand. However, you should not conclude that "every byte arriving from the network is stored zero-copy" or that "a `Flux` always bounds total payload size automatically." The server, codecs, buffers, proxies, and each source's backpressure support determine actual behavior.

If you manually read `Flux<DataBuffer>` at a low level, you need to understand:

- `DataBuffer` may use pooled/native memory.
- Do not retain buffers for use long after the request lifecycle ends.
- Do not manually subscribe to the body multiple times; the stream contents should normally be consumed according to the contract.
- `retain`/`release` APIs must be used properly when intervening on pooled buffers manually, to avoid memory leaks or use-after-release bugs.
- Configure `spring.codec.max-in-memory-size` when codecs need to aggregate data in memory; it is not an absolute cap for every streaming path.
- For large uploads, prefer streaming processing or chunked storage rather than buffering everything into an unbounded `List<byte[]>`.

## 12. Which Layers Does the Response Travel Back Through?

A handler can produce a response:

~~~java
@GetMapping(path = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
public Mono<String> hello() {
    return Mono.just("hello");
}
~~~

With `@RestController`:

1. The controller returns a `Publisher` (`Mono<String>`).
2. `HandlerAdapter` turns the result into a `HandlerResult` and returns it to the framework.
3. The appropriate `HandlerResultHandler` determines how to write the body.
4. `HttpMessageWriter`/`Encoder` turns the string into response data according to the media type.
5. `ServerHttpResponse` accepts status, headers, and body.
6. `HttpWebHandlerAdapter` and the HTTP server adapter await/combine the completion `Publisher`.
7. Reactor Netty sends bytes out over the channel, respecting transport and lifecycle conditions.

**Response headers and status must be set before the response is committed.** A `WebFilter` can use:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders().set("X-Flow", "committed");
    return Mono.empty();
});
~~~

This snippet assumes `exchange` is in scope; it is not a standalone class. `beforeCommit` registers a callback before commit, useful when headers depend on processing results. The callback must return an appropriate completing `Mono`; do not perform blocking I/O inside it.

### What Does `Mono<Void>` Completion Mean?

`Mono<Void>` represents completion or error of response processing/writing; it does not imply an empty body. An HTTP response may have a large JSON payload written via `Publisher`s while the orchestration layer still returns `Mono<Void>` to signal when writing finishes.

If an exception occurs **after headers or body have been committed**, an error handler usually cannot change the HTTP status to 500 or write a fresh JSON error body the way it can before commit. A streaming response may terminate abnormally, and the client may receive only a partial body.

## 13. Error Signals and WebExceptionHandler

In a reactive flow, a component can emit an error signal:

~~~java
return Mono.error(new IllegalArgumentException("invalid"));
~~~

This is a `Publisher` snippet; it does not produce a response on its own.

Errors can occur in:

- A `WebFilter` before calling the handler.
- `HandlerMapping` due to no matching route or unmet mapping conditions.
- Argument resolution, JSON decoding, or validation.
- The controller or service during processing.
- `HandlerResultHandler` or response encoding.
- I/O when the client disconnects, times out, or while writing the response.

WebFlux has multiple exception-handling layers:

1. **Handler-specific**: `@ExceptionHandler` inside a controller or `@ControllerAdvice`/`@RestControllerAdvice` can handle errors associated with annotated controllers.
2. **Framework/global WebHandler chain**: `WebExceptionHandler` can handle error signals from the inner chain.
3. **Spring Boot error handling**: a standard Boot application provides reactive web error-handling configuration unless replaced.
4. **Transport**: network errors occurring after response commit may not be convertible into an error body.

Example of a `@RestControllerAdvice` in WebFlux:

~~~java
@RestControllerAdvice
class ApiErrors {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> badRequest(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid request"));
    }
}
~~~

This is an illustrative class; it requires imports for `java.util.Map`, `org.springframework.http.ResponseEntity`, and the annotation classes to compile standalone. If an error originates from a component outside the annotated-controller exception mechanism, check the global `WebExceptionHandler` or the corresponding error chain.

### Error Responses and Security

Do not send stack traces, tokens, `Authorization` headers, internal SQL, or sensitive infrastructure details to clients. Log sufficient correlation IDs and root causes on the server side, and return consistent status and error codes. Avoid swallowing all errors and returning HTTP 200.

## 14. Reactor Subscription, Cancellation, and Thread Model

WebFlux does not "execute every `Mono` the moment it is created." A `Publisher` can describe deferred work; the HTTP runtime and framework are what connect and execute the chain upon subscription.

Comparison example:

~~~java
Mono<String> message = Mono.fromSupplier(() -> "hello");
// Creating the Mono does not mean the supplier has been invoked yet.
// The server framework can subscribe as part of request processing.
~~~

The snippet above is a Java snippet requiring `reactor.core.publisher.Mono`, not a server implementation.

### Key Principles

- **Do not manually subscribe** in a `WebFilter` or controller to produce a response when the framework already receives a `Publisher`.
- **Do not call `.block()` on an event-loop thread** to wait for a database, `WebClient`, or `Mono` to complete.
- **Do not assume every `map`/`flatMap` runs on a single thread**: scheduling and async boundaries depend on the publisher.
- When a client cancels a request or disconnects, cancellation can propagate downstream, but side effects that have already happened (such as a committed database transaction) do not automatically roll back without an appropriate transaction/cancellation mechanism.
- A long-running stream (SSE) can keep the response open; `Mono<Void>` completion only arrives when the stream finishes, is cancelled, or errors.
- For a multi-item `Flux`, backpressure coordinates demand rate; do not assume resources stay bounded if there are unbounded buffers, caches, or retries.
- `ThreadLocal` does not automatically follow a logical request across schedulers; use Reactor `Context` and appropriate context-propagation tools when tracing or security requires it.

### Especially for Logging

Example attaching completion callbacks:

~~~java
return chain.filter(exchange)
        .doOnError(error -> logger.error("Request failed", error))
        .doFinally(signal -> logger.debug("Request terminated: {}", signal));
~~~

This illustrates code inside a `WebFilter` class with a declared logger. `doFinally` runs with `COMPLETE`/`ERROR`/`CANCEL` signals; it does not necessarily correspond to whether an HTTP status has already been written. If the body has already committed, the logger may still see cancellation or error; do not try to modify the response after it has committed.

## 15. Complete Example: Tracing Two Handler Styles Through the Same WebFlux Chain

We build a Spring Boot 3.3.13, Java 17 application:

- Embedded Reactor Netty listens on default HTTP port 8080.
- A `WebFilter` adds the `X-Flow` header to every request.
- An annotated controller handles `GET /api/greet/{name}` and `POST /api/echo`.
- A functional `RouterFunction` handles `GET /functional/ping`.
- Integration tests use `WebTestClient` against a real server on `RANDOM_PORT`.
- Do not add `spring-boot-starter-web` to avoid Boot defaulting to Servlet MVC.

### 15.1 Project Structure

~~~text
webflux-flow-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/com/example/flow/
    │       ├── FlowApplication.java
    │       ├── GreetingController.java
    │       ├── FunctionalRoutes.java
    │       └── FlowHeaderFilter.java
    └── test/
        └── java/com/example/flow/
            └── FlowIntegrationTests.java
~~~

### 15.2 settings.gradle

~~~groovy
rootProject.name = 'webflux-flow-demo'
~~~

### 15.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

If the project has a Gradle wrapper, use `./gradlew` on Linux/macOS or `gradlew.bat` on Windows; the examples below use an installed `gradle` command. The versions listed are an illustrative configuration consistent with Spring Boot 3.3.x; when using another version, let Boot dependency management choose the corresponding Reactor/Netty versions.

### 15.4 FlowApplication.java

~~~java
package com.example.flow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(FlowApplication.class, args);
    }
}
~~~

### 15.5 GreetingController.java

~~~java
package com.example.flow;

import java.util.Locale;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class GreetingController {

    @GetMapping(
            path = "/greet/{name}",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> greet(
            @PathVariable String name,
            @RequestParam(defaultValue = "false") boolean upper) {

        String greeting = "Hello, " + name;
        return Mono.just(upper
                ? greeting.toUpperCase(Locale.ROOT)
                : greeting);
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Payload> echo(@RequestBody Mono<Payload> input) {
        return input.map(payload ->
                new Payload(payload.message().trim()));
    }
}

record Payload(String message) {
}
~~~

Explanation:

- `@GetMapping` is recognized by `RequestMappingHandlerMapping`.
- `RequestMappingHandlerAdapter` resolves `@PathVariable` and `@RequestParam`.
- The method returns `Mono<String>`; the framework handles the return value and writes `text/plain`.
- POST uses `@RequestBody Mono<Payload>`; JSON decoding happens inside the reactive pipeline.
- The record `Payload` is package-private in the same package and handled by Jackson via Java record support.
- If the JSON is missing `message` or `message` is `null`, the `map` method will throw a `NullPointerException` when calling `trim()`; this is not production input handling. Validation and an error policy are needed when building a real API.

### 15.6 FunctionalRoutes.java

~~~java
package com.example.flow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class FunctionalRoutes {

    @Bean
    public RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route(
                RequestPredicates.GET("/functional/ping"),
                request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("pong"));
    }
}
~~~

For this route, the handler is found via `RouterFunctionMapping` instead of `RequestMappingHandlerMapping`. The functional route returns a `ServerResponse`, and then `ServerResponseResultHandler` writes the response. Both styles still sit under the same HTTP handler and `WebFilter` chain.

### 15.7 FlowHeaderFilter.java

~~~java
package com.example.flow;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class FlowHeaderFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().getHeaders()
                .set("X-Flow", "webfilter");

        return chain.filter(exchange);
    }
}
~~~

This single filter is invoked for both `/api/greet/An` and `/functional/ping` when requests pass through the WebFlux chain. The `X-Flow` header is set before the response commits. It does not dictate the exact callbacks of all other filters in a real application, because ordering and conditions can change when security/CORS or custom filters are added.

### 15.8 Running and Inspecting Results

From the project directory:

~~~bash
gradle clean test bootRun
~~~

In another terminal:

~~~bash
curl -i 'http://127.0.0.1:8080/api/greet/An?upper=true'
~~~

Expected HTTP 200, `Content-Type` `text/plain`, header:

~~~text
X-Flow: webfilter
~~~

And body:

~~~text
HELLO, AN
~~~

Call the functional route:

~~~bash
curl -i 'http://127.0.0.1:8080/functional/ping'
~~~

Expected HTTP 200, header `X-Flow: webfilter`, and body:

~~~text
pong
~~~

Call the JSON endpoint:

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/echo' \
    -H 'Content-Type: application/json' \
    -d '{"message":" WebFlux "}'
~~~

Expected HTTP 200 and an equivalent JSON body:

~~~json
{"message":"WebFlux"}
~~~

Do not assert every exact header (`Date`, `Content-Length`, `Connection`) or JSON field order, because those details depend on the server and encoder. These results are expected from the source code, **not logs from an execution run inside this document**.

### 15.9 FlowIntegrationTests.java

~~~java
package com.example.flow;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FlowIntegrationTests {

    @LocalServerPort
    private int port;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void annotatedControllerUsesWebFluxPipeline() {
        client().get()
                .uri("/api/greet/An?upper=true")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Flow", "webfilter")
                .expectBody(String.class)
                .isEqualTo("HELLO, AN");
    }

    @Test
    void functionalRouteUsesSameFilterChain() {
        client().get()
                .uri("/functional/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Flow", "webfilter")
                .expectBody(String.class)
                .isEqualTo("pong");
    }

    @Test
    void jsonBodyIsDecodedAndEncoded() {
        client().post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("message", " WebFlux "))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("WebFlux");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

The test uses `RANDOM_PORT` so it does not depend on port 8080 being free. `WebTestClient.bindToServer` actually sends HTTP requests over TCP to the embedded server during the test. Passing tests prove that from the HTTP server through `WebFilter` to both handler styles everything works, and that the JSON codec decoded/encoded the body. They **do not prove** non-blocking performance or good backpressure under all loads.

### 15.10 Distinguishing From a Mock Setup Test

`WebTestClient` can also be bound to an `ApplicationContext`/`WebHandler` to test without opening a real HTTP server. When testing that way, the network adapter `ReactorHttpHandlerAdapter` is not verified over a socket. Because this lesson focuses on the path *through the reactive server*, using `RANDOM_PORT` + `bindToServer` lets you observe the fuller path.

## 16. Different Branches of the Same HTTP Request

The path is not identical for every request. Some scenarios:

### 16.1 Unmapped URL

If `GET /missing` matches no controller or `RouterFunction`, `DispatcherHandler` can emit a handler-not-found signal. WebFlux/Boot error handling can produce HTTP 404. `WebFilter`s may still have executed before discovering the URL does not exist.

### 16.2 Filter Blocks the Request

A policy-checking `WebFilter` can set a status, call `response.setComplete()`, and skip calling `chain.filter(exchange)`. In that case `DispatcherHandler` may **never be invoked** for that request. Test both rejected and valid requests.

### 16.3 Wrong Content-Type or Unreadable Body

A `POST /api/echo` request with an unsupported `Content-Type` can yield HTTP 415, while malformed JSON can yield HTTP 400. Actual behavior depends on mappings, codecs, and error handling. `RequestMappingHandlerAdapter` might not even invoke the controller method if decoding `@RequestBody` fails.

### 16.4 Controller Emits Mono.error

A controller returning `Mono.error` or throwing an exception before returning a publisher can be handled via `@ExceptionHandler` or the `WebExceptionHandler` chain depending on where the error occurs and configuration. If the response has not committed yet, an error status/body can be built; if already committed, changing the status cannot be assumed to work safely.

### 16.5 Client Cancels the Request

A client may close the connection mid-way while reading a streaming response. Cancellation can propagate to `Publisher`s; however, database writes or external side effects already executed are not automatically undone. Design idempotency, transactions, and compensation per business requirements.

## 17. WebFlux and Spring MVC: Similar Names, Different Flows

| Aspect | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Front controller | `DispatcherServlet` | `DispatcherHandler` |
| Infrastructure HTTP abstraction | Servlet request/response | Reactive `ServerHttpRequest`/`ServerHttpResponse` |
| Web middleware | Servlet `Filter` / `HandlerInterceptor` | `WebFilter` / `WebExceptionHandler` |
| Request context object | `HttpServletRequest`, `Model`... | `ServerWebExchange` |
| Adapter result | `ModelAndView` or handled response | `Mono<HandlerResult>` per WebFlux contract |
| Body codec | `HttpMessageConverter` | `HttpMessageReader` / `HttpMessageWriter` |
| I/O handling | Servlet API; has async support | Reactive server adapters and `Publisher`s |
| Typical starter server | Tomcat | Reactor Netty |

Spring MVC supports returning `Mono` or `Flux` in some cases. Therefore, do not judge solely from return types. Check whether `SpringApplication` selected `SERVLET` or `REACTIVE`, the runtime factory, the application context, and the front controller.

Likewise, **`WebClient` is an HTTP client**, not proof that WebFlux `DispatcherHandler` is serving inbound server requests. An MVC app can use `WebClient` while still receiving HTTP via Tomcat + `DispatcherServlet`.

## 18. Observing and Debugging the Path Layer by Layer

### 18.1 Startup Logs

Identify which embedded server is running: Reactor Netty, Tomcat, or another runtime. With WebFlux + Reactor Netty, logs usually mention Netty web server startup, though exact log names vary by Spring Boot version. Also check `WebApplicationType` and the dependency tree if you suspect MVC was selected unintentionally.

Command:

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

Verify that `spring-boot-starter-webflux` and `spring-boot-starter-reactor-netty` are present; check for `spring-boot-starter-web` if the application is not running on the expected stack.

### 18.2 Selective Debug Logging

~~~properties
logging.level.org.springframework.web.server.adapter.HttpWebHandlerAdapter=DEBUG
logging.level.org.springframework.web.reactive.DispatcherHandler=TRACE
logging.level.org.springframework.web.reactive.result.method.annotation=DEBUG
logging.level.reactor.netty.http.server=INFO
~~~

Exact loggers and output volume depend on version. Do not enable full request/response wiretap in production without data-protection measures. `TRACE` can increase overhead and expose URL metadata; scrub sensitive tokens and query strings before sharing logs.

When you need to inspect auto-configuration:

~~~bash
gradle bootRun --args='--debug'
~~~

Read the Condition Evaluation Report for the reactive web server and WebFlux instead of guessing from Reactor being on the classpath.

### 18.3 Suggested Breakpoints

If your IDE has the matching Spring Framework 6.1.x and Reactor Netty sources, you can set breakpoints at these observation points:

~~~text
ReactorHttpHandlerAdapter.apply(...)
HttpWebHandlerAdapter.handle(...)
FilteringWebHandler.handle(...)
ExceptionHandlingWebHandler.handle(...)
DispatcherHandler.handle(...)
DispatcherHandler.handleResult(...)
RequestMappingHandlerAdapter.handle(...)
HandlerFunctionAdapter.handle(...)
ResponseBodyResultHandler.handleResult(...)
ServerResponseResultHandler.handleResult(...)
~~~

Exact method names or overloads can differ across patch versions; check the actual implementation before setting breakpoints. The goal is to trace:

- What headers/path does the incoming server request have?
- When is `ServerWebExchange` created?
- Which filters run, and do any short-circuit?
- Does mapping select a `HandlerMethod` or a `HandlerFunction`?
- Does the adapter invoke the controller/function successfully?
- Has the result handler written the status/body yet?
- Did an error occur before or after commit?

### 18.4 Observing via Headers and Correlation IDs

This hands-on exercise uses `X-Flow: webfilter` to prove requests pass through the filter. In production, use tracing/observability that manages correlation IDs rather than logging full request bodies or tokens.

You can store an attribute in the exchange:

~~~java
exchange.getAttributes().put("flow.stage", "filter");
return chain.filter(exchange);
~~~

This snippet sits inside a `WebFilter` that has `exchange` and `chain` in scope. Attributes are scoped to the logical request, not global shared state; avoid storing request data in mutable static fields.

## 19. Common Mistakes

### Mistake 1: Manually calling `subscribe()` in a WebFilter

~~~java
// Do not do this:
chain.filter(exchange).subscribe();
return Mono.empty();
~~~

The server does not properly wait for the publisher, error/cancellation propagation can disconnect from the request lifecycle, and response commit can race.

### Mistake 2: Using HttpHandler as a Business Controller API

`HttpHandler` is low-level. Using `RouterFunction`, `@RestController`, or `WebFilter` is usually right and far less risky. Only replace `HttpHandler` when genuinely building framework or server integration.

### Mistake 3: Equating WebHandler with DispatcherHandler

`DispatcherHandler` is an important `WebHandler` implementation, but `WebHandler` is a general interface; the chain also contains wrappers for filtering and exception handling. An application can configure a different `WebHandler` for specialized use cases.

### Mistake 4: Calling HttpWebHandlerAdapter the same as ReactorHttpHandlerAdapter

The first converts **HttpHandler ↔ WebHandler/ServerWebExchange**; the second converts **Reactor Netty objects ↔ Spring HttpHandler**. They do not perform the same job.

### Mistake 5: Believing `Mono<Void>` Means an Empty Body

`Mono<Void>` primarily marks completion of processing. The body may be written in multiple chunks via another `Flux<DataBuffer>`.

### Mistake 6: Blocking the Event Loop

Using `.block()`, `Thread.sleep`, or synchronous JDBC on the Netty event loop can stall other requests. Use an appropriate reactive driver or properly isolate blocking work.

### Mistake 7: Enabling Full Payload Logging in a Filter

The request body is a stream with lifecycle rules and pooled buffers; reading and replaying the body incorrectly can leave the controller with an empty body or leak memory. Never log tokens, cookies, or sensitive data.

### Mistake 8: Assuming HTTP 404 Means the Server Is Down

404 can come from `DispatcherHandler` having no matching mapping even though the server and `HttpHandler` are already running. Check routes and `WebFilter`s before investigating ports.

### Mistake 9: Returning Error JSON After the Response Has Committed

A streaming response may already have sent headers. An error handler cannot arbitrarily rewrite status or body past that point; log the error and handle network termination appropriately.

### Mistake 10: Trying to "Improve Performance" by Increasing Threads Indefinitely

There is no universally optimal event-loop thread count or queue size. Measure throughput, p95/p99 latency, blocking, allocations, and connection behavior before tuning.

## 20. Diagnostic Checklist

When a WebFlux request does not reach the expected handler, check in order:

1. **Stack:** Is Spring Boot running `REACTIVE`, rather than switched to `SERVLET` by `starter-web`?
2. **Server:** Did Reactor Netty or another reactive server bind the port, and is the client connecting to the right address/port?
3. **Runtime adapter:** Did the server wire the `HttpHandler` properly from the reactive application context?
4. **Exchange:** Did `HttpWebHandlerAdapter` create `ServerWebExchange` with the expected request/path?
5. **WebFilter:** Is a filter short-circuiting, rewriting the path/headers, or returning an error?
6. **Security:** Is the WebFlux security chain allowing the request through?
7. **Mapping:** Which route did `RequestMappingHandlerMapping` or `RouterFunctionMapping` select?
8. **Adapter:** Was the handler invoked by `RequestMappingHandlerAdapter` or `HandlerFunctionAdapter` accordingly?
9. **Body:** Does the request have the right `Content-Type`, does a codec support JSON/stream, and are memory limits sufficient?
10. **Publisher:** Does the handler return a valid `Mono`/`Flux` without manually subscribing or blocking?
11. **Result:** Which `HandlerResultHandler` wrote the response? Were status/headers already committed?
12. **Error:** Was the error handled by `@ExceptionHandler`/`WebExceptionHandler` before commit?
13. **Cancellation:** Did the client disconnect or a proxy timeout occur?
14. **Test:** Verify both annotated controllers and functional routes via `RANDOM_PORT`.

If item 2 fails, resolve server/port/dependencies first. If item 7 fails, do not modify `HttpHandler`; inspect mappings. If items 8–11 fail, inspect argument binding, codecs, reactive `Publisher`s, and result handlers. If errors begin at items 12–13, inspect response commit timing and connection lifecycle.

## 21. Summary

The path of an HTTP request in WebFlux has **two consecutive adapter layers**: a server-layer adapter (such as `ReactorHttpHandlerAdapter`) converts Reactor Netty objects into Spring HTTP abstractions; then `HttpWebHandlerAdapter` turns the `HttpHandler` call into a **ServerWebExchange + WebHandler chain**. Inside, `WebExceptionHandler`s and `WebFilter`s wrap the main `WebHandler`; `DispatcherHandler` uses `HandlerMapping`, `HandlerAdapter`, and `HandlerResultHandler` to map, invoke, and write the result of a controller or functional handler.

**Invariants to remember:** `HttpHandler` receives `ServerHttpRequest`/`ServerHttpResponse`; `WebHandler` receives `ServerWebExchange`; both return `Mono<Void>` to represent processing completion. Creating a `Publisher`, subscribing, I/O, and committing the response are distinct phases. Understanding these boundaries lets you debug request routing, middleware, body decoding, streaming, and post-commit errors accurately.

## 22. References

- Spring Framework 6.1 — WebHttpHandlerBuilder Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html
- Spring Framework 6.1 — ReactorHttpHandlerAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ReactorHttpHandlerAdapter.html
- Spring Framework 6.1 — HttpHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/HttpHandler.html
- Spring Framework 6.1 — WebHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebHandler.html
- Spring Framework — WebFlux Reactive Core / WebHandler API: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — WebFlux DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
- Spring Framework — Functional Endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Reactor Netty — HTTP Server: https://projectreactor.io/docs/netty/release/reference/http-server.html
