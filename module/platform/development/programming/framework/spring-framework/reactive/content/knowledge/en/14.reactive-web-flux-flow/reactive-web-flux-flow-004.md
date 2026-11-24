# DispatcherHandler and the Dispatching Mechanism in Spring WebFlux

> **Module:** Spring Framework – reactive · **Parent topic:** WebFlux processing flow. This lesson follows the lifecycle of an HTTP request through `DispatcherHandler`: from `HttpHandler`, `WebFilter`, `HandlerMapping`, `HandlerAdapter`, and `HandlerResult`, to `HandlerResultHandler` and the response writer. It compares annotated controllers with functional endpoints, error handling, configuration, a runnable Spring Boot 4.0.9 / Java 17+ example, and HTTP integration tests.

## 1. Learning objectives

After this lesson, you can:

1. Explain why `DispatcherHandler` is the **front controller** of Spring WebFlux and its role in the `WebHandler` chain.
2. Draw the request lifecycle: server adapter → `HttpHandler` → `WebExceptionHandler`/`WebFilter` → `DispatcherHandler` → mapping → adapter → result handler → HTTP response.
3. Distinguish the three core contracts: `HandlerMapping`, `HandlerAdapter`, and `HandlerResultHandler`.
4. Explain what roles `HandlerResult`, `ServerWebExchange`, `Mono<Void>`, `HttpMessageReader`, and `HttpMessageWriter` play.
5. Understand that annotated controllers (`@RestController`) and WebFlux.fn (`RouterFunction`/`HandlerFunction`) use the **same dispatch mechanism**, while choosing different mappings, adapters, and result handlers.
6. Identify at which layer an exception is handled when it occurs before a handler is found, while invoking the handler, or while writing the response.
7. Customize WebFlux appropriately using `WebFluxConfigurer`, `WebFilter`, `WebExceptionHandler`, and custom special beans.
8. Run a Java 17+ application and test routes, errors, and 404s with HTTP integration tests without calling `subscribe()`/`block()` in controllers.

**One memorable sentence:** `DispatcherHandler` coordinates *who handles the request* and *who turns the result into a response*; by itself, it does not contain all controller logic, codecs, or server sockets.

## 2. What is DispatcherHandler?

Spring WebFlux uses the **Front Controller pattern**, similar in idea to `DispatcherServlet` in Spring MVC. A central `DispatcherHandler` receives a `ServerWebExchange`, finds a suitable handler, picks an adapter to invoke the handler, and picks a result handler to complete the response.

`DispatcherHandler`:
- Is a `WebHandler` in the package `org.springframework.web.reactive`.
- Implements `ApplicationContextAware` to read delegate beans from the Spring `ApplicationContext`.
- Discovers special beans according to WebFlux contracts: `HandlerMapping`, `HandlerAdapter`, `HandlerResultHandler`.
- Is usually registered with the bean name **`webHandler`**, so `WebHttpHandlerBuilder` finds it when building the HTTP chain.
- Is preconfigured when using WebFlux Config / `@EnableWebFlux`; Spring Boot auto-configures most of the infrastructure when the WebFlux starter is present.

It is not a renamed `DispatcherServlet`. WebFlux processes according to a reactive contract: request/response use `ServerWebExchange`, handlers typically return `Mono`/`Flux`, completion is represented by `Mono<Void>`, and the server can run on Reactor Netty or other supported runtimes. There is no mandatory dedicated thread per request; non-blocking behavior depends on both the connector and the application code not locking the event loop.

### 2.1. The processing chain at the HTTP level

Before a request reaches `DispatcherHandler`, Spring builds a chain wrapping `WebHandler`:

~~~text
HTTP server (e.g. Reactor Netty)
          |
          v
      HttpHandler
          |
          v
 WebExceptionHandler chain
          |
          v
    WebFilter chain
          |
          v
   DispatcherHandler
          |
          v
    HandlerMapping
          |
          v
    HandlerAdapter
          |
          v
      HandlerResult
          |
          v
  HandlerResultHandler
          |
          v
ServerHttpResponse / HttpMessageWriter
          |
          v
HTTP response
~~~

`WebHttpHandlerBuilder` has two responsibilities: assembling a target `WebHandler` with `WebFilter`s, and then with `WebExceptionHandler`s; and turning that chain into a low-level `HttpHandler` for the server adapter to use. In the request direction, exception handlers wrap the filter chain and the target handler; responses/errors flow back out through the outer layers reactively.

**Distinguishing the layers:**

| Component | Responsibility |
| --- | --- |
| `HttpHandler` | Low-level HTTP abstraction, not directly tied to a specific server. |
| `WebHandler` | Contract for handling `ServerWebExchange`; `DispatcherHandler` is an implementation. |
| `WebFilter` | Intercepts/wraps request-response before and after `WebHandler`, e.g. security, CORS, correlation ID. |
| `WebExceptionHandler` | Handles exceptions arising in the filter chain or the target `WebHandler`. |
| `DispatcherHandler` | Coordinates mapping, invocation, and result handling. |
| Server adapter | Connects `HttpHandler` to the actual HTTP runtime. |

`ServerWebExchange` is the context for one HTTP request/response, containing `ServerHttpRequest`, `ServerHttpResponse`, session, attributes, principal, and resolved request information. Handlers and filters use the same exchange to coordinate without passing each object separately through a series of methods.

### 2.2. `DispatcherHandler` is not the place to write business logic

