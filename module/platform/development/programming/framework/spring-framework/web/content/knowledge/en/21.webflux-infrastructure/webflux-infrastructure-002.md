# DispatcherHandler, HandlerMapping, HandlerAdapter, and HandlerResultHandler in Spring WebFlux

## 1. Learning objectives

Spring WebFlux uses the **front controller** architecture: an HTTP request passes through the reactive infrastructure and is routed to a central coordinator, `DispatcherHandler`. The Dispatcher does not need to understand every controller/route style or how to write JSON/HTML directly. Instead, it coordinates three SPI groups: `HandlerMapping` **finds the handler**, `HandlerAdapter` **invokes the handler**, and `HandlerResultHandler` **processes the result to produce the response**.

This is a foundational lesson in the **WebFlux Infrastructure** section, targeting **Java 17+, Spring Framework 6.x, and Spring Boot 3.x**. Specific objectives:

- Trace the exact pipeline from the HTTP server/`HttpHandler` through `WebFilter`, `DispatcherHandler`, and out to the response.
- Distinguish `WebHandler`, `HandlerMapping`, `HandlerAdapter`, `HandlerResult`, and `HandlerResultHandler`; understand what the word "Handler" means in each name.
- Explain the *first matching mapping → supporting adapter → supporting result handler* algorithm and its priority ordering.
- Recognize annotated controllers (`@RestController`, `@GetMapping`, `ResponseEntity`) versus functional routes (`RouterFunction`, `HandlerFunction`, `ServerResponse`).
- Understand why JSON bodies, statuses, headers, and view rendering go through different result handlers.
- Understand how `Mono<Void>` completes the HTTP response, who subscribes to `Mono/Flux`, and error handling before/after response commit.
- Build a small Boot WebFlux app running both routing models, observe `WebFilter`, print the SPI bean list, and test with `curl` and `WebTestClient`.
- Avoid arbitrarily overriding default SPIs, misusing `@Order`, blocking the event loop, or confusing `DispatcherHandler` with Spring MVC's `DispatcherServlet`.

**Scope:** this is the **WebFlux reactive stack**, not Servlet MVC. Classes with similar names exist in Spring MVC in different packages with different return types; do not copy an MVC interceptor/adapter into WebFlux.

## 2. Overall diagram of an HTTP request

```text
Client / HTTP request
         |
         v
Reactor Netty (or appropriate reactive server adapter)
         |
         v
HttpHandler / HttpWebHandlerAdapter
         |
         v
WebExceptionHandler chain / WebFilter chain
         |
         v
DispatcherHandler             (central WebHandler, bean "webHandler")
         |
         +--> HandlerMapping #1 --no match--+
         +--> HandlerMapping #2 --match----> handler object
         |                                    |
         |                                    v
         +--------------------------> supporting HandlerAdapter
                                              |
                                              v
                                         Mono<HandlerResult>
                                              |
                                              v
                                     supporting HandlerResultHandler
                                              |
                               +--------------+---------------+
                               |                              |
                         JSON / HTTP body                HTML view / other
                               |                              |
                               +--------------+---------------+
                                              |
                                              v
                                       Mono<Void> completes
                                              |
                                              v
                                         HTTP response
```

This diagram is a logical model, **not a separate thread/transaction at each arrow**. All stages can return a `Mono`; actual execution begins when the HTTP infrastructure subscribes to the reactive chain. The response writer may emit multiple `DataBuffer`s/events and encounter backpressure or cancellation when the client disconnects.

### One-sentence roles

| Component | One-sentence explanation |
| --- | --- |
| `DispatcherHandler` | Coordinates the pipeline to select the handler, invoke it, and choose how to write the result |
| `HandlerMapping` | "Which handler object is this request meant for?" |
| `HandlerAdapter` | "How do I invoke a handler object of this type?" |
| `HandlerResult` | Wraps the return value along with metadata needed to process the result |
| `HandlerResultHandler` | "How should this result be written into an HTTP response?" |

**Two different meanings of "handler":** *HandlerAdapter* invokes the discovered **request handler**; *HandlerResultHandler* processes the **return value** of that invocation. One group cannot replace the other.

## 3. Where do the HTTP server, HttpHandler, and WebHandler sit?

WebFlux separates the server transport abstraction from the web application:

- `org.springframework.http.server.reactive.HttpHandler` is the HTTP-server-level contract handling `ServerHttpRequest` and `ServerHttpResponse`, returning `Mono<Void>`.
- `org.springframework.web.server.WebHandler` is the web-application-level contract handling `ServerWebExchange`, returning `Mono<Void>`.
- `ServerWebExchange` wraps request/response plus attributes, session, principal, locale, form/multipart access, and processing state.
- `HttpWebHandlerAdapter` is one of the classes bridging the HTTP server adapter and the `WebHandler` pipeline.
- `WebHttpHandlerBuilder.applicationContext(...)` can discover `WebFilter`, `WebExceptionHandler`, and the `WebHandler` named `webHandler` to build the chain.
- `DispatcherHandler` is a central implementation of `WebHandler`; Spring WebFlux configuration/Boot registers it by default.

Conceptual signature examples:

```java
// Built-in Spring APIs, DO NOT recreate them.
Mono<Void> HttpHandler.handle(
    ServerHttpRequest request,
    ServerHttpResponse response);

Mono<Void> WebHandler.handle(ServerWebExchange exchange);
```

These are **illustrative signatures**, not valid Java source to drop straight into a project. The real interfaces live in the Spring libraries.

**Important point:** `WebFilter` usually runs **around** the dispatcher and can intercept both annotated and functional routes. A functional `HandlerFilterFunction`, on the other hand, wraps the `HandlerFunction`s of a specific router; their scopes differ.

## 4. DispatcherHandler: the reactive front controller

`org.springframework.web.reactive.DispatcherHandler` holds the general algorithm for request routing and response processing. It discovers SPI beans from the `ApplicationContext`:

1. List of `HandlerMapping`s.
2. List of `HandlerAdapter`s.
3. List of `HandlerResultHandler`s.

Ordered beans (`Ordered` or `@Order`) can be prioritized according to configuration. `DispatcherHandler` is a Spring bean; in standard configurations it is named `webHandler` so `WebHttpHandlerBuilder` recognizes it.

### Simplified algorithm

