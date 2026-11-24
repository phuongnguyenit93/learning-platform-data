# DispatcherHandler, HandlerMapping, and HandlerAdapter in Spring WebFlux

## 1. The Problem: How Does an HTTP Request Reach the Right Handler?

In Spring WebFlux, a controller or functional endpoint does not directly accept TCP sockets and does not decide on its own which URLs are routed to it. Spring WebFlux provides a unified dispatching mechanism to accept a request converted by the HTTP server into framework abstractions, locate the right handler, invoke that handler, and write the result as an HTTP response.

Three core components of this lesson:

- **DispatcherHandler**: Spring WebFlux's front controller, acting as the central coordinator.
- **HandlerMapping**: finds a handler suitable for the incoming request (based on URL, HTTP method, media type, or matching rules).
- **HandlerAdapter**: knows how to execute the specific handler type that was found and returns a `HandlerResult` when result processing is needed.

After these three steps comes another critical component: **HandlerResultHandler**. It transforms the value returned by the handler into the response's body, headers, and status—for example, serializing JSON or writing a stream of data. Without `HandlerResultHandler`, it is hard to see why finding and invoking the controller is not yet the final step of the HTTP flow.

A typical request:

~~~text
Client
  |
  v
HTTP server (Reactor Netty / supported container)
  |
  v
HttpHandler / HttpWebHandlerAdapter
  |
  v
WebFilter chain; WebExceptionHandlers on the error path
  |
  v
DispatcherHandler (WebHandler)
  |
  +-- HandlerMapping #1 ----\
  +-- HandlerMapping #2 -----+--> picks first matching handler
  +-- HandlerMapping #N ----/
  |
  v
HandlerAdapter matching the handler type
  |
  v
HandlerResult (value + handling metadata)
  |
  v
Matching HandlerResultHandler
  |
  v
HTTP response: status + headers + body
~~~

This diagram describes the logical processing path; it does not claim that every operation runs synchronously on one thread. Spring WebFlux is built on Reactive Streams: processing steps typically assemble and compose `Publisher`s that execute when subscribed by the HTTP runtime; I/O and callbacks can be scheduled across different threads depending on the server, schedulers, and operators used by the application.

## 2. Four Boundaries to Keep in Mind

Do not confuse Spring WebFlux with Spring MVC just because both support `@RestController` and `@GetMapping`.

| Layer | Spring WebFlux | Spring MVC |
|---|---|---|
| Front controller | `DispatcherHandler` | `DispatcherServlet` |
| Central request-handling contract | `WebHandler` / `Mono<Void>` | `HttpServlet` / Servlet API |
| Request/response context | `ServerWebExchange`; `ServerHttpRequest`/`Response` | `HttpServletRequest`/`Response` |
| HTTP server integration | `HttpHandler` and server adapters | Servlet container and Servlet registration |
| Annotated controller lookup | WebFlux `RequestMappingHandlerMapping` | MVC `RequestMappingHandlerMapping` |
| Annotated handler invocation | WebFlux `RequestMappingHandlerAdapter` | MVC `RequestMappingHandlerAdapter` |
| Common return types | `Mono<T>`, `Flux<T>`, `ResponseEntity<T>`, `ServerResponse` | `T`, `ResponseEntity<T>`, `ModelAndView`, async types |
| Functional routing | `RouterFunctionMapping` and `HandlerFunctionAdapter` | Spring MVC's own functional routing |
| Result handling | `HandlerResultHandler` | `HandlerAdapter` combined with MVC return-value handling |
| Characteristic filter | `WebFilter` | Servlet `Filter` |
| Reactive error handling | `WebExceptionHandler` and handler exception mechanisms | `HandlerExceptionResolver` and Servlet error handling |

Both frameworks share many class names that belong to different packages. For example, WebFlux's `RequestMappingHandlerAdapter` is not the same class as Spring MVC's `RequestMappingHandlerAdapter`. Always check package names when reading stack traces or writing configuration.

**`DispatcherHandler` never turns into `DispatcherServlet`** simply by adding `WebClient`. `WebClient` is just an HTTP client with a reactive API and can be used inside a Spring MVC application. Conversely, a reactive Spring WebFlux server application uses `DispatcherHandler` as its central dispatch point.

## 3. What Is DispatcherHandler?

`DispatcherHandler` is a class in the `org.springframework.web.reactive` package. It implements `WebHandler`, meaning it accepts a `ServerWebExchange` and returns a `Mono<Void>` representing completion of HTTP request/response processing under the reactive contract.

Conceptual method of `WebHandler`:

~~~java
Mono<Void> handle(ServerWebExchange exchange);
~~~

Where:

- **ServerWebExchange** represents a single HTTP exchange, including the request, response, attributes, session/principal info, and related collaborators. Do not treat it as a POJO to be freely shared across other requests.
- **Mono<Void>** is a `Publisher` signaling completion or error of the handling task; it does not carry a body object for the caller to read directly. The body is written to `ServerHttpResponse` during processing.
- **DispatcherHandler** acts as a coordinator—not a place for business logic, not directly executing SQL, and not enforcing authentication policy in place of `WebFilter`/Spring Security.

A simplified version of the dispatch algorithm:

~~~text
handle(exchange):
  find a HandlerMapping that returns a matching handler
  if no handler:
      emit a no-handler-found signal (usually leading to 404)
  select a HandlerAdapter that supports the returned handler
  adapter.handle(exchange, handler) -> Mono<HandlerResult>
  select a HandlerResultHandler that supports the HandlerResult
  resultHandler.handleResult(exchange, result) -> Mono<Void>
  complete or propagate exceptions to the error-handling path
~~~

This algorithm is for understanding the architecture, **not verbatim source code** of `DispatcherHandler`. Details such as empty results, result-attached exception handlers, ordering, and writing the response follow actual API/runtime behavior.

### 3.1. Why Doesn't DispatcherHandler Need to Know Every Controller Type?

`DispatcherHandler` only depends on strategy interfaces. `HandlerMapping`s know how to find handlers, `HandlerAdapter`s know how to invoke each handler type, and `HandlerResultHandler`s know how to write results. That is why the same front controller can serve:

- Annotated controllers using `@RestController`, `@RequestMapping`, `@GetMapping`.
- Functional endpoints using `RouterFunction` and `HandlerFunction`.
- Static resources via resource handlers.
- Extension handlers provided by the framework or application.

Adding a new `@GetMapping` method does not require modifying `DispatcherHandler`. Spring registers route metadata in a `HandlerMapping` managed by the `ApplicationContext`; `DispatcherHandler` picks the appropriate mapping/adapter at runtime.

### 3.2. When Is DispatcherHandler Registered?

In a Spring Boot application using `spring-boot-starter-webflux` and running in reactive web application mode, Boot sets up the Spring WebFlux infrastructure. `DispatcherHandler` is typically the central `WebHandler` in the `ApplicationContext`. `WebHttpHandlerBuilder` combines the `WebHandler` with `WebFilter`s and `WebExceptionHandler`s, and `HttpWebHandlerAdapter` provides integration with the HTTP server's `HttpHandler`.

With Reactor Netty, the server-side adapter translates Netty-level requests and responses to Spring's `HttpHandler` contract. Other reactive web servers have corresponding adapters. You do not register `DispatcherHandler` via `web.xml` or `ServletRegistrationBean` like Spring MVC's `DispatcherServlet`.

In advanced scenarios, `@EnableWebFlux` gives greater manual control over WebFlux configuration; normal Spring Boot applications **do not need** to add `@EnableWebFlux`. If you only want to customize CORS, formatters, or resource handling, `WebFluxConfigurer` is usually more appropriate and preserves most of Boot's auto-configuration.

## 4. HandlerMapping: Which Handler Should Process the Request?

`HandlerMapping` in WebFlux provides a contract along the lines of:

~~~java
Mono<Object> getHandler(ServerWebExchange exchange);
~~~

When a mapping finds no matching handler, it typically returns `Mono.empty()`, allowing `DispatcherHandler` to consult other `HandlerMapping`s in order. When it finds a handler, it returns a `Publisher` emitting that handler. A mapping may also produce a specific HTTP error, such as when method or media-type conditions are not met, rather than simply saying "no handler found."

Common `HandlerMapping` implementations:

| Type | What is registered? | Returned handler |
|---|---|---|
| `RequestMappingHandlerMapping` | Controller methods with `@RequestMapping`/`@GetMapping`/... | `HandlerMethod`, carrying bean and method info |
| `RouterFunctionMapping` | `RouterFunction` beans declared in context | `HandlerFunction` matching the request |
| Mapping for static resources | Resource handlers / path patterns | `ResourceWebHandler` or suitable resource handler |
| Custom mappings added by app/libraries | Specialized routes/handlers | Depends on handler type and supporting adapter |

The key point is that **a handler is not necessarily a Controller instance**. With the annotation model, it is usually a `HandlerMethod`. With functional routing, it is usually a `HandlerFunction`. `HandlerAdapter` is selected based on **the type of handler found**, not merely the request path.

### 4.1. How Does Spring Know About `@GetMapping`?

When the `ApplicationContext` starts, WebFlux's `RequestMappingHandlerMapping` scans controller beans and methods with mapping annotations. It builds route info from:

- HTTP method: GET, POST, PUT, DELETE...
- URL/path pattern.
- `params` and `headers` conditions.
- `consumes` and `produces` conditions.
- Related mapping metadata.

Example:

~~~java
@RestController
@RequestMapping("/api/items")
class ItemController {

    @GetMapping("/{id}")
    Mono<String> get(@PathVariable long id) {
        return Mono.just("item-" + id);
    }
}
~~~

`GET /api/items/42` can map to the `HandlerMethod` for `ItemController.get(...)`. Tomcat/Netty does not understand `@GetMapping`; it is Spring WebFlux's `HandlerMapping` infrastructure that detects annotations and selects the handler.

### 4.2. Which HandlerMapping Takes Precedence?

Spring can have multiple `HandlerMapping` beans at once. They are typically sorted by order and `DispatcherHandler` checks them sequentially until one matches. Order matters greatly when a path could match a functional route, an annotated route, and a static resource handler.

Do not assume annotated controllers always beat functional routes across every configuration or version. If you register two endpoints with the same path and method under both models, check the mapping order at runtime—and better yet, avoid overlapping route designs.

The order of `HandlerMapping`s and the order of `HandlerResultHandler`s are separate concerns: one decides **who handles the request**, while the other decides **who writes the handled result**.

### 4.3. 404 Is Not Always a Missing Controller

If no `HandlerMapping` matches, the request usually results in `404 Not Found`. However, a 404 can also occur because a business handler returns `Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND))`, a resource handler cannot find a file, or a gateway/proxy rewrote the path.

Therefore, when encountering a 404, inspect the actual URL reaching Spring, the HTTP method, media types, registered handlers, and whether another route or static handler claimed the request. Do not jump to the conclusion that `DispatcherHandler` wasn't initialized.

## 5. HandlerAdapter: Executing the Selected Handler

Once `HandlerMapping` returns a handler, `DispatcherHandler` finds a `HandlerAdapter` that supports it. The core interface can be expressed simply:

~~~java
boolean supports(Object handler);

Mono<HandlerResult> handle(ServerWebExchange exchange, Object handler);
~~~

`supports(...)` determines whether the adapter can handle the handler type. `handle(...)` invokes the handler through its mechanism and returns a `HandlerResult` so later steps can decide how to write the response.

Common adapters:

- **RequestMappingHandlerAdapter**: executes `HandlerMethod`s of annotated controllers. It uses WebFlux argument resolvers, reactive type adapters, validation/binding when applicable, and WebFlux return-value mechanisms.
- **HandlerFunctionAdapter**: executes a `HandlerFunction` selected by `RouterFunctionMapping`, passing a `ServerRequest` and producing a `Publisher` for the functional result.
- **SimpleHandlerAdapter**: supports handlers conforming to the `WebHandler` contract in framework-supported cases.