Do not put database queries, pricing calculations, or business rules directly inside a custom `DispatcherHandler`. Business logic belongs in services/domain; a controller or `HandlerFunction` calls the service and returns a Publisher. `DispatcherHandler` keeps the general dispatch algorithm so different kinds of handlers work together.

## 3. The three core delegates

`DispatcherHandler` looks up three groups of beans in the ApplicationContext. Each group has its own contract.

### 3.1. HandlerMapping — finding a handler for the request

Main contract:

~~~java
Mono<Object> getHandler(ServerWebExchange exchange);
~~~

`HandlerMapping` receives the exchange and returns a `Mono` containing the handler if found, or completes empty if that mapping does not match. There are several ways to find a handler, for example:
- `RequestMappingHandlerMapping`: finds methods in `@Controller`/`@RestController` based on `@RequestMapping`, `@GetMapping`, HTTP method, path, headers, params, `consumes`, `produces`, and other mapping conditions.
- `RouterFunctionMapping`: finds routes declared with WebFlux.fn (`RouterFunction`).
- `SimpleUrlHandlerMapping`: maps URL patterns to specific `WebHandler`s, commonly used for static resources and resource handlers.

`DispatcherHandler` queries the `HandlerMapping`s in sorted order; **the first mapping that returns a matching handler wins**. If a mapping returns `Mono.empty()`, it moves on to the next mapping. Therefore, the order of custom mappings can affect which route wins.

**Having a similar-looking URL does not automatically mean a mapping is chosen.** A mapping also checks the method, headers, media type, query parameters, path pattern, version, or configured conditions. CORS/preflight may also be checked during mapping.

### 3.2. HandlerAdapter — invoking the chosen handler

Contract:

~~~java
boolean supports(Object handler);

Mono<HandlerResult> handle(
    ServerWebExchange exchange, Object handler);
~~~

A `HandlerAdapter` knows how to **invoke a specific kind of handler**, so `DispatcherHandler` does not have to understand every programming model. The adapter checks `supports(handler)`, then invokes the handler and returns a `Mono<HandlerResult>`. The adapter may also return an empty Mono if the request has already been handled completely and does not need the normal result-handling step.

Some common adapters:

| HandlerAdapter | Supported handler | Role |
| --- | --- | --- |
| `RequestMappingHandlerAdapter` | Handler methods from annotated controllers | Resolves arguments, invokes controller methods, handles reactive return values. |
| `HandlerFunctionAdapter` | `HandlerFunction<ServerResponse>` | Invokes WebFlux.fn handler functions. |
| `SimpleHandlerAdapter` | Handlers of type `WebHandler` | Directly invokes a mapped WebHandler. |
| `WebSocketHandlerAdapter` | `WebSocketHandler` | Delegates WebSocket handling according to the corresponding contract. |

The adapter is the boundary that lets the same dispatcher support annotations, functional endpoints, resources, and extensible handler types.

### 3.3. HandlerResult — wrapping the invocation result

`HandlerResult` carries the information needed to handle the result:
- The handler that was invoked.
- The actual return value (which may be an object or a reactive type).
- The declared return type via `ResolvableType`/`MethodParameter`.
- `BindingContext` and model in cases that require data binding/views.
- The `DispatchExceptionHandler` mechanism if the adapter provides error handling for asynchronous results.

**The declared return type matters a lot.** `Mono<Item>`, `ResponseEntity<Mono<Item>>`, `Flux<Item>`, `String`, or `ServerResponse` can be processed by result handlers under different contracts. HandlerResult keeps both the return value and the metadata needed to choose.

### 3.4. HandlerResultHandler — turning HandlerResult into a response

Main contract:

~~~java
boolean supports(HandlerResult result);

Mono<Void> handleResult(
    ServerWebExchange exchange, HandlerResult result);
~~~

The dispatcher finds the first `HandlerResultHandler` that supports the result. This handler writes status/headers/body directly or renders a view; `Mono<Void>` completes when response processing finishes.

Common default result handlers:

| HandlerResultHandler | Return values typically handled | Default order |
| --- | --- | ---: |
| `ResponseEntityResultHandler` | `ResponseEntity`, usually from a controller | 0 |
| `ServerResponseResultHandler` | `ServerResponse` from functional endpoints | 0 |
| `ResponseBodyResultHandler` | `@ResponseBody`, `@RestController` | 100 |
| `ViewResolutionResultHandler` | `CharSequence`, `View`, `Model`, `Map`, `Rendering`, or model attributes | `Integer.MAX_VALUE` |

Order and `supports` work together: two result handlers can have the same order while accepting different result types. `ResponseEntityResultHandler` handles status/headers/body from ResponseEntity; `ResponseBodyResultHandler` writes `@ResponseBody` bodies; `ServerResponseResultHandler` writes ServerResponse; `ViewResolutionResultHandler` resolves Views when the application renders HTML.

## 4. Step-by-step dispatch flow

This is the general sequence for a normal request:

1. **The server receives the request.** Reactor Netty or a server adapter receives the HTTP bytes and invokes `HttpHandler`.
2. **Creates the Web exchange.** `HttpWebHandlerAdapter` converts the request into a `ServerWebExchange`, creating the context for the request/response.
3. **WebExceptionHandler and WebFilter wrap around.** Exception handlers set up the ability to turn errors into responses; filters can authenticate, log, add headers, or reject the request before dispatch.
4. **DispatcherHandler receives the exchange.** It uses the list of `HandlerMapping`s discovered from the ApplicationContext.
5. **Finds a handler.** Each mapping is queried; the first matching result is used. If no mapping returns a handler, the request has no matching route and by default goes to a 404 error.
6. **Chooses a HandlerAdapter.** The dispatcher finds an adapter whose `supports(handler)` is true, then calls `handle(exchange, handler)`.
7. **Produces a HandlerResult.** The adapter resolves arguments and invokes the controller/function/WebHandler. The invocation result is wrapped into a `HandlerResult`.
8. **Chooses a HandlerResultHandler.** The dispatcher inspects the result handlers in order and chooses the one that supports the result.
9. **Writes the response.** The result handler sets the status/headers and writes the body via `ServerHttpResponse` or `HttpMessageWriter`, or may render a view. `Mono<Void>` represents when response processing ends.
10. **The filter chain completes.** Outer operators/filters can observe the status, timing, terminal signal, and clean up according to the lifecycle.

~~~mermaid
flowchart TD
    A["HTTP server / HttpHandler"] --> B["WebExceptionHandler chain"]
    B --> C["WebFilter chain"]
    C --> D["DispatcherHandler"]
    D --> E["Query HandlerMapping in order"]
    E --> F{"Matching handler?"}
    F -- "No" --> G["404 / dispatch error"]
    F -- "Yes" --> H["Find HandlerAdapter.supports"]
    H --> I["Adapter.invoke → Mono<HandlerResult>"]
    I --> J["Find HandlerResultHandler.supports"]
    J --> K["Write status, headers, body, or render View"]
    K --> L["Mono<Void> completes response"]
    G --> M["Exception handling"]
~~~

The dispatcher does not wait on a dedicated synchronous thread for the entire request. Each step can return a Publisher and only executes as the subscription progresses; reactive I/O can complete later. **Do not call `block()` or `subscribe()` yourself in a controller/service** to wait for a result before returning the response.

## 5. How does an annotated controller go through DispatcherHandler?

Given:

~~~java
@RestController
@RequestMapping("/api/items")
class ItemController {

    @GetMapping("/{id}")
    Mono<Item> get(@PathVariable String id) {
        return service.findById(id);
    }
}
~~~

Typical flow:
1. `RequestMappingHandlerMapping` finds the handler method matching `/api/items/{id}` and GET.
2. `RequestMappingHandlerAdapter` prepares the invocation: resolves `@PathVariable`, `@RequestBody`, `@RequestHeader`, `Principal`, `ServerWebExchange`, validation, and appropriate argument resolvers.
3. The adapter invokes the controller method. The return value `Mono<Item>` is placed in HandlerResult along with return-type metadata.
4. `ResponseBodyResultHandler` receives the return value of `@RestController`.
5. An appropriate `HttpMessageWriter` (for example the Jackson JSON encoder) writes the Item to the response; `Mono<Void>` terminates when the response has been written.

**Important point:** the controller method can return `Mono<Item>` as soon as the pipeline is constructed. The Item value is produced later when the service Publisher emits; the adapter/result handler coordinate according to the reactive contract. The controller does not need to wait for `Item` and then return a synchronous object.

### 5.1. Mapping conditions

A method can be selected based on many conditions:

~~~java
@GetMapping(
    path = "/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE)
Mono<Item> getJson(@PathVariable String id) {
    return service.findById(id);
}
~~~

The attributes `path`, `method`, `params`, `headers`, `consumes`, `produces`, and mapping conditions are used to identify the method. For example:
- A mismatched HTTP method can produce a method-not-allowed error.
- `consumes` not matching Content-Type can lead to 415.
- `produces` not matching Accept can lead to 406.
- A path with no matching handler can become 404.

The exact mapping depends on configuration and competing routes; you should not create two methods with ambiguous conditions and rely on declaration order in the Java file.

## 6. Functional endpoints also use DispatcherHandler

WebFlux.fn separates routes from handlers. Instead of declaring `@GetMapping`, we create a `RouterFunction` and `HandlerFunction`:

~~~java
@Bean
RouterFunction<ServerResponse> itemRoutes(ItemHandler handler) {
    return RouterFunctions.route()
        .GET("/api/functional/items/{id}", handler::get)
        .build();
}
~~~

~~~java
@Component
class ItemHandler {
    Mono<ServerResponse> get(ServerRequest request) {
        String id = request.pathVariable("id");
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new Item(id, "Item " + id));
    }
}
~~~

The two fragments above require Spring WebFlux, the `Item` type, and the `ItemHandler` bean. Mechanism:
1. `RouterFunctionMapping` evaluates the RouterFunction and selects the `HandlerFunction`.
2. `HandlerFunctionAdapter` invokes the function with `ServerRequest`.
3. The function returns `Mono<ServerResponse>`.
4. `ServerResponseResultHandler` receives the ServerResponse and writes the response.

**Functional endpoints do not bypass DispatcherHandler.** They only change how handlers are declared; mapping, adapter, result handling, and the WebHandler chain still use the same foundation. You can use annotated controllers and functional routes in the same application as long as routes do not conflict.

### 6.1. Comparing the two models