```text
handle(exchange):
  handler = first HandlerMapping that produces a handler
  if no handler:
      signal response status 404 / error pathway as configured
  else:
      adapter = first HandlerAdapter where supports(handler) is true
      result = adapter.handle(exchange, handler)
      if result emitted:
          resultHandler = first handler where supports(result) is true
          resultHandler.handleResult(exchange, result) -> Mono<Void>
      if adapter completes empty:
          response may already be fully handled
  finish on completion/error/cancel
```

This is **pseudocode**, not line-by-line internal Java implementation. In reality there are also CORS preflight handling, exchange metadata, dispatch exception handling, special no-handler behavior, WebExceptionHandlers, and reactive operator composition.

### Why select only one HandlerMapping?

Mappings are iterated in priority order; the first candidate emitting a handler determines the execution path. An earlier mapping that *errors* because HTTP method/media type conditions do not match may terminate the lookup; do not assume "if an earlier mapping has a problem, always try the next mapping". This differs from trying all routes until one returns 200.

**Do not blindly use @Order to resolve two overlapping endpoints.** Choose non-overlapping paths/predicates, test GET/POST/Accept/Content-Type cases, and audit the actual ordering in the application context.

## 5. HandlerMapping: from request to handler object

The reactive mapping contract looks like:

```java
Mono<Object> getHandler(ServerWebExchange exchange);
```

This is the signature of Spring's `org.springframework.web.reactive.HandlerMapping` interface (excerpted for study). `Mono.empty()` generally means this mapping found no matching handler; it does not have to produce an HTTP response itself. An error signal may be emitted when the request fails conditions, depending on the implementation.

Important implementations:

| Mapping | Characteristics | Selected handler object |
| --- | --- | --- |
| `RequestMappingHandlerMapping` | Scans `@RequestMapping`, `@GetMapping`, `@PostMapping` on annotated controllers | `HandlerMethod` representing the mapped Java method |
| `RouterFunctionMapping` | Scans `RouterFunction<?>` beans, combining functional routes | `HandlerFunction<?>` |
| `SimpleUrlHandlerMapping` | Maps URL patterns directly to registered handler objects | For example, a `WebHandler` |
| Resource mappings | Serves static resources per WebFlux config | Appropriate handler for resource infrastructure |

**Do not equate HandlerMapping with plain URL string comparison.** Annotated mappings also check HTTP method, path variables, query params, headers, `consumes`, `produces`, content negotiation, and other specific conditions.

### 5.1. Annotated request mapping

```java
@RestController
@RequestMapping("/api")
class ExampleController {

    @GetMapping(path = "/products/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<ProductDto> one(@PathVariable String id) {
        return service.find(id);
    }
}
```

This is a **snippet** requiring `service`/`ProductDto` and imports. `RequestMappingHandlerMapping` detects the annotations and builds mapping metadata for the method. When `GET /api/products/42` arrives, the handler object is a `HandlerMethod`, not `Mono<ProductDto>` directly.

### 5.2. Functional route mapping

```java
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route()
        .GET("/fn/ping",
             request -> ServerResponse.ok().bodyValue("pong"))
        .build();
}
```

This is a **snippet** inside a `@Configuration` class with imports. `RouterFunctionMapping` finds the `RouterFunction` and selects a `HandlerFunction`; functional routes do not need `@RestController`. For the invocation to produce an HTTP response, the pipeline also uses `HandlerFunctionAdapter` and `ServerResponseResultHandler`.

### 5.3. HandlerMapping ordering

A system having both annotated and functional routes works because each style has its corresponding mapping. If two different mappings match the **same URL/method**, the outcome may depend on mapping order. Never assert "functional always takes precedence over annotated" or vice versa across all Spring versions/configurations. The safe approach: use non-overlapping paths, verify with tests, and intervene in ordering only when genuinely needed at the infrastructure level.

## 6. HandlerAdapter: invoking a handler regardless of type

The `org.springframework.web.reactive.HandlerAdapter` interface has two core operations:

```java
boolean supports(Object handler);

Mono<HandlerResult> handle(
        ServerWebExchange exchange, Object handler);
```

These are **illustrative signatures**, not a standalone compilable class. `supports` decides whether the adapter understands that handler object. `handle` invokes the handler and supplies a `Mono<HandlerResult>` to the dispatcher.

Typical adapters:

- `RequestMappingHandlerAdapter`: invokes a `HandlerMethod` in an annotated controller; resolves `@PathVariable`, `@RequestParam`, `@RequestBody`, validation, return values, and exception-handling metadata.
- `HandlerFunctionAdapter`: invokes a functional `HandlerFunction<ServerResponse>` with an appropriate `ServerRequest`.
- `SimpleHandlerAdapter`: supports simple `WebHandler`-style handlers.

### Controller invocation is not response serialization

Example annotated method:

```java
@GetMapping("/data")
Mono<MyDto> data() {
    return service.load();
}
```

`RequestMappingHandlerAdapter` calls the method and receives the return value (here `Mono<MyDto>`) along with metadata inside `HandlerResult`; the adapter **is not always the final component that sends JSON itself**. `ResponseBodyResultHandler`, HTTP message writers/codecs, and the response layer are responsible for serialization/writing.

An adapter can also handle the entire request itself and complete with `Mono.empty()` in supported scenarios; do not build middleware assuming a `HandlerResult` is always emitted.

## 7. HandlerResult: a result that is not yet HTTP bytes

`org.springframework.web.reactive.HandlerResult` wraps:

- **Handler** that produced the result.
- **Return value** (either a regular object or a reactive wrapper).
- **Return type metadata** such as `MethodParameter`/`ResolvableType` to decide how to process it.
- **Model** if applicable for view rendering.
- **Exception handling** reference depending on the adapter, e.g. `DispatchExceptionHandler` for deferred errors.

For a controller:

```java
@GetMapping("/users/{id}")
Mono<ResponseEntity<UserDto>> user(@PathVariable long id) {
    return userService.find(id)
        .map(ResponseEntity::ok);
}
```

This is a snippet with `userService`/`UserDto`. The adapter can return a `HandlerResult` holding a reactive value declared as `Mono<ResponseEntity<UserDto>>` and return type metadata. **Do not think each `onNext` from Mongo/DB creates a new HandlerResult**: HandlerResult is the outcome of invoking the handler, while the Publisher inside it is the source of values consumed by the result handler to write the body.

`HandlerResult` is not WebFlux.fn's `ServerResponse`. `ServerResponse` is a kind of **return value** that can sit inside `HandlerResult` to be handled by `ServerResponseResultHandler`.