The adapter is not chosen by whether the class name contains `Controller`; it is chosen via `supports(handler)`. If an application adds a custom handler type without a `HandlerAdapter` that supports it, `DispatcherHandler` cannot execute it as expected.

### 5.1. How Is an Annotated Handler Invoked?

When the adapter handles a `HandlerMethod`, it must resolve the Java method parameters:

- `@PathVariable` extracts values from path variables.
- `@RequestParam` extracts query parameters per configuration.
- `@RequestHeader` reads matching headers.
- `@RequestBody` works with codecs/body readers to decode the HTTP body.
- `ServerWebExchange`, `ServerHttpRequest`, `Principal`, and other supported parameter types are supplied by their corresponding resolvers.
- When `@Valid` and Bean Validation are configured, a validation step may run after data binding.

Underneath are reflection/invocation, conversion, validation, error handling, and reactive type adaptation mechanisms. Controllers can return `Mono<T>`, `Flux<T>`, `ResponseEntity<T>`, or other return types supported by WebFlux.

Example method:

~~~java
@PostMapping(path = "/orders", consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<ResponseEntity<OrderView>> create(
        @RequestBody Mono<CreateOrder> body) {

    return body.map(req ->
            ResponseEntity.status(HttpStatus.CREATED)
                    .body(new OrderView(100L, req.item())));
}
~~~

This is an illustrative method, not a standalone class; it needs to sit in an annotated controller with `CreateOrder` and `OrderView` records defined. The adapter decodes the body into `Mono<CreateOrder>`, passes it to the controller, and receives `Mono<ResponseEntity<OrderView>>`. Writing JSON and status 201 happens in the result-handling step, not inside `HandlerMapping`.

### 5.2. How Is a Functional Handler Invoked?

With functional endpoints, a `RouterFunction` defines a set of routes using `RequestPredicate`s. When `RouterFunctionMapping` finds a matching route, `HandlerFunctionAdapter` invokes the `HandlerFunction` with a `ServerRequest`.

General pattern:

~~~java
HandlerFunction<ServerResponse> handler =
        request -> ServerResponse.ok().bodyValue("hello");
~~~

This snippet uses `org.springframework.web.reactive.function.server.HandlerFunction` and `ServerResponse`; it needs to be placed inside a Java class with imports. The result of a functional handler is `Mono<ServerResponse>`; writing the response is handled by dedicated WebFlux components.

A functional handler is not a `@RestController` in disguise. `RouterFunctionMapping` does not need `@GetMapping`; it evaluates route predicates and dispatches the request to the `HandlerFunction`. Yet both models participate in the unified `DispatcherHandler` pipeline.

## 6. HandlerResult and HandlerResultHandler: The Missing Step for an HTTP Response

If you only study `DispatcherHandler` + `HandlerMapping` + `HandlerAdapter`, you miss the question: "Who serializes the value returned by the controller and writes it out to the socket?"

**HandlerResult** holds the handler invocation result and metadata needed for result handling, such as the return value and its type. **HandlerResultHandler** knows how to interpret a specific result shape and write it to `ServerHttpResponse`.

Common result handlers:

| HandlerResultHandler | Typical scenario | Outcome |
|---|---|---|
| `ResponseBodyResultHandler` | `@ResponseBody` or `@RestController` | Serializes body using an appropriate `HttpMessageWriter` |
| `ResponseEntityResultHandler` | `ResponseEntity`, `HttpEntity`, and supported reactive wrappers | Sets status/headers, then writes body |
| `ServerResponseResultHandler` | Functional endpoint returning `ServerResponse` | Writes `ServerResponse` per the functional model contract |
| `ViewResolutionResultHandler` | Controller returning a view/model | Resolves a matching `View` and renders the response |

Not every handler returns a value of the same type. For example, an annotated controller might return `Mono<Book>`, whereas a functional handler returns `Mono<ServerResponse>`. Their adapters differ, and the matching result handlers also differ.

### 6.1. Once You Have a Mono, Who Subscribes?

The controller simply creates and returns a `Publisher`; creating a `Mono`/`Flux` does not automatically perform all I/O. Spring WebFlux and the HTTP runtime coordinate to subscribe to the pipeline, demand data via Reactive Streams, and complete writing the response.

Example:

~~~java
@GetMapping("/answer")
Mono<Integer> answer() {
    return Mono.fromSupplier(() -> 42);
}
~~~

In a valid WebFlux controller, the supplier runs when the `Publisher` is subscribed reactively, not necessarily at the instant the Java method creates the `Mono`. Do not manually call `.subscribe()` inside a controller to force output out to the HTTP response; doing so can detach work from the request lifecycle, breaking error handling, cancellation, and backpressure.

### 6.2. Flux as a Multi-Element Response Body

If a controller returns `Flux<Book>`, WebFlux can use a JSON writer to encode the body; the exact format depends on `Content-Type`, codecs, and data type. With `application/json`, multiple items are typically represented as an appropriate JSON structure. With `text/event-stream` or `application/x-ndjson`, the body can be streamed element by element when codecs and handlers support it.

Do not conclude that "returning a `Flux` guarantees every element is flushed immediately." Buffering in codecs, the HTTP stack, reverse proxies, and clients also affects when data arrives. Choose the right media type and test actual streaming behavior.

## 7. Complete Example: Annotated WebFlux Controller

Assume a Spring Boot 3.x project using Java 17+, Gradle, Maven Central, and the Spring Boot Gradle plugin configured. Basic dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Depending on the project version, `starter-test` may already bring in the required test libraries; declaring `reactor-test` explicitly keeps `StepVerifier` dependencies clear. This example deliberately omits `spring-boot-starter-web` to avoid accidentally switching the application to Servlet MVC.

Create `src/main/java/dev/example/webflux/WebFluxFlowApplication.java`:

~~~java
package dev.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxFlowApplication.class, args);
    }
}
~~~

Create `src/main/java/dev/example/webflux/BookController.java`:

~~~java
package dev.example.webflux;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/books")
public class BookController {

    public record BookView(long id, String title) {}