| Aspect | Annotated controller | WebFlux.fn |
| --- | --- | --- |
| Route declaration | `@RequestMapping`, `@GetMapping`, ... | `RouterFunction` / `RequestPredicate` |
| Handler | Method on `@Controller` | `HandlerFunction<ServerResponse>` |
| Default mapping | `RequestMappingHandlerMapping` | `RouterFunctionMapping` |
| Default adapter | `RequestMappingHandlerAdapter` | `HandlerFunctionAdapter` |
| Common result handler | `ResponseEntityResultHandler`, `ResponseBodyResultHandler` | `ServerResponseResultHandler` |
| Getting parameters | `@PathVariable`, `@RequestBody`, `@RequestHeader`... | `ServerRequest.pathVariable`, `bodyToMono`, headers... |
| Best suited for | Familiar API controllers, annotations/argument resolvers | Explicit routes, functional composition, small route modules |

### 6.2. Mapping order in Spring Boot

In the default Spring Boot configuration, the order is usually set as:
1. `RouterFunctionMapping` for `RouterFunction` beans.
2. `RequestMappingHandlerMapping` for `@Controller`/`@RestController`.
3. A `RouterFunctionMapping` for the welcome page if present.

Because `DispatcherHandler` picks the **first match**, declaring the same path/method in both models can cause route shadowing. Avoid duplicate routes or configure order intentionally; do not assume annotated routes always beat functional routes. For a custom `HandlerMapping`, implement `Ordered`/`@Order` with a clear goal.

## 7. Result handling, bodies, and codecs

`HandlerResultHandler` decides how to interpret the return value, while codecs are responsible for converting Java data ↔ HTTP bytes.

| Direction | Contract | Example |
| --- | --- | --- |
| Read request body | `HttpMessageReader` | JSON request → `Mono<CreateItemRequest>` |
| Write response body | `HttpMessageWriter` | `Mono<Item>` → JSON bytes |
| Write custom response | `ServerHttpResponse` | Direct headers/status/body |
| Render HTML | `ViewResolver` + `View` | logical view name → template |

Controller example:

~~~java
@PostMapping("/items")
Mono<ResponseEntity<Item>> create(
        @Valid @RequestBody Mono<CreateItemRequest> request) {
    return request
        .flatMap(service::create)
        .map(item -> ResponseEntity
            .created(URI.create("/api/items/" + item.id()))
            .body(item));
}
~~~

This is a fragment that requires the types `CreateItemRequest`, `Item`, service, and imports. `HttpMessageReader` decodes the request body; argument resolution supplies `Mono<CreateItemRequest>`; the service creates the Item; the result handler processes `ResponseEntity<Item>` to write status 201, Location, and the JSON body.

**Reactive return values:**
- `Mono<T>` represents at most one value.
- `Flux<T>` represents multiple values; a suitable writer can stream elements instead of having to collect them all.
- `Mono<Void>` usually represents an operation that only needs to complete, with no body.
- `ResponseEntity<T>` carries status/headers/body; it can be combined with a reactive body according to supported APIs.
- `ServerResponse` is the response model of functional endpoints.

Content negotiation relies on `Accept`, `produces`, the return value type, and supported codecs. If the response is a stream (SSE, NDJSON, or an appropriate media type), the writer can write incrementally and apply backpressure. If the response has already started writing bytes before an error occurs, the server cannot simply replace the whole body/status like an uncommitted response; stream error handling must be designed separately.

## 8. Where are exceptions handled?

Errors can happen at many stages, so you must choose the right layer:

| Where the error occurs | Suitable handling mechanism |
| --- | --- |
| Before a handler is selected: filter, mapping, dispatch | `WebExceptionHandler`; adapters may implement `DispatchExceptionHandler` for some dispatch errors |
| While invoking a controller method | The adapter and the annotated controller's exception handlers, typically `@ExceptionHandler`/`@ControllerAdvice` |
| After the controller returns a Mono/Flux and the Publisher emits an error | The exception handler attached to HandlerResult can handle it if the response can still be changed |
| While the result handler/codec writes the response | `DispatchExceptionHandler`/WebExceptionHandler depending on stage; if the response is already committed, status/body already sent cannot be changed |
| No handler found | Default dispatch leads to 404 |

### 8.1. `@ControllerAdvice` is not a global handler for every error

`@ExceptionHandler` inside a controller or `@RestControllerAdvice` is tied to handler invocation and can also handle deferred errors from reactive return values according to WebFlux's mechanism. However, **do not use `@ControllerAdvice` as the sole way to handle errors occurring before a handler is selected**, such as errors in a `WebFilter` or `HandlerMapping`. Those errors belong to the WebHandler exception chain/`WebExceptionHandler` or the appropriate `DispatchExceptionHandler`.

### 8.2. WebExceptionHandler

`WebExceptionHandler` handles exceptions in the chain of `WebFilter`s and the target `WebHandler`. WebFlux Config includes `ResponseStatusExceptionHandler`; `WebFluxResponseStatusExceptionHandler` also inspects `@ResponseStatus` on exceptions. You can register beans and use `@Order`/`Ordered` to control order when multiple handlers participate.

**Do not catch every Throwable and always return 200.** Keep the right status, log/trace the correlation ID, avoid exposing stack traces/secrets, and do not write the response a second time after the response has been committed.

### 8.3. DispatchExceptionHandler

`DispatchExceptionHandler` provides a way to handle errors in the dispatch pipeline. A `HandlerAdapter` can:
- Handle invocation errors right inside `handle`.
- Attach an exception handler to `HandlerResult` to handle errors emitted late while processing the return value or writing the response.
- Implement `DispatchExceptionHandler` to participate in handling errors that occur before a handler is chosen, such as mapping errors or earlier filter errors.