## 8. HandlerResultHandler: turning a result into an HTTP response

The Spring `org.springframework.web.reactive.HandlerResultHandler` contract:

```java
boolean supports(HandlerResult result);

Mono<Void> handleResult(
        ServerWebExchange exchange, HandlerResult result);
```

`supports` confirms it can process the return value + metadata, and `handleResult` updates status/headers, picks a body writer or view, and completes the reactive operation. `Mono<Void>` represents when response writing finishes, **not** a mandatory empty body.

Spring WebFlux 6.x configuration provides these main handlers:

| Result handler | Supported values | Default order documented by Spring |
| --- | --- | --- |
| `ResponseEntityResultHandler` | `ResponseEntity` from annotated controllers | **0** |
| `ServerResponseResultHandler` | `ServerResponse` from functional endpoints | **0** |
| `ResponseBodyResultHandler` | `@ResponseBody` / `@RestController` ordinary body | **100** |
| `ViewResolutionResultHandler` | View name, `View`, model, `Rendering`, ... | **Integer.MAX_VALUE** |

Two result handlers having the same order 0 does **not** mean they compete for the same value. Each handler uses `supports(...)` to match its exact contract. Do not override ordering to force every `Mono<Dto>` through `ResponseEntityResultHandler`.

### 8.1. ResponseEntityResultHandler

An annotated method returns:

```java
@GetMapping("/accepted")
Mono<ResponseEntity<Message>> accepted() {
    return Mono.just(ResponseEntity.accepted()
        .header("X-Example", "yes")
        .body(new Message("queued")));
}
```

Snippet assuming `Message` record/imports exist. `ResponseEntityResultHandler` processes status **202**, header metadata, and the `Message` body via a message writer. It does not turn 202 into "the job has already executed"; that is application semantics.

### 8.2. ResponseBodyResultHandler

A `@RestController` returning `Mono<Message>` or `Flux<Message>` is handled according to `@ResponseBody` semantics. For `application/json`, an appropriate message writer/codec (usually Jackson) encodes the DTO. For `text/event-stream`, a streaming codec is used; do not equate one Reactor element with one TCP packet.

### 8.3. ServerResponseResultHandler

A functional `HandlerFunction` returns `Mono<ServerResponse>`. The result handler receives `ServerResponse` and invokes its `writeTo(...)` logic, utilizing appropriate message writers/handler strategies. Do not force an annotated controller to return `ServerResponse` just because both are called "response"; that is WebFlux.fn's own contract.

### 8.4. ViewResolutionResultHandler

When an annotated `@Controller` returns a logical view name and a view resolver engine is configured, the handler can render HTML (Thymeleaf/Freemarker depending on dependencies/config). Without a view technology, do not assume templates always render. If the method has `@ResponseBody`, a `String` is normally an **HTTP response body**, not a view name.

## 9. Four paths on the same DispatcherHandler

```text
GET /api/hello/Ana
  RequestMappingHandlerMapping -> HandlerMethod
  RequestMappingHandlerAdapter -> HandlerResult(Mono<Greeting>)
  ResponseBodyResultHandler -> 200 JSON

GET /api/status
  RequestMappingHandlerMapping -> HandlerMethod
  RequestMappingHandlerAdapter -> HandlerResult(Mono<ResponseEntity<Greeting>>)
  ResponseEntityResultHandler -> 202 JSON

GET /fn/hello/Ana
  RouterFunctionMapping -> HandlerFunction
  HandlerFunctionAdapter -> HandlerResult(Mono<ServerResponse>)
  ServerResponseResultHandler -> 200 JSON

GET /pages/home   (when view template config is present)
  RequestMappingHandlerMapping -> HandlerMethod
  RequestMappingHandlerAdapter -> HandlerResult("home")
  ViewResolutionResultHandler -> rendered HTML
```

The diagram illustrates the flows **according to standard contracts**, not traces captured from a live app. Steps like annotation metadata, content negotiation, and response writing involve additional internal steps. The goal is to show that Dispatcher **does not change its algorithm** even though results are handled by different result handlers.

## 10. Message readers, writers, and content negotiation

`HandlerAdapter` needs to read/bind parameters/bodies; `HandlerResultHandler` often needs to pick how to write the response. In WebFlux, the codec infrastructure consists of `HttpMessageReader`, `HttpMessageWriter`, and `ServerCodecConfigurer`.

- Request `Content-Type` states what body type the client is sending. An endpoint with `consumes="application/json"` can reject with **415 Unsupported Media Type** if the client sends an unsupported type.
- `Accept` states what representation the client accepts. An endpoint returning only JSON can reject with **406 Not Acceptable** when no compatible representation exists.
- `produces` in an annotation/request predicate is a routing condition; a message writer must also support encoding that data type/format.
- Reading a `Mono<Dto>` request body requires a matching decoder; malformed JSON can produce **400 Bad Request**.
- `@ResponseBody` + String does not become a view; `@Controller` + String is not a raw body by default.
- Server-Sent Events and NDJSON have different streaming semantics from a regular JSON array and require the proper media type configuration.

**Do not write a new HandlerResultHandler just to add a field to a JSON DTO.** If your need is validation/serialization, look at Jackson, controller advice, `CodecCustomizer`, WebFlux config, or message writers before writing a custom SPI.

## 11. Reactive response completion and backpressure

Although class names resemble Spring MVC, WebFlux uses reactive types:

```text
Adapter.handle(...)          -> Mono<HandlerResult>
ResultHandler.handleResult() -> Mono<Void>
Response body Publisher      -> Mono<T> / Flux<T>
```

Common points of confusion:

- `Mono<HandlerResult>` does not guarantee synchronous execution: the handler may read the body or run async work to produce the result.
- `Mono<Void>` completes when the corresponding response-writing work finishes/is handled; it does not mean the response body is always empty.
- The HTTP infrastructure subscribes to the Publisher produced by the request chain; **controllers never call `subscribe()` themselves** to make the result handler run.
- A stream can be **canceled** when the HTTP client disconnects; resource cleanup must handle complete/error/cancel.
- A result handler may invoke codecs and coordinate flow control; `onNext` does not necessarily correspond to a single TCP write.
- Once the response has committed headers/body, there is no guarantee you can convert a late stream error into a fresh JSON error body with a different status.