    public record CreateBook(String title) {}

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<BookView> find(@PathVariable long id) {
        if (id <= 0) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "id must be positive"));
        }
        return Mono.just(new BookView(id, "WebFlux Handbook"));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<BookView>> create(
            @RequestBody Mono<CreateBook> body) {

        return body.map(input -> ResponseEntity
                .status(HttpStatus.CREATED)
                .body(new BookView(101L, input.title())));
    }
}
~~~

These are two syntactically standalone Java files in a Spring Boot WebFlux project. The two records are illustrative data types and do not query or persist to a real database. `@RestController` is discovered by component scanning because it is in the same package as the `@SpringBootApplication` class.

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
~~~

Run the application with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell, use `.\gradlew.bat bootRun`. Test GET:

~~~bash
curl -i http://localhost:8080/api/books/7
~~~

Key expected output: HTTP 200 and JSON body:

~~~json
{"id":7,"title":"WebFlux Handbook"}
~~~

Test POST:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Reactive Systems"}'
~~~

Line continuations as above are for Unix shells; on Windows you can use `curl.exe` on a single line. The primary expected result is HTTP 201 and JSON body:

~~~json
{"id":101,"title":"Reactive Systems"}
~~~

Headers such as `Date`, `Content-Length`, and `Transfer-Encoding` can vary by server, codec, and runtime; do not treat the entire header set as fixed output.

### 7.1. Tracing GET Through the Three Components

For `GET /api/books/7`:

1. The HTTP runtime receives the request and creates `ServerWebExchange`.
2. The `WebFilter` chain runs any cross-cutting steps, if present.
3. `DispatcherHandler` asks `HandlerMapping`s to find a handler.
4. `RequestMappingHandlerMapping` identifies `BookController.find(...)`, with path variable `id=7`.
5. `DispatcherHandler` picks `RequestMappingHandlerAdapter` to execute the `HandlerMethod`.
6. The adapter uses an argument resolver to convert path segment `"7"` into `long 7` and invokes the controller.
7. The controller returns `Mono<BookView>`; the adapter creates the matching `HandlerResult`.
8. `ResponseBodyResultHandler` writes the JSON body from `BookView` using the writer/codec on the classpath.
9. The reactive pipeline completes and the runtime sends the response to the client.

If `id` is invalid per controller logic, `Mono.error(ResponseStatusException)` enters the error-handling path and returns HTTP 400 when status can still be set. The error path differs from the normal result path, yet remains part of the WebFlux mechanism.

### 7.2. Tracing POST and Reactive Body Handling

For `POST /api/books` with JSON:

1. `HandlerMapping` matches the POST route and `consumes`/`produces` conditions.
2. `RequestMappingHandlerAdapter` uses a reader/codec to supply `@RequestBody Mono<CreateBook>`.
3. The controller returns `Mono<ResponseEntity<BookView>>` built by mapping over the body.
4. `ResponseEntityResultHandler` receives the response entity once the `Publisher` emits its result.
5. Status 201 is applied, `BookView` is serialized to JSON, and the response completes.

Do not call `.block()` inside the controller to extract `CreateBook` from the `Mono`; write reactive code by composing `Publisher`s and returning them to the framework.

## 8. Complete Example: Functional Routing on the Same DispatcherHandler

Alongside annotated controllers, Spring WebFlux provides a functional endpoint API. To demonstrate that `HandlerMapping`/`HandlerAdapter` change depending on the handler type, create `src/main/java/dev/example/webflux/FunctionalRoutes.java`:

~~~java
package dev.example.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    public record Message(String text) {}

    @Bean
    RouterFunction<ServerResponse> helloRoute() {
        return route(GET("/functional/hello"), request ->
                ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(new Message("Hello functional WebFlux")));
    }
}
~~~

The configuration class is discovered by Spring Boot component scanning. The `RouterFunction<ServerResponse>` bean defines route `GET /functional/hello`.

Run the same application from Section 7 and test:

~~~bash
curl -i http://localhost:8080/functional/hello
~~~

Expected body:

~~~json
{"text":"Hello functional WebFlux"}
~~~

Here:

1. `DispatcherHandler` is still the front controller.
2. `RouterFunctionMapping` finds the route with matching `RequestPredicate` `GET("/functional/hello")`.
3. `HandlerFunctionAdapter` invokes the `HandlerFunction` with `ServerRequest`.
4. `HandlerFunction` returns `Mono<ServerResponse>`.
5. `ServerResponseResultHandler` writes HTTP status, headers, and JSON body.

REST annotations and functional routing can coexist in the same Spring WebFlux application. They do not require two `DispatcherHandler`s or two HTTP ports.

### 8.1. Functional Predicates Can Go Beyond a GET Path

`RequestPredicate`s can combine HTTP method, path, headers, content type, and request attributes. In the functional API, a route accepting JSON can declare POST, require a content type, and read the body via `request.bodyToMono(...)`. Functional endpoints handle requests via `ServerRequest` and `ServerResponse`; annotated endpoints use their own argument resolvers and return handlers.

Do not assume that annotated `@ControllerAdvice` exception handling automatically covers every functional handler in the exact same way. For functional routes, you often need reactive operators, error handling within the functional handler, or a compatibly designed global `WebExceptionHandler`.

### 8.2. Overlapping Routes Between Annotation and Functional Models

If both `BookController` and a `RouterFunction` declare `GET /api/books/7`, runtime selection follows the order of `HandlerMapping`s and their conditions—not Java file order. Avoid creating duplicate routes in production. If multiple strategies are strictly required, verify the `HandlerMapping` order and test real requests so upgrades do not expose unexpected behavior.

## 9. How Does HandlerResultHandler Differ From HandlerAdapter?

This is an important question that often causes confusion when reading debug logs.

**HandlerAdapter** answers "how do I **invoke** this handler?"  
**HandlerResultHandler** answers "how do I **write the result** returned by this handler?"

Summary table:

| Selected handler | Matching adapter | Return value | Typical result handler |
|---|---|---|---|
| Annotated `HandlerMethod` `GET /books` | `RequestMappingHandlerAdapter` | `Mono<BookView>` with `@ResponseBody` | `ResponseBodyResultHandler` |
| Annotated `HandlerMethod` `POST /books` | `RequestMappingHandlerAdapter` | `Mono<ResponseEntity<BookView>>` | `ResponseEntityResultHandler` |
| Functional `HandlerFunction` | `HandlerFunctionAdapter` | `Mono<ServerResponse>` | `ServerResponseResultHandler` |
| Annotated controller returning a view | `RequestMappingHandlerAdapter` | Model/view per WebFlux contract | `ViewResolutionResultHandler` |

Do not put JSON serialization logic inside `HandlerMapping`. Do not put URL-based controller selection logic inside `HandlerResultHandler`. Giving each interface one responsibility makes the system easier to extend and test.

### 9.1. Where Are Headers and Status Set?

In annotated WebFlux, `ResponseEntity` can control status and headers, and `@ResponseStatus` can supply status via handler metadata. A result such as `Mono<ResponseEntity<T>>` is interpreted by the framework before writing the response.

In functional WebFlux, `ServerResponse.ok()`, `ServerResponse.status(...)`, `contentType(...)`, and similar APIs describe the HTTP response. Executing and writing the data belongs to the `ServerResponse` handling layer.

HTTP status is not solely decided by `HandlerMapping`: a handler can be matched successfully and still return 404 when an entity is missing, 400 on validation failure, or 503 when a backend is unavailable.

## 10. Errors, WebExceptionHandler, and @RestControllerAdvice

A reactive pipeline can signal errors in many places: `WebFilter`, `HandlerMapping`, argument binding, handler logic, codecs, or response writing. The error path depends on where the error happens and the response state.

Common mechanisms:

- **ResponseStatusException**: conveys an intentional HTTP status from a handler or appropriate layer.
- **@ExceptionHandler / @RestControllerAdvice**: handles exceptions from annotated WebFlux controllers per configuration.
- **WebExceptionHandler**: handles errors at the `WebHandler` chain scope, reaching beyond a single annotated controller.
- **Reactive operators** such as `onErrorResume`, `onErrorMap`, `timeout`: reshape errors within individual reactive flows.
- **Spring Boot error handling**: built-in error responses following HTTP semantics and configuration.

The example handler in Section 7 returns an error when `id` is invalid. To standardize errors for annotated APIs, you can create an advice:

~~~java
package dev.example.webflux;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import reactor.core.publisher.Mono;

@RestControllerAdvice
public class ApiErrorAdvice {

    public record ApiError(String code, String message) {}

    @ExceptionHandler(IllegalArgumentException.class)
    public Mono<ResponseEntity<ApiError>> onBadInput(
            IllegalArgumentException error) {

        return Mono.just(ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(new ApiError("INVALID_INPUT", error.getMessage())));
    }
}
~~~

The class above illustrates handling `IllegalArgumentException` during annotated request processing. Do not assume it will handle every Netty error, errors occurring before `DispatcherHandler`, or exceptions emitted by functional `HandlerFunction`s. For those paths, design error handling at the appropriate scope.

**Be careful once the response has committed.** If a `Flux` is streaming the body and the server has already sent headers/bytes, a late error may no longer allow changing the HTTP status to 500. In that case, manage stream termination, logging, client retries, and data consistency to preserve business semantics.

## 11. WebFilter Differs From HandlerInterceptor and Servlet Filter

Spring WebFlux uses `WebFilter` to intercept/modify HTTP flow at the `WebHandler` layer before dispatch. In Servlet MVC, Servlet `Filter` belongs to `jakarta.servlet` and `HandlerInterceptor` sits inside the MVC handler chain. WebFlux does not run as a Servlet `Filter` chain by default on Reactor Netty.

Simple `WebFilter` example adding a response header:

~~~java
package dev.example.webflux;

import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class DemoResponseHeaderFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        exchange.getResponse().getHeaders()
                .add("X-App-Pipeline", "webflux");

        return chain.filter(exchange);
    }
}
~~~

In the demo, the filter is auto-registered by Spring via `@Component`. The header is added before the chain continues processing; this is an illustration, not a full security policy or tracing mechanism. If a header needs to depend on the outcome and response state, consider commit timing or use `beforeCommit` appropriately.

Spring Security reactive server uses a `WebFilter` chain and `SecurityWebFilterChain` with WebFlux-specific APIs, not Servlet/MVC's `SecurityFilterChain`. Using the wrong filter type or security configuration can block all requests or leave security rules inactive.

### 11.1. Avoid Side Effects Outside the Publisher

Inside a `WebFilter`/handler method, if you manually subscribe to a `Publisher` to run secondary work, the request can finish before the side effect completes, errors will not propagate to the HTTP pipeline, and cancellation will no longer be controlled. Instead, chain publishers with `then`, `flatMap`, or `doOn...` according to their intended semantics, or offload side effects to a managed background processing system.

## 12. Threading, Blocking, and Reactive Streams

WebFlux supports non-blocking HTTP handling, **but does not automatically turn every dependency non-blocking**. Calling JDBC, blocking filesystem operations, or network-waiting SDKs directly on an event-loop thread can slow down all requests sharing that event loop.

Things to remember:

- Reactor Netty typically uses a finite number of event-loop threads to handle many connections.
- `Mono` and `Flux` are publisher models; they do not mean each request spawns a new thread.
- `map` handles fast/synchronous transformations; `flatMap` is suited when a transformation returns an asynchronous publisher; `concatMap` preserves sequential order per Reactor semantics.
- `subscribeOn`/`publishOn` change the scheduler for the pipeline depending on operator placement; do not sprinkle them blindly to "increase concurrency."
- Blocking I/O does not vanish just because it is wrapped in `Mono.just(...)`. A blocking call inside `Mono.just` executes immediately when Java evaluates the expression.
- `boundedElastic` is a bounded transitional option for blocking work when reactive drivers are unavailable; monitor queues, threads, and deadlines.

Example wrapping an unavoidable blocking call:

~~~java
Mono<LegacyResult> result = Mono
        .fromCallable(() -> legacyBlockingClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
~~~

This is an illustrative snippet: `legacyBlockingClient`, `LegacyResult`, and Reactor imports must be defined in the project. This approach **does not make the dependency non-blocking**; it only avoids occupying the event loop while blocking, while consuming worker resources from `boundedElastic`. In the long run, prefer `WebClient`, R2DBC, or reactive-compatible drivers when architecture and business requirements allow.

When processing many items, consider backpressure, cancellation, timeouts, and memory. A handler returning an unbounded or high-rate `Flux` without bounds can overload the system even without blocking threads.

## 13. When Does WebFlux Auto-Create the Dispatch Pipeline?

A standard Spring Boot WebFlux project requires the right dependencies and a reactive server. With `spring-boot-starter-webflux`, Boot typically uses Reactor Netty as the default embedded runtime. During startup, WebFlux's annotation infrastructure, functional routes, and `WebFilter`s are configured in the `ApplicationContext`.

Notable configuration properties:

~~~yaml
spring:
  main:
    web-application-type: reactive
  webflux:
    base-path: /service

server:
  port: 8080
~~~

**Distinguish their purposes:** `spring.main.web-application-type=reactive` forces Boot to choose a reactive web application when needed; many projects with only `starter-webflux` do not need to force it. `spring.webflux.base-path` sets the WebFlux base path—for example, endpoint `/api/books/7` becomes reachable at `/service/api/books/7`. Do not use `server.servlet.context-path` (which belongs to Servlet MVC) in place of the reactive base path.

When both `spring-boot-starter-web` and `starter-webflux` are present, Spring Boot typically prefers the MVC Servlet stack unless overridden. Do not identify the web stack just by seeing `Mono` or `WebClient` in code. Check the dependency tree, `ApplicationContext` type, and actual runtime server.

### 13.1. Do You Need to Create a DispatcherHandler Bean Manually?

Usually no. When the application properly runs WebFlux, the framework sets up `DispatcherHandler` along with matching mappings, adapters, and result handlers. Manually creating another `DispatcherHandler` bean without understanding the infrastructure configuration can cause missing strategies, bean conflicts, or unpredictable routing changes.

To add endpoints, choose annotated controllers or `RouterFunction`s. To configure CORS, codecs, path matching, formatters, or resource handlers, prefer `WebFluxConfigurer` or supported customizers. Only build a custom `HandlerMapping` or `HandlerAdapter` when you genuinely need a handler type unsupported by the framework and have integration tests in place.

### 13.2. When to Use `@EnableWebFlux`?

`@EnableWebFlux` enables and gives manual control over WebFlux framework configuration when managing many aspects by hand. In Spring Boot, adding this annotation can change the level of auto-configuration/extensions Boot provides. Do not add it just to "activate `DispatcherHandler`" when `starter-webflux` is already present.

An application may need `WebFluxConfigurer` to customize CORS or codecs while still letting Boot auto-configure everything else. Choose the least intrusive approach that meets your real goal.

## 14. Testing HandlerMapping and HandlerAdapter With WebTestClient

A unit test invoking a Java controller method directly does not prove that the route is registered or that the adapter works. You need to test requests going through the WebFlux dispatch pipeline.

Using the project from Section 7, create `src/test/java/dev/example/webflux/BookControllerTest.java`:

~~~java
package dev.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = BookController.class)
class BookControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void findBookIsMapped() {
        client.get().uri("/api/books/7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7)
                .jsonPath("$.title").isEqualTo("WebFlux Handbook");
    }