This is an important difference in WebFlux: errors from `Mono`/`Flux` can happen **after the controller method has already returned**, so you cannot just use synchronous `try/catch` around the method call to catch every error.

## 9. How do WebFilter, HandlerInterceptor, and mappings differ?

- **WebFilter** wraps the entire WebHandler chain. Use it for security, CORS, request IDs, logging, metrics, and broadly applied cross-cutting concerns.
- **HandlerInterceptor** is tied to processing the selected handler, usually per `HandlerMapping`; suitable for pre/post logic on specific handlers.
- **HandlerMapping** finds the handler; it is not the place to execute business methods.
- **HandlerAdapter** invokes the chosen handler; it does not decide the route.
- **HandlerResultHandler** writes/interprets the result; it does not choose the controller method.

Example of a filter that records timing:

~~~java
@Component
class RequestTimingFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        long start = System.nanoTime();

        return chain.filter(exchange)
            .doFinally(signal -> {
                long elapsedMs =
                    (System.nanoTime() - start) / 1_000_000;
                System.out.printf("%s %s -> %s (%s, %d ms)%n",
                    exchange.getRequest().getMethod(),
                    exchange.getRequest().getURI().getPath(),
                    exchange.getResponse().getStatusCode(),
                    signal,
                    elapsedMs);
            });
    }
}
~~~

This is a component fragment that can be added to a WebFlux application. `doFinally` runs on complete/error/cancel, so it is useful for observing the exchange lifecycle; `getStatusCode()` may not be set yet if an error occurred very early. The callback must be fast, must not block the event loop, and must not open an independent subscription to write logs.

## 10. Configuring WebFlux and special beans

### 10.1. Spring Boot auto-configuration

When `spring-boot-starter-webflux` is present, Boot configures the default beans: DispatcherHandler, HandlerMapping, HandlerAdapter, HandlerResultHandler, codecs, static resource handling, and server integration. For most applications, add a `WebFluxConfigurer` for needed customizations.

**If you want to keep Boot's auto-configuration:** declare a `WebFluxConfigurer` bean, but **do not add `@EnableWebFlux`**. `@EnableWebFlux` gives the application full control over WebFlux configuration; when present, Boot no longer applies all default WebFlux auto-configuration. Only choose this approach when you intentionally manage the infrastructure yourself.

### 10.2. Configuring codecs

~~~java
@Configuration
class ApiWebConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
            .maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

This fragment limits the default codec buffer size to 2 MiB; the value must fit the payload and application requirements. This is an example of `WebFluxConfigurer` that preserves Boot auto-configuration. Do not increase the buffer unboundedly to hide oversized-payload errors.

### 10.3. Custom HandlerMapping/Adapter/ResultHandler

You can declare custom special beans if you need a custom route or handler style. Before writing your own, check:
- Can it be solved with `RouterFunction`/annotated controllers?
- Does the custom `HandlerMapping` specify an order and return `Mono.empty()` properly when it does not match?
- Does the custom `HandlerAdapter` handle both synchronous and deferred reactive exceptions?
- Does the custom `HandlerResultHandler` implement `supports` strictly and return `Mono<Void>` only once the response has been handled?
- Are backpressure, cancellation, codecs, and content negotiation preserved properly?

A custom mapping placed too early can shadow default routes; a result handler whose `supports` is too broad can mistakenly pick up another controller's return value. This is a powerful extension point, but it should be used when the handler model truly differs from the standard models.

## 11. Runnable example: Spring Boot 4.0.9 + Java 17

The example below has two endpoints both working through DispatcherHandler:
- `/api/annotated/{id}` uses an annotated controller.
- `/api/functional/{id}` uses WebFlux.fn.
- `/api/annotated/fail` produces an error to show `@RestControllerAdvice`.
- A filter logs the request path, status, and duration.

### 11.1. Project structure

~~~text
dispatcher-handler-demo/
├── pom.xml
├── src/main/java/com/example/dispatch/DispatchApplication.java
├── src/main/java/com/example/dispatch/Item.java
├── src/main/java/com/example/dispatch/ItemController.java
├── src/main/java/com/example/dispatch/FunctionalRoutes.java
├── src/main/java/com/example/dispatch/ApiExceptionHandler.java
├── src/main/java/com/example/dispatch/RequestTimingFilter.java
└── src/test/java/com/example/dispatch/DispatchIntegrationTest.java
~~~

### 11.2. pom.xml

Boot 4.0.9 requires Java 17 or higher and Maven 3.6.3 or higher. The WebFlux starter provides the reactive web stack and embedded server integration; Spring Boot manages compatible Spring Framework/Reactor versions.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>dispatcher-handler-demo</artifactId>
    <version>1.0.0</version>
    <name>dispatcher-handler-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.3. `DispatchApplication.java`

~~~java
package com.example.dispatch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DispatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(DispatchApplication.class, args);
    }
}
~~~

### 11.4. `Item.java`

~~~java
package com.example.dispatch;

public record Item(String id, String name) {}
~~~

### 11.5. `ItemController.java` — annotated route

~~~java
package com.example.dispatch;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/annotated")
public class ItemController {

    @GetMapping("/{id}")
    public Mono<Item> find(@PathVariable String id) {
        return Mono.just(new Item(id, "Item " + id));
    }

    @GetMapping("/fail")
    public Mono<Item> fail() {
        return Mono.error(new IllegalArgumentException("invalid item"));
    }
}
~~~