**Simply returning Flux/Mono is not enough to make everything non-blocking.** If a controller calls blocking JDBC before returning a Mono or uses `block()` on the Netty event loop, it can cause thread starvation/errors. Use reactive drivers or offload legacy blocking work to a bounded scheduler with capacity management.

## 12. Error handling across layers

Not every error occurs in the same place. Distinguish them:

| Stage | Example | Typical handling mechanism |
| --- | --- | --- |
| `WebFilter` before dispatcher | Authentication/rate/error | Security filter, `WebExceptionHandler` |
| `HandlerMapping` | No route, wrong method, mismatched predicates | Not-found/status exception or mapping error per config |
| `HandlerAdapter` during binding | Wrong query type, malformed JSON body, validation | Annotated controller exception resolver or WebExceptionHandler |
| Reactive business logic | `Mono.error(ex)` from service | `@ExceptionHandler`/`@ControllerAdvice` where applicable |
| Result handling | Missing codec, serialization failure, missing view | Exception handling before commit if feasible |
| After response commit | Streaming error/client disconnect | Cleanup/metrics, usually cannot change already-sent status |

Spring Framework 6.x has `DispatchExceptionHandler` to assist turning a `Throwable` into a `HandlerResult` in certain situations. `RequestMappingHandlerAdapter` supports annotated controller exception handling; `HandlerResult` can carry an exception handler used for **deferred errors** or errors during result rendering.

At the web chain level, `WebExceptionHandler` handles errors from filters/target handlers; Spring Boot also provides auto-configured error handling. **`@RestControllerAdvice` does not catch every exception before/outside the dispatcher** and cannot intervene after bytes have been sent to the client.

### No mapping and HTTP status

A non-existent route normally yields 404. However:

- Matching path with an unsupported HTTP method can yield **405 Method Not Allowed**.
- A `consumes` mismatch can yield 415.
- A `produces`/Accept mismatch can yield 406.
- A security filter can return 401/403 before mapping.
- Custom error handlers/proxies can alter the body or status.

Therefore, do not assume every request that misses the controller is a 404 or every 404 comes from a specific `HandlerMapping`.

## 13. How does WebFilter differ from HandlerMapping and ControllerAdvice?

A `WebFilter` has the contract:

```java
Mono<Void> filter(
    ServerWebExchange exchange, WebFilterChain chain);
```

This is the Spring interface signature, not complete class code. It can run logic before/after `chain.filter(exchange)`, add response headers, extract correlation IDs, establish context, or reject requests early.

| Tool | Scope | Best used for |
| --- | --- | --- |
| `WebFilter` | Wraps requests processed through the WebHandler pipeline | Authn/authz in Spring Security, tracing, request metrics |
| `HandlerMapping` | Finds endpoint/handler for a request | Annotation routes, functional routes, custom routing |
| `HandlerAdapter` | Invokes a kind of handler object | Extending programming models |
| `HandlerResultHandler` | Processes return values | HTTP body/result/view strategy |
| `@RestControllerAdvice` | Exception/binding responses for the annotated controller model | Domain/validation error mapping |
| `WebExceptionHandler` | Errors across the WebFilter/WebHandler chain | Errors outside annotated methods or infrastructure |
| Functional `HandlerFilterFunction` | Wraps handler functions belonging to a router | Shared logic for a group of functional routes |

A `WebFilter` can set a header before a route is chosen; it is **not** a HandlerMapping. If a WebFilter rejects a request and completes the response itself, DispatcherHandler may never be invoked.

## 14. WebFlux config and SPI extensibility

In normal projects, **letting Spring Boot and WebFlux Config create the default SPIs** is the best choice. Typical customization entrypoints are:

- `WebFluxConfigurer` (configuring formatters, codecs, CORS, view resolvers, resource handlers...).
- Custom `WebFilter` for cross-cutting logic in the request chain.
- `RouterFunction<ServerResponse>` beans or annotated `@RestController`s for business routes.
- Global exception handling, codecs, validation, and functional filters.
- Custom implementations of `HandlerMapping`, `HandlerAdapter`, or `HandlerResultHandler` **only when introducing a genuinely new programming model**.

**Do not blindly add `@EnableWebFlux` in Spring Boot and expect Boot autoconfiguration to continue working identically.** When taking over WebFlux configuration manually, some Boot conveniences may change or no longer apply in the same way; consult the current Boot version docs. The runnable example below **does not use `@EnableWebFlux`**.

An adapter that accepts every `Object` or a result handler whose `supports(...) == true` with very high priority can hijack requests/results from standard components. If you need a custom SPI, write `supports` **strictly**, choose order deliberately, verify coexistence with annotated and functional routes, and test no-match cases.

## 15. Runnable Spring Boot 3 Java 17+ project

Create a Maven project from Spring Initializr with **Java 17+**, Spring Boot **3.x**, and dependencies:

- `spring-boot-starter-webflux`.
- `spring-boot-starter-test` (test scope).
- `io.projectreactor:reactor-test` (test scope if the test starter version used does not already pull it in).

**Do not add `spring-boot-starter-web`** if you want Boot to automatically select the reactive WebFlux server application type when both starters are present. If both MVC and WebFlux are present, Boot usually prefers MVC unless application type is explicitly configured. This project uses pure WebFlux.

Source structure:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  ApiController.java
  FunctionalRoutes.java
  TraceWebFilter.java
  PipelineInspector.java
src/test/java/com/example/demo/
  PipelineHttpTest.java