    @Test
    void invalidIdGetsBadRequest() {
        client.get().uri("/api/books/0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

`@WebFluxTest` creates a WebFlux test slice subset of the `ApplicationContext` for controller testing rather than loading every business bean. If the controller depends on service beans, use `@MockBean` or the mocking mechanism supported by your Boot version, or provide suitable test configuration. In this example, the controller has no service dependencies.

For functional routes, you can test by binding `WebTestClient` directly to a `RouterFunction`, or run a `SpringBootTest` integration test and call `GET /functional/hello`. To verify the exact `HandlerMapping` ordering between annotation and functional models, run an integration test with both route types in the same `ApplicationContext`.

### 14.1. When Are Integration Tests Needed?

When you need to verify a real HTTP server, `WebFilter`s, TLS, Reactor Netty, proxy behavior, or network-dependent errors, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with `WebTestClient` bound to the actual server port. A slice test does not reproduce all server/connector characteristics.

Valuable tests to include:

1. `GET /api/books/7` returns JSON 200 and maps to the annotated controller.
2. `POST /api/books` accepts a JSON body and returns JSON 201.
3. `GET /functional/hello` goes through `RouterFunctionMapping` and `HandlerFunctionAdapter`.
4. Wrong HTTP method returns the expected response, usually 405 when path matches but method does not.
5. Request with a `Content-Type` incompatible with `consumes` results in an error like 415.
6. An `Accept` header incompatible with `produces` can result in 406.
7. Unmapped request returns 404, distinguished from resource handler fallback if configured.
8. Invalid `id` emits `ResponseStatusException` and returns 400.
9. `WebFilter` adds `X-App-Pipeline` to the response when registered.
10. In an appropriate test setup, publisher cancellation and streaming errors are properly observed.

Tests do not need to assert internal classes via reflection once HTTP behavior is clear. However, when debugging a custom handler, inspect logs or bean types to confirm the right mapping/adapter was selected.

## 15. Observing and Diagnosing the Pipeline

Distinguish three separate problem areas:

- **Request not routed:** mapping does not exist, wrong base path, different method/media type than expected, or proxy rewrote the URL.
- **Handler selected but fails on invocation:** argument conversion, body decoding, validation, service error, blocking I/O, or exception inside `Publisher`.
- **Handler returns a result but response fails:** no result handler supports the return type, codec does not support media type, response already committed, client closed connection, or encoding error.

### 15.1. Controlled Logging

In dev/test environments, you can increase log verbosity:

~~~yaml
logging:
  level:
    org.springframework.web.reactive.DispatcherHandler: DEBUG
    org.springframework.web.reactive.result.method.annotation.RequestMappingHandlerMapping: TRACE
    org.springframework.web.reactive.function.server.support.RouterFunctionMapping: TRACE
~~~

Log categories and output details can change across versions; do not rely on one specific log string to verify all routes. `TRACE` can be very verbose, so enable it only temporarily and avoid logging sensitive data.

### 15.2. Actuator Mappings Endpoint

With `spring-boot-starter-actuator`, you can expose `mappings` in test environments:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,mappings
~~~

Then call the endpoint on the right management port/path:

~~~bash
curl -i http://localhost:8080/actuator/mappings
~~~

For WebFlux, the response typically includes handler-mapping details; the exact JSON structure depends on version and configuration. This endpoint can expose internal API routes, so restrict access via authentication/network policy or enable it only in development.

If `management.server.port` is configured separately, `/actuator/mappings` may listen on the management port. If a proxy or Spring Security returns 401/403/404, check configuration before concluding `DispatcherHandler` does not exist.

### 15.3. Distinguishing 404, 405, 406, 415, and Codec Errors

| Outcome | Common cause | What to check |
|---|---|---|
| 404 Not Found | No matching handler/resource, or handler explicitly signaled not found | Request path, base path, route registration, proxy rewrite |
| 405 Method Not Allowed | Path is mapped but HTTP method is wrong | `@GetMapping`/`@PostMapping`, `RequestPredicate` |
| 406 Not Acceptable | `Accept` header incompatible with producible response types | `produces`, `Accept`, media type writers |
| 415 Unsupported Media Type | Body `Content-Type` incompatible | `consumes`, codecs, request body |
| 400 Bad Request | Binding/decoding/validation failure or business error mapped to bad request | Path variables, query/body schema, codec errors |
| 500 Internal Server Error | Unhandled error in handler/pipeline | Stack trace, reactive error chain, response commit |
| Client timeout/connection closed | Network error, overloaded server, blocking operation, or streaming/cancellation | Event loop, response time, downstream, reverse proxy |

These status codes represent typical scenarios, not immutable outcomes across every configuration or API. A request may be blocked by a `WebFilter` or Spring Security before reaching `DispatcherHandler` and return 401/403 even if `HandlerMapping` is configured properly.

## 16. Customizing WebFlux at the Right Layer

When adding features, place logic in the appropriate layer:

| Goal | Typically appropriate extension point |
|---|---|
| Define API URL/HTTP method | `@RequestMapping` annotations or `RouterFunction` |
| Add CORS, formatters, custom codecs, static resources | `WebFluxConfigurer` or Boot-supported properties |
| Reactive authentication/authorization | `SecurityWebFilterChain` and WebFlux security |
| Tracing / common headers on all requests | `WebFilter` and corresponding tracing/metrics observability |
| Standardize annotated controller errors | `@RestControllerAdvice` / `@ExceptionHandler` |
| Global error handling before/after handlers | `WebExceptionHandler` or Boot error handling |
| Customize body serialization | Appropriate codec / `HttpMessageWriter` |
| Completely new handler selection strategy | Custom `HandlerMapping` |
| Execute a new handler type | Custom `HandlerAdapter` |
| Write a new `HandlerResult` type | Custom `HandlerResultHandler` |

Do not write a custom `HandlerAdapter` just to "optimize speed" for a controller. When using `@RestController`, Spring already provides an optimized, well-tested adapter. Infrastructure customization should only come after standard APIs fall short of requirements.

### 16.1. Why Must Extensions Align Across All Three Parts?

Suppose you write a `HandlerMapping` returning a `MyHandler` object. Without a `HandlerAdapter` whose `supports(MyHandler)` matches, the dispatcher cannot invoke that object. If the adapter returns a `HandlerResult` with a data type that no `HandlerResultHandler` supports, the pipeline likewise cannot write the response.

Therefore, an entirely new handler type typically needs:

1. Mapping rules (`HandlerMapping`).
2. Invocation rules (`HandlerAdapter`).
3. Result representation rules (existing `HandlerResultHandler` or a custom one).
4. Error, cancellation, ordering, and observability rules.
5. Integration tests alongside other `HandlerMapping`s and `HandlerAdapter`s.

You do not need any of that when simply adding a new REST endpoint with annotations or functional routing.

## 17. Common Mistakes to Avoid

**Mistake 1 — Using DispatcherServlet and ServletRegistrationBean for reactive WebFlux.**  
`DispatcherServlet` belongs to Spring MVC/Servlet. The reactive Spring WebFlux front controller is `DispatcherHandler` and typically runs through an `HttpHandler` adapter. Before fixing "mapping," verify whether WebFlux or MVC is actually running.

**Mistake 2 — Calling `.block()` in a controller/WebFilter on the event loop.**  
Blocking calls can stall the event loop or throw errors on non-blocking threads. Compose `Publisher`s with `map`/`flatMap`/`zip`; for unavoidable legacy blocking dependencies, offload in a controlled manner via `boundedElastic` or migrate to reactive drivers.

**Mistake 3 — Calling `.subscribe()` manually and returning `Mono.empty()`.**  
This breaks the link between side effects, response, errors, and cancellation. Return the `Publisher` describing the entire work to be completed to the framework.

**Mistake 4 — Adding `@GetMapping` without `@RestController` in component scan.**  
If the `ApplicationContext` does not discover the handler method, `RequestMappingHandlerMapping` will not register the route. Check the `@SpringBootApplication` package, conditional beans, and controller annotations.

**Mistake 5 — Mistaking HandlerAdapter as the component that matches URLs.**  
`HandlerMapping` selects the handler; `HandlerAdapter` invokes the handler. These two layers run consecutively and solve different problems.

**Mistake 6 — Forgetting HandlerResultHandler.**  
A handler may return `Mono<ResponseEntity<Book>>`, yet response status, headers, and body only materialize when the matching result handler writes them into the HTTP response.

**Mistake 7 — Confusing WebFlux RequestMappingHandlerAdapter with MVC's.**  
The class name is identical, but the package and contract differ. When importing or debugging, check full packages: `org.springframework.web.reactive...` vs. `org.springframework.web.servlet...`.

**Mistake 8 — Assuming every Flux streams instantaneously.**  
HTTP body format, codecs, proxy buffering, and clients can batch or buffer data. When streaming is required, use an appropriate media type like `text/event-stream` or NDJSON and test actual delivery timing.

**Mistake 9 — Assuming WebFilter works like MVC HandlerInterceptor.**  
`WebFilter` wraps a `WebHandler` exchange; `HandlerInterceptor` belongs to the MVC Servlet stack. Do not place mandatory security logic in an extension point that does not execute on the active stack.

**Mistake 10 — Declaring the same path in both annotated and functional routes.**  
`HandlerMapping` order can decide which route handles the request. Design unique routes or explicitly test the order if overlap is unavoidable.

**Mistake 11 — Using `server.servlet.context-path` for WebFlux.**  
That is a Servlet property; for reactive WebFlux, use the appropriate base-path configuration such as `spring.webflux.base-path` and check URLs behind proxies.

**Mistake 12 — Adding `@EnableWebFlux` to "fix" WebFlux starter issues.**  
Boot applications with `starter-webflux` automatically configure infrastructure. `@EnableWebFlux` can alter auto-configuration, so only use it when intentionally taking manual responsibility for configuration.

**Mistake 13 — Trying to set HTTP status after the response has committed.**  
An error occurring after a streaming response has started may no longer be able to change the status. Design streaming protocols carefully, know when commit happens, and handle errors appropriately on the client side.

## 18. Step-by-Step Analysis of a Real WebFlux Request

When a `GET /api/books/7` request does not return the expected result:

1. Confirm the application runs the **WebFlux reactive server**, not Spring MVC due to both starters being present.
2. Check the HTTP host/port, base path, and the request path arriving at the server after any gateway/proxy.
3. Check `WebFilter`/Spring Security: was the request blocked before the dispatcher?
4. Confirm `DispatcherHandler` is configured by Boot and handler-mapping beans are registered.
5. Check whether `RequestMappingHandlerMapping` or `RouterFunctionMapping` matched the request.
6. Check route conditions: path, method, headers, `consumes`, `produces`.
7. Once a handler is selected, check which `HandlerAdapter` returns `true` for `supports(...)`.
8. If argument binding fails, inspect `@PathVariable`/`@RequestBody`, JSON codecs, and validation.
9. If the handler returns a `Publisher`, confirm the pipeline is not blocking, not manually subscribing in a detached branch, and not forgetting `return`.
10. Check which `HandlerResultHandler` writes status, headers, and body.
11. If the response errors or slows down, inspect the event loop, downstream services, timeouts, cancellation, and whether the response is already committed.
12. Use `WebTestClient`, Actuator `mappings`, and controlled logging to verify after fixing.

Do not just put a breakpoint in a controller and assume every bug lives there. In WebFlux, failures can happen before a handler is selected or during `Publisher` execution after the controller method has already returned.

## 19. Self-Check Questions

**Question 1. Is DispatcherHandler a Servlet?**  
No. `DispatcherHandler` belongs to Spring WebFlux and implements `WebHandler`; `DispatcherServlet` belongs to the Spring MVC/Servlet stack.

**Question 2. Why do both `@RestController` and `RouterFunction` work?**  
Because `DispatcherHandler` uses multiple `HandlerMapping`/`HandlerAdapter` pairs: `RequestMappingHandlerMapping` + `RequestMappingHandlerAdapter` for annotated handlers, and `RouterFunctionMapping` + `HandlerFunctionAdapter` for functional endpoints.

**Question 3. Does HandlerMapping serialize JSON?**  
No. It selects the handler. Serialization and writing the body belong to result handling via `HttpMessageWriter`/codecs and the matching `HandlerResultHandler`.

**Question 4. Does HandlerAdapter decide status 201 vs. 200?**  
It executes the handler and returns the corresponding result. Status may come from `ResponseEntity`, metadata, or `ServerResponse`, and is applied by the result handler when writing the response.

**Question 5. Once a controller returns `Mono<Book>`, is the request complete?**  
Not yet. `Mono` is a `Publisher` describing a computation; the runtime still needs to subscribe, produce the data, encode/write the body, and complete the reactive pipeline.

**Question 6. Why does `Mono.just(blockingCall())` still block?**  
Because `blockingCall()` is evaluated immediately by Java as the argument to `just`; defer it with `fromCallable` and use an appropriate scheduler if you must call a blocking dependency.

**Question 7. When should you write a custom HandlerMapping and HandlerAdapter?**  
When the application genuinely introduces a new handler type or mapping strategy that annotated or functional APIs cannot satisfy; you must control ordering, result handling, and testing.

**Question 8. What does WebTestClient verify?**  
It can send requests through the WebFlux pipeline to verify routes, status, body, headers, and behavior; verifying actual connectors/networking requires an integration test against a real server.

## 20. Summary

Remember the chain of responsibility:

**DispatcherHandler coordinates → HandlerMapping finds the handler → HandlerAdapter invokes the handler → HandlerResultHandler writes the result.**

In Spring WebFlux, the same pipeline handles both annotated controllers and functional routes via different mapping and adapter strategies. `ServerWebExchange` carries request/response context; `Mono`/`Flux` describe asynchronous work; `WebFilter`s handle cross-cutting concerns; and error-handling mechanisms handle emitted failures.

Understanding the exact boundaries among the three core components helps you read stack traces, test routes, diagnose 404/405/406/415, pick the right extension points, and avoid confusing the WebFlux reactive server with Spring MVC Servlet. In a standard Spring Boot application, **you do not need to manually instantiate `DispatcherHandler` or `HandlerAdapter`**: simply declare controllers/functional routes on the right stack, return `Publisher`s consistently, and verify HTTP behavior with `WebTestClient`.

## 21. Official Reference Documentation

- Spring Framework WebFlux — DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
- Spring Framework WebFlux — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework WebFlux — Functional Endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework WebFlux — WebHandler API and HTTP adapters: https://docs.spring.io/spring-framework/reference/web/webflux/web-handler-api.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework Testing — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