Here `RequestMappingHandlerMapping` selects the method; `RequestMappingHandlerAdapter` resolves `@PathVariable` and invokes the method; `ResponseBodyResultHandler` writes `Mono<Item>` as JSON. The `fail()` method returns an asynchronous error Mono, letting WebFlux exception handling handle it according to the handler context.

### 11.6. `FunctionalRoutes.java` — functional route

~~~java
package com.example.dispatch;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> itemRoutes() {
        return RouterFunctions.route()
            .GET("/api/functional/{id}", request -> {
                String id = request.pathVariable("id");
                Item item = new Item(id, "Item " + id);
                return ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(item);
            })
            .build();
    }
}
~~~

`RouterFunctionMapping` finds the route; `HandlerFunctionAdapter` invokes the lambda; `ServerResponseResultHandler` writes `ServerResponse`. Both the annotated and functional endpoints are served by the same DispatcherHandler and the same HTTP server.

### 11.7. `ApiExceptionHandler.java`

~~~java
package com.example.dispatch;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badRequest(
            IllegalArgumentException exception) {
        return ResponseEntity.badRequest().body(
            Map.of("error", exception.getMessage()));
    }
}
~~~

This advice handles errors from controller/handler invocations. If an error happens in a WebFilter before a handler is selected, a `WebExceptionHandler` at the WebHandler chain layer is needed; do not expect this advice to cover every server error.

### 11.8. `RequestTimingFilter.java`

~~~java
package com.example.dispatch;

import org.springframework.core.annotation.Order;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class RequestTimingFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        long start = System.nanoTime();

        return chain.filter(exchange)
            .doFinally(signal -> {
                long elapsedMs =
                    (System.nanoTime() - start) / 1_000_000;
                String status = exchange.getResponse().getStatusCode() == null
                    ? "unset"
                    : String.valueOf(
                        exchange.getResponse().getStatusCode().value());

                System.out.printf("%s %s -> %s (%s, %d ms)%n",
                    exchange.getRequest().getMethod(),
                    exchange.getRequest().getURI().getPath(),
                    status,
                    signal,
                    elapsedMs);
            });
    }
}
~~~

The filter is applied around the dispatcher. `LOWEST_PRECEDENCE` here is just a choice for the demo; applications with Spring Security, CORS, or other filters need to design order according to security policy and actual execution order. Do not make log or metrics callbacks blocking operations.

### 11.9. Running the application

In the directory containing `pom.xml`, check:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

By default the application listens on port 8080 if configuration is not changed.

Try the annotated endpoint:

~~~bash
curl -i http://localhost:8080/api/annotated/42
~~~

Expected JSON body:

~~~json
{"id":"42","name":"Item 42"}
~~~

Try the functional endpoint:

~~~bash
curl -i http://localhost:8080/api/functional/42
~~~

Expected JSON body:

~~~json
{"id":"42","name":"Item 42"}
~~~

Try the controller error:

~~~bash
curl -i http://localhost:8080/api/annotated/fail
~~~

Expected status is `400 Bad Request`; the body contains the field `"error":"invalid item"` (JSON fields may be in a different order).

Try an unmapped URL:

~~~bash
curl -i http://localhost:8080/api/not-found
~~~

Expected status is `404 Not Found`. Boot's default error handler may add a JSON/HTML body depending on Accept and error-attribute configuration; do not depend on the exact body unless customized.

**Example log printed by the filter** (times vary by machine):

~~~text
GET /api/annotated/42 -> 200 (ON_COMPLETE, 3 ms)
GET /api/functional/42 -> 200 (ON_COMPLETE, 2 ms)
GET /api/annotated/fail -> 400 (ON_COMPLETE, 4 ms)
~~~

The ms values above are only illustrative; they are not fixed stdout. `ON_COMPLETE` is the filter chain signal after the response has been handled; the controller error was converted into a 400 response by the advice, so the chain can complete normally.

## 12. HTTP integration testing with JUnit 5

Do not only unit test controller methods: an HTTP integration test verifies that the route is mapped, the adapter invokes the right handler, the result handler writes the right response, and the filter/server chain participates.

**src/test/java/com/example/dispatch/DispatchIntegrationTest.java**

~~~java
package com.example.dispatch;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class DispatchIntegrationTest {

    @Value("${local.server.port}")
    int port;

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + path))
            .GET()
            .build();

        return HttpClient.newHttpClient().send(
            request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void annotatedControllerIsDispatchedAndWrittenAsJson()
            throws Exception {
        HttpResponse<String> response = get("/api/annotated/42");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"id\":\"42\""));
        assertTrue(response.body().contains("\"name\":\"Item 42\""));
    }

    @Test
    void functionalEndpointUsesTheSameHttpPipeline()
            throws Exception {
        HttpResponse<String> response = get("/api/functional/42");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"id\":\"42\""));
        assertTrue(response.body().contains("\"name\":\"Item 42\""));
    }

    @Test
    void controllerAdviceMapsReactiveHandlerError()
            throws Exception {
        HttpResponse<String> response = get("/api/annotated/fail");

        assertEquals(400, response.statusCode());
        assertTrue(response.body().contains("invalid item"));
    }

    @Test
    void unmappedPathReturnsNotFound() throws Exception {
        HttpResponse<String> response = get("/api/not-found");

        assertEquals(404, response.statusCode());
    }
}
~~~

The test uses `java.net.http.HttpClient` built in since JDK 11 so it does not depend on a specific test client API. `RANDOM_PORT` starts a real server on a random port; the test checks the HTTP status and JSON body. To run:

~~~bash
mvn test
~~~

If tests fail, check the startup logs before concluding the dispatcher is broken: a port failing to open, a missing server dependency, conflicting mappings, or the response codec can all be different causes.

## 13. Common mistakes when debugging dispatch

| Symptom | Where to check | How to handle |
| --- | --- | --- |
| Route returns 404 even though controller has annotations | Component scan, `RequestMappingHandlerMapping`, path/base path | Check package scan, HTTP method, path, and mapping conditions. |
| Functional route does not run | `RouterFunction` bean, `RouterFunctionMapping`, order | Ensure the bean is registered and not shadowed by an earlier mapping. |
| Functional and annotated routes have the same URL | HandlerMapping order | Avoid duplicates; if needed, configure order explicitly. |
| Handler is found but fails on invocation | HandlerAdapter, argument resolver, validation, controller | Check `supports`, parameter types, body reader, and method errors. |
| Controller returns Mono but response hangs | Publisher does not emit/complete, service I/O | Check timeout, subscription, backpressure, remote dependency; do not block. |
| JSON cannot be written | HandlerResultHandler, `HttpMessageWriter`, codec/classpath | Check return type, content type, Jackson/codec, and whether response is already committed. |
| `@ControllerAdvice` does not catch filter errors | Error before handler selection | Use the appropriate `WebExceptionHandler`. |
| Exception occurs after stream has already sent a partial response | Response already committed | Design a stream error protocol; do not expect to change already-sent status/body. |
| Static resource not found | `SimpleUrlHandlerMapping`, resource location | Check classpath `/static`, resource patterns, and resource configuration. |
| WebFlux runs as MVC unexpectedly | Dependencies and Boot web application type | Avoid adding `spring-boot-starter-web` as well if you want a reactive server; if using both intentionally, configure application type explicitly. |
| Event loop becomes slow | Blocking in handler/service/filter | Use reactive clients/drivers or offload blocking sources properly; measure event-loop latency. |
| Filter does not run in expected order | `Ordered`, `@Order`, Security filter chain | Check the entire filter order and security chain. |
| 406/415 even though endpoint exists | `produces`, `consumes`, `Accept`, `Content-Type` | Compare media types against mappings and codecs. |
| HandlerResultHandler does not support the return value | Return type and result handler `supports` | Return a supported WebFlux type or add a result handler with a specific contract. |

### 13.1. Debugging at the right layer

Do not immediately edit the controller when you see HTTP 404. Check in turn:
1. Did the server receive the request?
2. Could any filter have stopped the request before the dispatcher?
3. Which mapping was queried and did it return a handler?
4. What type is the chosen handler; which adapter supports it?
5. Did the adapter resolve arguments and invoke successfully?
6. Does HandlerResult have the expected return value/type?
7. Which result handler supports it and which writer/codec was chosen?
8. Was the response already committed; which exception handler handled the error?

Setting a breakpoint or logging at the right contract finds the cause faster than turning on overly broad logging for the entire framework.

## 14. Customizing without breaking the pipeline

**Usually start with high-level extension points:**
- `WebFluxConfigurer`: codecs, CORS, formatters, view resolvers, path matching, and API versioning.
- `WebFilter`: cross-cutting concerns for every request.
- `@ControllerAdvice`: exceptions/validation for annotated controllers.
- `RouterFunction`: functional routes for a group of endpoints.
- `WebExceptionHandler`: errors at the WebHandler chain level.
- Custom `HandlerMapping`/`HandlerAdapter`/`HandlerResultHandler`: only when a new handler/return contract type is needed.

Do not create another `DispatcherHandler` bean yourself when Boot already configures one, unless you fully understand the infrastructure and have a specific goal to replace it. Multiple duplicate beans can change mapping/adapter order or send requests to the wrong handler.

### 14.1. WebFlux Config and `@EnableWebFlux`

| Configuration approach | Suitable for |
| --- | --- |
| Spring Boot starter + `WebFluxConfigurer` | Keep auto-configuration, only customize codecs/CORS/formats... |
| `@EnableWebFlux` | Control WebFlux infrastructure yourself and do not want Boot to configure defaults for you |
| Custom special beans | Need a new mapping/adapter/result contract, and understand order/lifecycle |

If you need a global handler to record a correlation ID, prefer a filter. If you need to change how JSON is serialized, configure codecs/writers. Do not rewrite DispatcherHandler for a need that has a smaller extension point.

## 15. Reactive execution, backpressure, and cancellation during dispatch

DispatcherHandler orchestrates Publishers rather than turning synchronous code into non-blocking code. A controller can return `Mono<Item>` yet call synchronous JDBC or `Thread.sleep` inside; in that case the request still blocks on the thread executing the method. Use reactive repositories/WebClient or bridge legacy blocking via `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` with bounded load.

`HandlerResultHandler` writes `Flux<T>` using the appropriate writer. When the client is slow, backpressure and network flow control affect write speed. For streaming responses:
- Set appropriate timeouts and cleanup.
- Handle cancel when the client disconnects.
- Do not keep unbounded buffers.
- Do not treat client disconnection as a rollback of the business operation.
- If the response has already been partially written, a subsequent error usually ends the stream/connection; the initial status code cannot be resent.

`Mono<Void>` from `WebHandler`/`HandlerResultHandler` represents **request/response processing completing**. It is not a waiting thread or a synchronous `void`; the framework subscribes and tracks the terminal signal.