```

Put all files in package `com.example.demo`. No database, security, or template engine is needed. Once running, WebFlux will serve both annotated routes `/api/*` and functional route `/fn/*`, avoiding URL overlap for deterministic tests.

### 15.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 15.2. ApiController.java

```java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping(path = "/hello/{name}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Greeting> hello(@PathVariable String name) {
        return Mono.just(new Greeting("annotated", name));
    }

    @GetMapping(path = "/status",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Greeting>> status() {
        return Mono.just(ResponseEntity.status(
                HttpStatus.ACCEPTED)
            .body(new Greeting("responseEntity", "ok")));
    }

    @GetMapping(path = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Greeting> events() {
        return Flux.range(1, 3)
            .map(i -> new Greeting("event", Integer.toString(i)))
            .delayElements(Duration.ofMillis(60));
    }

    @GetMapping("/missing")
    public Mono<Greeting> missing() {
        return Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "not found"));
    }

    public record Greeting(String style, String name) {}
}
```

Endpoints:

- `/api/hello/{name}`: annotated route returning `Mono<Greeting>`; `ResponseBodyResultHandler` and the JSON writer handle the result.
- `/api/status`: annotated route returning `Mono<ResponseEntity<Greeting>>`; `ResponseEntityResultHandler` handles 202 and the JSON body.
- `/api/events`: annotated route returning `Flux<Greeting>` with `text/event-stream`; the body writer emits SSE.
- `/api/missing`: emits an error before response commit; `ResponseStatusException` leads to 404 per standard error handling.

The controller does not call `subscribe()` or `block()`. The Mono/Flux operators are synchronous/lazy/scheduled according to each operator; the framework manages subscription and the response writing lifecycle. `delayElements` does not promise an exact 60ms interval under heavy load.

### 15.3. FunctionalRoutes.java

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class FunctionalRoutes {

    @Bean
    public RouterFunction<ServerResponse> greetingRoutes() {
        return RouterFunctions.route()
            .GET("/fn/hello/{name}", request ->
                ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(new ApiController.Greeting(
                        "functional", request.pathVariable("name"))))
            .build();
    }
}
```

Do not use `@RestController` for functional routes. `RouterFunctionMapping` selects the `HandlerFunction`, `HandlerFunctionAdapter` invokes the lambda, and `ServerResponseResultHandler` writes `ServerResponse`. Functional `ServerResponse.ok().bodyValue(...)` builds `Mono<ServerResponse>` per contract; the handler function does not write bytes manually.

### 15.4. TraceWebFilter.java

```java
package com.example.demo;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(-100)
public class TraceWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        // Demo: add header before WebFlux writes the response.
        exchange.getResponse().getHeaders()
                .add("X-Pipeline", "webflux");

        return chain.filter(exchange);
    }
}
```

A simple filter applying to both route families. Do not use this header as an authentication/security signal; production tracing needs reliable and sanitized correlation IDs. If a security filter or gateway terminates the request before this filter due to different chain ordering, the header might not appear — do not use it as sole proof that a route executed.

### 15.5. PipelineInspector.java

To **observe the SPI beans created by Boot/WebFlux config**, use an `ApplicationRunner` that prints class names on startup:

```java
package com.example.demo;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerAdapter;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.HandlerResultHandler;

@Component
public class PipelineInspector implements ApplicationRunner {

    private final List<HandlerMapping> mappings;
    private final List<HandlerAdapter> adapters;
    private final List<HandlerResultHandler> resultHandlers;

    public PipelineInspector(
            List<HandlerMapping> mappings,
            List<HandlerAdapter> adapters,
            List<HandlerResultHandler> resultHandlers) {
        this.mappings = mappings;
        this.adapters = adapters;
        this.resultHandlers = resultHandlers;
    }

    @Override
    public void run(ApplicationArguments args) {
        mappings.forEach(x ->
            System.out.println("mapping=" +
                x.getClass().getSimpleName()));

        adapters.forEach(x ->
            System.out.println("adapter=" +
                x.getClass().getSimpleName()));

        resultHandlers.forEach(x ->
            System.out.println("result=" +
                x.getClass().getSimpleName()));
    }
}
```

Output **may** include lines like:

```text
mapping=RequestMappingHandlerMapping
mapping=RouterFunctionMapping
adapter=RequestMappingHandlerAdapter
adapter=HandlerFunctionAdapter
result=ResponseEntityResultHandler
result=ServerResponseResultHandler
result=ResponseBodyResultHandler
```

This is an **example list**, not exhaustive or fixed in bean order/count. Spring version, auto-config, static resources, and other beans can produce additional lines; the list depends on the context. This tool introspects default SPIs and **does not alter `@Order` or override behavior**.

### 15.6. Running the application

Inside the Maven Boot project directory with the wrapper:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

The default server port is typically 8080 if `server.port` is unchanged. Do not compile an individual controller with `javac ApiController.java` without the Spring/Reactor/Jackson classpath; the example is a **Maven application**, not a standalone JDK file.

## 16. curl: each path going through a different result handler

### Annotated route → response body

```bash
curl -i 'http://localhost:8080/api/hello/Ana'
```

Expected:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Pipeline: webflux

{"style":"annotated","name":"Ana"}
```

Other automatic headers, casing, and ordering may vary by web server. `X-Pipeline` is added by the demo filter before the dispatcher; the JSON object is serialized by Jackson.

### ResponseEntity → status/headers/body

```bash
curl -i 'http://localhost:8080/api/status'
```

Expected HTTP **202 Accepted**, body:

```json
{"style":"responseEntity","name":"ok"}
```

A 202 response does not by itself prove a background job was enqueued; the endpoint merely illustrates `ResponseEntityResultHandler` reading the status from `ResponseEntity`.

### Functional route → ServerResponse

```bash
curl -i 'http://localhost:8080/fn/hello/Ana'
```

Expected HTTP **200**:

```json
{"style":"functional","name":"Ana"}
```

This is the `RouterFunctionMapping → HandlerFunctionAdapter → ServerResponseResultHandler` path. Same dispatcher, different set of delegates compared to the annotated route.

### SSE → streaming body writer

```bash
curl -N -i 'http://localhost:8080/api/events'
```

Example body portion:

```text
data:{"style":"event","name":"1"}

data:{"style":"event","name":"2"}

data:{"style":"event","name":"3"}

```

`curl -N` disables buffering in curl to make events easy to observe. Body formatting follows the SSE writer, though flush timing and packet boundaries vary. Do not assert that the third event arrives at exactly 180ms.

### Error status and no-match

```bash
curl -i 'http://localhost:8080/api/missing'
curl -i 'http://localhost:8080/not-found'
```

Both typically return **404**, yet the detection mechanisms differ: `/api/missing` is routed to a method and then emits an error; `/not-found` has no matching handler. Error bodies can differ depending on Spring Boot/problem-details config; do not assert unconfigured JSON details.

## 17. WebTestClient: testing the real HTTP flow

File `src/test/java/com/example/demo/PipelineHttpTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class PipelineHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void annotatedControllerProducesJson() {
        client.get().uri("/api/hello/Ana")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Pipeline", "webflux")
            .expectBody()
            .jsonPath("$.style").isEqualTo("annotated")
            .jsonPath("$.name").isEqualTo("Ana");
    }

    @Test
    void responseEntityControlsStatus() {
        client.get().uri("/api/status")
            .exchange()
            .expectStatus().isAccepted()
            .expectBody()
            .jsonPath("$.style").isEqualTo("responseEntity");
    }

    @Test
    void functionalRouteUsesServerResponse() {
        client.get().uri("/fn/hello/Ana")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Pipeline", "webflux")
            .expectBody()
            .jsonPath("$.style").isEqualTo("functional");
    }

    @Test
    void controllerErrorsAndUnknownRoutesYield404() {
        client.get().uri("/api/missing")
            .exchange().expectStatus().isNotFound();

        client.get().uri("/does-not-exist")
            .exchange().expectStatus().isNotFound();
    }

    @Test
    void streamEmitsThreeEvents() {
        Flux<ApiController.Greeting> events =
            client.get().uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(ApiController.Greeting.class)
                .getResponseBody();

        StepVerifier.create(events)
            .expectNext(new ApiController.Greeting("event", "1"))
            .expectNext(new ApiController.Greeting("event", "2"))
            .expectNext(new ApiController.Greeting("event", "3"))
            .verifyComplete();
    }
}
```

**Test caveat:** WebTestClient uses codecs configured by Spring Test/WebFlux. In some versions/client settings, SSE JSON may need to be decoded via `ServerSentEvent<Greeting>` or an explicit `ParameterizedTypeReference` instead of the DTO directly; adjust the test if the codec does not map directly. Using `returnResult` and `StepVerifier` verifies **stream signals**, not to be confused with TCP chunks. If Spring Security is enabled, mock identity/CSRF or client credentials per test profile; security can block before the handler.

Run:

```bash
./mvnw test
```

On PowerShell:

```powershell
.\mvnw.cmd test
```

This is sample code for a Spring Boot 3 project with matching dependencies, **not a claim that tests have been executed in the user's repository**. When verifying on real Netty/proxies, use `RANDOM_PORT`/HTTP and test through the actual production ingress, not just mock exchanges.

## 18. Pure Java 17: simulating the three responsibilities with fixed stdout

This section **does not simulate Reactor or implement Spring SPIs**; it simply exposes the three responsibilities in standalone Java 17 as a reference when reading the real interfaces.

File `PipelineRolesDemo.java`:

```java
public class PipelineRolesDemo {

    interface Mapping {
        String map(String path);
    }

    interface Adapter {
        String invoke(String handler);
    }

    interface ResultWriter {
        void write(String result);
    }

    public static void main(String[] args) {
        Mapping mapping = path ->
            "/hello".equals(path) ? "helloHandler" : null;

        Adapter adapter = handler ->
            "helloHandler".equals(handler) ? "Hello" : "unknown";

        ResultWriter writer = result ->
            System.out.println("HTTP body: " + result);

        String handler = mapping.map("/hello");
        System.out.println("handler=" + handler);
        String result = adapter.invoke(handler);
        System.out.println("result=" + result);
        writer.write(result);
    }
}
```

Run without Spring:

```bash
javac PipelineRolesDemo.java
java PipelineRolesDemo
```

**Exact** stdout:

```text
handler=helloHandler
result=Hello
HTTP body: Hello
```

This simulation omits `ServerWebExchange`, reactive Publishers, HTTP statuses, codecs, errors, and real SPI contracts. When reading WebFlux code, map from demo interfaces `Mapping/Adapter/ResultWriter` to `HandlerMapping/HandlerAdapter/HandlerResultHandler` with their real signatures and `Mono` return types.

## 19. Advanced routing experiments and priority ordering

If you need to diagnose a route that is not executing:

1. Check which `HandlerMapping` beans exist in the context: whether `RequestMappingHandlerMapping` and `RouterFunctionMapping` are present.
2. Check method, path, headers, consumes/produces, and path variables, not only the URL.
3. Check mapping order (`Ordered`), but do not rely on hardcoded order numbers heard from a different Spring version.
4. If the mapping matches yet the controller is not invoked, check `WebFilter`/Spring Security, CORS preflight, and exceptions before the adapter.
5. If the controller is invoked yet the status/body is wrong, inspect the **return value type** and its corresponding result handler.
6. If the body fails to serialize, inspect media type, codec registration, and DTO/Jackson configuration.
7. If the response is an HTML view instead of a string body, check `@Controller` vs `@RestController`/`@ResponseBody`.
8. If an exception misses `@ExceptionHandler`, determine whether the error occurred in the filter, mapping, adapter, or **after response commit**.
9. Inspect startup logs/mapping introspection and run real HTTP tests before considering a custom SPI.

### Custom HandlerMapping only when a different programming model is needed

A custom mapping implements `HandlerMapping.getHandler(ServerWebExchange)` and returns a handler object, yet **there must be a HandlerAdapter that knows how to invoke that object type**. If you return a custom object that no adapter `supports`, the dispatcher cannot guess how to invoke it.

### Custom HandlerAdapter must return a contract-compliant result

A custom adapter must:

- Implement `supports(Object)` strictly, avoiding swallowing Spring's HandlerMethod/HandlerFunction.
- Return `Mono<HandlerResult>` from `handle(exchange, handler)` or complete empty if it already handled the response itself.
- Never block the event loop on I/O calls.
- Respect cancellation/errors and attach an exception handling strategy where appropriate.
- Have a `HandlerResultHandler` supporting any new return value type if default handlers cannot write it.
- Have tests for both the custom route and **all standard routes** coexisting.

### Custom HandlerResultHandler must be careful with order

A result handler that `supports` everything with `@Order(-1000)` can intercept even `ResponseEntity`/`ServerResponse`, breaking HTTP semantics. If supporting a specialized return type, constrain `supports` by metadata/type and return `Mono<Void>` from the response writer per reactive contract; verify error/commit/backpressure behavior.

**Do not write a custom SPI just to serve an ordinary JSON endpoint.** Annotated controllers or RouterFunctions already cover nearly all standard business HTTP use cases.

## 20. When to choose annotated vs functional endpoints?

| Criterion | Annotated controllers | Functional endpoints |
| --- | --- | --- |
| Entry | `@RestController`/`@RequestMapping` | `RouterFunction`/`HandlerFunction` |
| Mapping | `RequestMappingHandlerMapping` | `RouterFunctionMapping` |
| Adapter | `RequestMappingHandlerAdapter` | `HandlerFunctionAdapter` |
| Result | `ResponseBodyResultHandler`/`ResponseEntityResultHandler`/view... | `ServerResponseResultHandler` |
| Request access | Method args and binding/validation annotations | `ServerRequest` |
| Response | Return DTO/Mono/Flux/ResponseEntity | `Mono<ServerResponse>` |
| Shared concerns | `@ControllerAdvice`, filters, codecs | Router-specific filters, `WebFilter`, codecs |
| Preference | Domain APIs + validation annotations | Centralized routing and functional composition |

You can combine both styles in **one WebFlux app**. Choose based on team/style/testability, not because one style is "more non-blocking" than the other: both use the exact same Reactor/HTTP infrastructure. **Spring MVC functional `RouterFunction` belongs to a different Servlet package than WebFlux.fn**, so ensure exact imports.

## 21. Security, CORS, and processing order

`DispatcherHandler` is not the sole layer responsible for security:

- Spring Security WebFlux uses `SecurityWebFilterChain`/WebFilters to authenticate/authorize requests per policy.
- `WebFilter` can reject before routing, yet route metadata and matcher policies must remain consistent to avoid bypasses.
- CORS preflight has a dedicated handling path; Spring MVC's Servlet `CorsFilter` must not be used as a substitute for WebFlux CORS config.
- Do not allow custom routing based on raw, uncanonicalized client headers/paths that bypass resource authorization checks.
- `@RestControllerAdvice` handles domain errors, **not** replacement for authorization policies in the filter chain.
- Error responses must not expose Java stack traces, internal handler bean names, session tokens, or SQL details.
- Do not turn a default result handler into "send raw HTML" for untrusted data: XSS requires output encoding/content policies.
- WebFlux reactive Context and security context should not be replaced by a hand-rolled ThreadLocal on the Netty event loop.
- For streaming, bound event counts, buffer sizes, and clean up subscriptions on disconnect.

A `WebFilter` writing status/body early can prevent the dispatcher from running; this must be intentional and tested, not mistaken for a HandlerMapping bug if the controller is not called.

## 22. Performance and observability per layer

The WebFlux pipeline is very fast through the default SPIs, and bottlenecks are usually in services/databases/networks or response body writers rather than mapping lookup.

Signals worth measuring:

| Metric / trace | Interpretation |
| --- | --- |
| Request route match / no match | Are route conditions working as intended? |
| 404/405/406/415 | URI, method, Accept/Content-Type, or codec mismatch |
| Controller/service latency | Time spent executing business logic |
| Async body emit / write latency | Backpressure, slow clients, serialization |
| Reactor Netty event-loop blocking | Are JDBC/`block()`/file IO running on the event loop? |
| JSON encode/error rates | DTO, codec, payload shape |
| WebFilter/security failures | Failures before the dispatcher |
| Client cancellations | Connection closed, resource cleanup |
| Memory buffers/queues | Is streaming accumulating without bounds? |
| Exception stage | Mapping, adapter, service, result writing, filter |

For tracing/metrics, propagate the same trace ID across the request (using Reactor Context/proper observability) rather than assuming an HTTP request always stays on one Java thread. Do not log raw Authorization headers, credentials, or private response bodies for debugging.

Printing entire HandlerResult/handler objects into logs can expose data and add overhead; the startup inspector should only print class names, and production can omit/limit such logs.

## 23. Comparison table with Spring MVC

| Feature | Spring WebFlux | Spring MVC |
| --- | --- | --- |
| Front controller | `DispatcherHandler` | `DispatcherServlet` |
| Core API | `WebHandler`, `ServerWebExchange`, `Mono<Void>` | `HttpServletRequest`/`HttpServletResponse` and Servlet dispatch |
| Mapping SPI | `org.springframework.web.reactive.HandlerMapping` | `org.springframework.web.servlet.HandlerMapping` |
| Adapter SPI | `org.springframework.web.reactive.HandlerAdapter` | `org.springframework.web.servlet.HandlerAdapter` |
| Result handling | `HandlerResultHandler` with `Mono<Void>` | MVC return-value handling/message converters/view resolvers |
| HTTP server | Reactor Netty or reactive adapters | Servlet container |
| Programming models | Annotated + WebFlux.fn | Annotated + MVC.fn |
| I/O model | Reactive/non-blocking end-to-end if dependencies support it | Servlet request model (with async support) |

Spring MVC also supports `@Controller`, `@RestController`, `ResponseEntity`, and reactive return values in certain scenarios. Therefore, identical annotation names **do not prove an app is running WebFlux**. Check dependencies, Boot `WebApplicationType`, actual server, and packages.

## 24. Common anti-patterns

1. **Confusing DispatcherHandler with DispatcherServlet**: different stacks and packages.
2. **Thinking DispatcherHandler invokes every controller method directly via reflection without an adapter**.
3. **Thinking HandlerMapping both finds and writes JSON**: mapping only finds the handler.
4. **Thinking HandlerAdapter is synonymous with HandlerResultHandler**.
5. **Thinking HandlerResult is already written body bytes**: it still holds return type/metadata and requires a writer.
6. **Thinking shared default order=0 makes ResponseEntity and ServerResponse conflict**: `supports` distinguishes them.
7. **Creating a catch-all custom HandlerResultHandler with very high priority**: breaks default routing/response semantics.
8. **Blindly adding @EnableWebFlux to a Boot app**: can alter Boot customization.
9. **Adding spring-boot-starter-web and assuming the app surely runs the reactive stack**.
10. **Overlapping annotated and functional URLs without checking order**: unpredictable which route wins.
11. **Checking only URL path, forgetting method/consumes/produces/headers**: leads to 405/415/406.
12. **Manually calling subscribe() inside a controller**: loses error/cancel/HTTP lifecycle management.
13. **Calling block() on the event loop**: stalls non-blocking processing.
14. **Returning String from @Controller and assuming it is a raw body**: it can be treated as a view name.
15. **Relying on @RestControllerAdvice to catch every WebFilter exception**: it does not cover every layer.
16. **Trying to write a JSON error after SSE bytes have committed**: status cannot always be changed.
17. **Treating each Flux element as a TCP packet**: codecs/buffering work differently.
18. **Failing to clean up when a client cancels a stream**: memory/connection leaks.
19. **Using a custom mapping with no matching adapter**: Dispatcher cannot invoke it.
20. **Making a custom adapter return supports=true for every Object**: swallows standard handlers.
21. **Not testing body writers against DTO/Accept types**: serialization errors.
22. **Ignoring Spring Security/WebFilter when tracing routing**: requests can be blocked before the dispatcher.
23. **Relying on logged SPI names to assume a fixed runtime order**: order depends on config.
24. **Not distinguishing genuine reactive services from blocking I/O wrapped in Mono**.
25. **Modifying infrastructure because a route failed to match** instead of checking predicates/error stage.
26. **Failing to test both annotated and functional routes in the same app**: regressions after custom config.
27. **Not distinguishing Mono.empty from a handled request vs no-handler**: adapter result and mapping are separate phases.
28. **Treating HTTP status as proof of DB mutation success** when timeouts/cancellations race.
29. **Putting handler logging that leaks user context/headers**: security risk.
30. **Catching every Throwable and returning 200 to suppress error logs**: hides errors and sends wrong data to clients.

## 25. Code review / production checklist

### Routing

- [ ] Does the project actually use the WebFlux starter/application type, not MVC by mistake?
- [ ] Is `DispatcherHandler` managed by WebFlux config/Boot, with no accidental duplicate bean?
- [ ] Are `HandlerMapping`s right for annotated and functional endpoints?
- [ ] Are routes free of unintended overlaps, with clear method/headers/consumes/produces predicates?
- [ ] Do custom mappings have tested ordering and no-match semantics?
- [ ] Are Security/CORS checked before or alongside routes per policy?

### Invocation and return values

- [ ] Does `HandlerAdapter` match the handler type emitted by the mapping?
- [ ] Do handler methods avoid blocking the event loop with JDBC/`block()`/sleep?
- [ ] Does `HandlerResultHandler` handle ResponseEntity, body DTO, ServerResponse, and views correctly?
- [ ] Do JSON codecs/HTTP message writers support the DTO/media type?
- [ ] Are controllers free of manual `subscribe()` calls?
- [ ] Does streaming handle backpressure/cancellation/cleanup properly?
- [ ] Are errors before vs after response commit clearly distinguished?

### Validation / operation

- [ ] Do `curl`/`WebTestClient` test both annotated and functional paths?
- [ ] Are 202 ResponseEntity/status and 200 functional JSON tested?
- [ ] Are 404 no-route vs 404 from handler, and 405/406/415 tested where applicable?
- [ ] Are WebFilter pre-dispatcher behavior and out-of-controller errors tested where needed?
- [ ] Are SSE/stream completion and client disconnect tested over real HTTP?
- [ ] Are metrics in place for routing/errors/codecs/serialization/event-loop blocking?
- [ ] Are `@EnableWebFlux`/custom SPIs avoided in Boot without integration tests?

## 26. Self-check questions

**1.** What is the primary job of DispatcherHandler?

**Answer:** It is the WebFlux front controller coordinating HandlerMapping to pick the request handler, HandlerAdapter to invoke it, and HandlerResultHandler to write the result into an HTTP response.

**2.** What object does HandlerMapping return for an annotated controller?

**Answer:** Typically a `HandlerMethod` representing the matched Java controller method, not JSON or a DTO.

**3.** Why does DispatcherHandler need HandlerAdapter?

**Answer:** Handler objects come in multiple kinds such as HandlerMethod, HandlerFunction, and WebHandler; the adapter hides the invocation details of each kind.

**4.** What type does `HandlerAdapter.handle(...)` return?

**Answer:** `Mono<HandlerResult>`, or it may complete empty when the request has already been handled per contract.

**5.** What type does `HandlerResultHandler.handleResult(...)` return?

**Answer:** `Mono<Void>` representing the reactive operation completing response processing, not implying an empty body.

**6.** Which result handlers do two endpoints returning `Mono<Greeting>` and `Mono<ResponseEntity<Greeting>>` normally go through?

**Answer:** `ResponseBodyResultHandler` for ordinary `@ResponseBody`, and `ResponseEntityResultHandler` for ResponseEntity.

**7.** Which adapter/result handler does a functional RouterFunction use?

**Answer:** `HandlerFunctionAdapter` and `ServerResponseResultHandler` after `RouterFunctionMapping`.

**8.** If the result handlers for ServerResponse and ResponseEntity both have order 0, how is it resolved?

**Answer:** `supports(result)` distinguishes the type/metadata; they do not compete for every result just because they share the same order.

**9.** Should you manually subscribe to a Mono in a WebFlux controller?

**Answer:** No. Return Mono/Flux so the HTTP infrastructure manages demand, serialization, errors, and cancellation.

**10.** Will an error inside a WebFilter definitely reach @RestControllerAdvice?

**Answer:** No. Depending on position/chain, errors outside annotated controllers may be handled by WebExceptionHandler.

**11.** Why can HTTP 404 appear even after a route has matched?

**Answer:** A controller/service can intentionally emit `ResponseStatusException(HttpStatus.NOT_FOUND)`; this differs from a route not existing.

**12.** Can a new JSON error be written after a streaming response has committed?

**Answer:** Not guaranteed; cleanup, logging/tracing, and a stream-protocol error mechanism are required if needed.

**13.** When a custom HandlerMapping returns a custom handler that no adapter supports, what happens?

**Answer:** Dispatcher has no way to invoke that handler kind; a matching HandlerAdapter is needed, or use a standard programming model.

**14.** When is a custom HandlerResultHandler needed?

**Answer:** When genuinely adding a new return type/response strategy unsupported by default handlers, after considering codecs/ResponseEntity/ServerResponse first.

**15.** Can both annotated controllers and RouterFunctions be used in one WebFlux app?

**Answer:** Yes. They share DispatcherHandler while having distinct mapping/adapter/result contracts.

## 27. References

- Spring Framework 6.2 — DispatcherHandler, SPI and result-handling order: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html
- Spring Framework 6.2 — Reactive Core / WebHandler API, filters and errors: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2 — Functional Endpoints and infrastructure beans: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html
- Spring Framework 6.2 — WebFlux Overview: https://docs.spring.io/spring-framework/reference/6.2/web/webflux.html
- Spring Framework — DispatcherHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/DispatcherHandler.html
- Spring Framework — HandlerMapping Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/HandlerMapping.html
- Spring Framework — HandlerAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/HandlerAdapter.html
- Spring Framework — HandlerResultHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/HandlerResultHandler.html
- Spring Framework — HandlerResult Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/HandlerResult.html
- Spring Framework — DispatchExceptionHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/DispatchExceptionHandler.html
- Spring Framework — WebFlux configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
- Spring Framework — WebFlux annotated return values: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Project Reactor documentation: https://projectreactor.io/docs/core/release/reference/