## 16. Quick summary table

| Question | Answer |
| --- | --- |
| Who receives the request and dispatches? | `DispatcherHandler` |
| Who finds the controller/route? | `HandlerMapping` |
| Who invokes the chosen handler type? | `HandlerAdapter` |
| Where is the invocation result packaged? | `HandlerResult` |
| Who writes the body/status or renders the view? | `HandlerResultHandler` |
| Which bean does annotated mapping use? | `RequestMappingHandlerMapping` |
| Which bean does functional mapping use? | `RouterFunctionMapping` |
| Which adapter invokes an annotated method? | `RequestMappingHandlerAdapter` |
| Which adapter invokes a functional handler? | `HandlerFunctionAdapter` |
| What usually handles `Mono<Item>` in `@RestController`? | `ResponseBodyResultHandler` |
| What handles `ServerResponse` from WebFlux.fn? | `ServerResponseResultHandler` |
| Where do common filters run? | `WebFilter` in the chain wrapping `DispatcherHandler` |
| Errors before a handler is selected? | Suitable `WebExceptionHandler`/`DispatchExceptionHandler` |
| Errors inside a controller? | Adapter/`@ExceptionHandler`/`@ControllerAdvice` |
| No mapping found? | Default 404 |
| What type does the server chain complete with? | `Mono<Void>` |

## 17. Practice exercises

**Exercise 1 – Trace an annotated request.** Send GET `/api/annotated/42`; note the names of the HandlerMapping, HandlerAdapter, and HandlerResultHandler used. **Answer:** RequestMappingHandlerMapping → RequestMappingHandlerAdapter → ResponseBodyResultHandler.

**Exercise 2 – Trace a functional endpoint.** Send GET `/api/functional/42`; compare with Exercise 1. **Answer:** RouterFunctionMapping → HandlerFunctionAdapter → ServerResponseResultHandler. Both still go through DispatcherHandler.

**Exercise 3 – Create a route conflict.** Declare the same path/method in RouterFunction and an annotated controller. Observe which mapping is chosen with Boot's default order. **Answer:** RouterFunctionMapping is ordered before RequestMappingHandlerMapping according to the default order published by Boot; avoid relying on route overlap in real applications.

**Exercise 4 – Error before handler.** Create a WebFilter that emits `Mono.error(...)` before `chain.filter(exchange)`. Identify why `@ControllerAdvice` is not the only place to catch errors. **Answer:** the error happens before a controller is chosen; a WebExceptionHandler in the WebHandler chain is needed.

**Exercise 5 – Deferred error.** Controller returns `Mono.error(...)`. Try `@RestControllerAdvice`; compare with an error thrown directly in a filter. **Answer:** reactive errors from the handler can be handled by the handler's exception-handler mechanism; filter errors belong to the WebExceptionHandler chain.

**Exercise 6 – Custom codec.** Reduce `maxInMemorySize`, send a large body, and observe the request-reading error. **Answer:** HttpMessageReader/codec enforces the limit; adjust the limit according to requirements but avoid raising it unboundedly.

**Exercise 7 – Response streaming.** Return `Flux<ServerSentEvent<String>>`, disconnect the client midway, and track cancellation/cleanup. **Answer:** the response subscription can be cancelled; source cleanup must be attached to the right lifecycle and external side effects may still have already run.

## 18. Production checklist

- [ ] I understand the chain `HttpHandler → WebExceptionHandler → WebFilter → DispatcherHandler`.
- [ ] Every route has an appropriate mapping and is not shadowed by another route.
- [ ] I know which mapping comes first; custom `Ordered` is intentional.
- [ ] HandlerAdapter matches the handler type, and argument resolvers/codecs are configured.
- [ ] Return types are handled by an appropriate HandlerResultHandler; the corresponding response writer/codec exists.
- [ ] Errors before mapping, inside controllers, and deferred errors have the right exception boundaries.
- [ ] Do not use `@ControllerAdvice` as a global handler for all filter/dispatch errors.
- [ ] Do not block or self-subscribe in controllers/services/filters.
- [ ] Backpressure, timeouts, streaming cancel, and cleanup are tested.
- [ ] Do not modify status/body after the response has committed.
- [ ] Boot WebFlux auto-configuration is preserved if only minor customizations are needed; `@EnableWebFlux` is used only when intentionally managing infrastructure yourself.
- [ ] Integration tests going through the HTTP server verify annotated, functional, error, and 404 routes.

## 19. Official references

1. Spring Framework – `DispatcherHandler`: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
2. Spring Framework – WebFlux Reactive Core / `WebHandler` API: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
3. Spring Framework – Functional Endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
4. Spring Framework – Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
5. Spring Framework Javadoc – `HandlerMapping`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerMapping.html
6. Spring Framework Javadoc – `HandlerAdapter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerAdapter.html
7. Spring Framework Javadoc – `HandlerResult` / `HandlerResultHandler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerResultHandler.html
8. Spring Framework Javadoc – `WebHttpHandlerBuilder`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html
9. Spring Boot 4.0 – Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
10. Spring Boot 4.0 – System Requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html

**Final self-check:** When a request arrives at `/api/functional/42`, who finds the route, who invokes the function, and who writes `ServerResponse`? What happens if the request does not match a mapping? If the controller returns `Mono.error`, where can the exception be handled? If a WebFilter errors before mapping, which mechanism is used? Once you can answer those four questions, you understand the central dispatch flow of Spring WebFlux.
