# `WebHandler`, `WebFilter`, and `WebExceptionHandler` in Spring WebFlux

## 1. Goals and the big picture

Spring WebFlux provides an HTTP processing pipeline based on the reactive model. The three foundational contracts in this lesson are:

- **`WebHandler`**: the component that handles requests at a web layer higher than `HttpHandler`. In a typical WebFlux application, `DispatcherHandler` is the central `WebHandler`.
- **`WebFilter`**: an interceptor component that performs logic before and after the rest of the filter chain and the handler, for example request ID, logging, CORS, or access-condition checks.
- **`WebExceptionHandler`**: the component that receives errors escaping from the `WebFilter` chain or the target `WebHandler`, and then turns the error into an HTTP response if it can handle it.

All three interfaces work with `Mono<Void>` because they describe the **process of handling and writing the response**, not a data value returned to a Java caller. `Mono<Void>` completes when the work finishes; it does not emit a `null` element.

After this lesson, you should understand how Spring assembles these components, read the request/response processing order correctly, write filters that can run before and after the handler, build exception handlers that can handle an error or pass it on, distinguish global error handling from `@ControllerAdvice`, and apply these interfaces in a runnable Spring Boot WebFlux application.

### Which layers does a request pass through?

~~~text
HTTP client
    |
    v
HTTP server (Reactor Netty, Tomcat, Jetty, ...)
    |
    v
Server adapter
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
WebHandler (usually DispatcherHandler)
    |
    +--> HandlerMapping
    |
    +--> HandlerAdapter
    |
    +--> HandlerResultHandler
    |
    v
HTTP response
~~~

`WebHttpHandlerBuilder` assembles a target `WebHandler`, wraps it with `WebFilter`s, and then places the `WebExceptionHandler`s on the outside to handle errors escaping from the chain. As a result, filters can wrap the entire controller/functional endpoint processing, while the exception handlers at the outer layer can observe errors arising in both the filters and the target handler.

## 2. How do `HttpHandler`, `WebHandler`, and `DispatcherHandler` differ?

### 2.1. `HttpHandler`: the lowest HTTP abstraction in Spring WebFlux

`HttpHandler` is a minimal contract for handling one HTTP request and response. It keeps Spring from depending directly on a particular server's own API. Spring has adapters for Reactor Netty, Tomcat, Jetty, and Servlet containers that support non-blocking I/O.

The main role of this layer is to connect the HTTP runtime with Spring's reactive model. A typical application does not need to write its own `HttpHandler`; Spring Boot configures the appropriate adapter and server from the dependencies.

### 2.2. `WebHandler`: request handling at the web level

The contract:

~~~java
public interface WebHandler {
    Mono<Void> handle(ServerWebExchange exchange);
}
~~~

`ServerWebExchange` is the object that represents one HTTP request-response exchange. It provides:

- `getRequest()`: request information, method, URI, headers, body.
- `getResponse()`: sets the status and headers and writes the body.
- `getAttributes()`: a map of attributes bound to the current exchange.
- `getSession()`: access to WebSession.
- `getPrincipal()`: principal information when authentication is integrated.
- `getLocaleContext()`: the request's locale context.
- APIs for reading form data and multipart data via codecs, with a caching mechanism for the corresponding APIs.

`WebHandler` does not force the application to use annotated controllers. An application can implement WebHandler directly or use a higher-level programming model such as annotated controllers and WebFlux.fn.

### 2.3. `DispatcherHandler`: the front controller of a typical WebFlux application

In a standard WebFlux configuration, `DispatcherHandler` is the central `WebHandler`, usually registered under the bean name `webHandler`. It uses special beans to find and invoke the actual handler:

1. `HandlerMapping` finds the handler that matches the request; for example `RequestMappingHandlerMapping` for annotated controllers or `RouterFunctionMapping` for functional routes.
2. `HandlerAdapter` invokes the handler that was found, regardless of whether the handler was declared with annotations or as a functional endpoint.
3. `HandlerResultHandler` processes the result, for example serializing an object to JSON or writing a `ServerResponse`.

`DispatcherHandler` is part of the target WebHandler in the outer chain. You usually configure controllers, routers, filters, and exception handlers as Spring beans so the framework assembles the pipeline. Only declare a replacement WebHandler yourself when you truly want to manage the programming model at a low level.

## 3. `WebFilter`: intervening before and after the processing chain

### 3.1. Contract and meaning

~~~java
public interface WebFilter {
    Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    );
}
~~~

`WebFilterChain` represents the rest of the filter chain and the target `WebHandler`:

~~~java
public interface WebFilterChain {
    Mono<Void> filter(ServerWebExchange exchange);
}
~~~

A filter typically does three things:

1. Reads the request or attaches attributes needed by later processing.
2. Calls `chain.filter(exchange)` to pass the request to the next filter or the target handler.
3. Uses Reactor operators to observe the outcome when the chain completes, emits an error, or is cancelled.

A general example:

~~~java
@Override
public Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
) {
    System.out.println("before");
    return chain.filter(exchange)
        .doOnSuccess(ignored -> System.out.println("success"))
        .doOnError(error -> System.err.println("error=" + error.getMessage()))
        .doFinally(signal -> System.out.println("finished=" + signal));
}
~~~

This is an illustrative example of where callbacks are placed. Because `Mono<Void>` emits no data, the argument of `doOnSuccess` can be `null` according to Reactor's callback contract; do not use it as the response body. `doFinally` runs for completion, error, or cancel paths, so it suits request-end metrics.

### 3.2. Filters run in a nested fashion

Suppose there are two filters A and B, with A ordered before B:

~~~text
A: before
    B: before
        WebHandler
    B: after
A: after
~~~

Filter A wraps the rest of the chain; B wraps the target handler. Therefore:

- On the way in, the filter with the earlier order runs first.
- When the response comes back out, the callbacks after the chain run in reverse order.
- If a filter does not call `chain.filter` and completes the response itself, the inner filters and the target handler will not run.

This is the right mechanism for cross-cutting concerns. Do not use a filter to cram all of a controller's business logic into one interceptor class.

### 3.3. Ordering filters with `@Order` or `Ordered`

When using WebFlux Config/Spring Boot, `WebFilter` beans are detected automatically. You can specify the order with `@Order` or by implementing `Ordered`.

~~~java
@Component
@Order(10)
public class AuditWebFilter implements WebFilter {
    // ...
}
~~~

A smaller order number takes priority first in the sorted list. Order is part of the operational contract: authentication, CORS, request ID, logging, and rate-limit filters may need different positions. For example, the Spring documentation recommends that the CORS filter come before the Spring Security chain so that preflight requests are handled correctly. When adding Spring Security or filters auto-configured by Boot, determine the actual order of each filter instead of relying on the order in which beans are declared in a Java file.

### 3.4. Stopping early or changing the exchange

A filter can block the request before calling the chain:

~~~java
if (exchange.getRequest().getHeaders().getFirst("X-Maintenance") != null) {
    exchange.getResponse().setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
    return exchange.getResponse().setComplete();
}
return chain.filter(exchange);
~~~

If you want to change the request, use the exchange's builder:

~~~java
ServerWebExchange mutated = exchange.mutate()
    .request(builder -> builder.path("/internal"))
    .build();

return chain.filter(mutated);
~~~

These are abbreviated examples; make sure URL/header changes do not break routing, security, or the cache key. Do not call `chain.filter` twice for the same request unless you are implementing a very specific retry/dispatch model and fully understand the side effects.

### 3.5. Reading the request body in a filter requires care

The request body is usually a stream that can be consumed only once. If a filter reads the raw body itself and then still calls `chain.filter(exchange)`, the controller downstream may no longer have data to read. For form data, prefer the `exchange.getFormData()` API because Spring provides a parse/cache mechanism for repeated access. For multipart or streaming bodies, choose the right API and consider memory/backpressure; do not gather the entire body into RAM just to write a log.

## 4. `WebExceptionHandler`: error handling at the WebHandler API layer

### 4.1. The contract

~~~java
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
~~~

The contract of the return value is very important:

- If the handler returns a `Mono<Void>` that completes successfully, Spring considers the error handled.
- If the handler returns `Mono.error(ex)`, the error is still unhandled and is forwarded to the next exception handler.
- If the response cannot be written because it has already been committed, the handler cannot change the status/headers/body of a response that was already sent; it must let the error continue or handle it according to the designed policy.

An exception handler can turn an error into an HTTP status, a JSON error body, a redirect, or an empty response. It does not need to return a JSON object via a generic type; it writes directly to the `ServerHttpResponse` and then returns a `Mono<Void>`.

### 4.2. Writing a selective exception handler

~~~java
@Component
@Order(-2)
public class ApiWebExceptionHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(
        ServerWebExchange exchange,
        Throwable error
    ) {
        if (!(error instanceof CatalogUnavailableException)) {
            return Mono.error(error);
        }

        ServerHttpResponse response = exchange.getResponse();
        if (response.isCommitted()) {
            return Mono.error(error);
        }

        response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] body =
            "{\"error\":\"CATALOG_UNAVAILABLE\"}".getBytes(StandardCharsets.UTF_8);

        DataBuffer buffer = response.bufferFactory().wrap(body);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

`CatalogUnavailableException` is a business exception defined by the application. The handler only handles exactly this type of error. For other errors, it returns `Mono.error(error)` so the next handler has a chance to handle it. For an error where the response is already committed, do not try to write a second JSON onto a response that is being transmitted.

### 4.3. Built-in handlers

Spring WebFlux provides:

- `ResponseStatusExceptionHandler`: handles `ResponseStatusException` by setting the corresponding HTTP status.
- `WebFluxResponseStatusExceptionHandler`: extends support to finding the status from the `@ResponseStatus` annotation on an exception; this handler is registered in WebFlux Config.

In Spring Boot, there is also a default error-handling mechanism that produces an appropriate error response. When adding your own handler, set the order deliberately so the application's exception handler runs at the right position relative to Boot's fallback and WebFlux's default handler. The example in section 10 uses `@Order(-2)` for the application's own business handler.

### 4.4. Do not treat every error as one that can overwrite the response

An exception can occur before the response has started being written or after part of the response has already been sent. The second case is more common with streaming responses such as SSE/NDJSON. Once the response is committed, you cannot change the status from 200 to 500 and replace the entire body with new JSON.

For streaming responses, design the error format into the stream protocol if needed; if the connection is already closed, logging/metrics and cleanup are all that remain. Do not assume `WebExceptionHandler` can always produce a complete error response.

## 5. Chain assembly order and the role of `WebHttpHandlerBuilder`

### 5.1. How does the builder assemble the components?

`WebHttpHandlerBuilder` can be created from a Spring `ApplicationContext` to auto-detect:

- A target `WebHandler` with the bean name `webHandler`.
- Zero or more `WebFilter` beans; sorted by order.
- Zero or more `WebExceptionHandler` beans; sorted by order.
- Some optional components such as `WebSessionManager`, `ServerCodecConfigurer`, `LocaleContextResolver`, and `ForwardedHeaderTransformer`.

Assembly diagram:

~~~text
WebExceptionHandler (outermost)
    |
    v
WebFilter #1
    |
    v
WebFilter #2
    |
    v
Target WebHandler
    |
    v
DispatcherHandler (usually the target)
~~~

Multiple `WebExceptionHandler`s are assembled into an error-handling chain. A handler that completes successfully means the error is considered handled; a handler that returns an error means the error is forwarded.

### 5.2. Creating an HttpHandler yourself at a low level

In an application that needs to build the chain itself, you can use the builder:

~~~java
WebHandler target = exchange -> {
    exchange.getResponse().setStatusCode(HttpStatus.NO_CONTENT);
    return exchange.getResponse().setComplete();
};

HttpHandler httpHandler = WebHttpHandlerBuilder
    .webHandler(target)
    .filter(myWebFilter)
    .exceptionHandler(myWebExceptionHandler)
    .build();
~~~

This is a snippet using `WebHttpHandlerBuilder` directly, not a typical Spring Boot configuration. The returned `HttpHandler` can be connected to a server adapter such as Reactor Netty. In a Boot application, auto-configuration usually builds this part from the context; there is no need to create another builder just to register a filter.

## 6. Distinguishing `WebExceptionHandler` from `@ControllerAdvice`

These two mechanisms differ in scope and in when they handle errors:

| Mechanism | Position | Suitable scope |
| --- | --- | --- |
| `@ExceptionHandler` in `@ControllerAdvice` / `@RestControllerAdvice` | Inside the controller dispatch mechanism | Errors from controllers/handlers managed by DispatcherHandler |
| `WebExceptionHandler` | Wraps the WebFilter chain and the target WebHandler | Errors escaping the filter chain or the target WebHandler, including errors from filters |
| `ResponseStatusExceptionHandler` | A framework WebExceptionHandler | Maps `ResponseStatusException` to an HTTP status |
| Spring Boot's default error handler | In Boot's error-handling chain | Fallback error response when no earlier handler handled the error |

For example: if a controller throws an exception and there is a suitable `@ExceptionHandler`, the error can be handled right inside the dispatch mechanism. If a `WebFilter` emits an error before the request reaches `DispatcherHandler`, `@ControllerAdvice` is not the right layer to handle that error; a `WebExceptionHandler` on the outside of the chain can handle it.

You do not need to choose a single mechanism for the whole application. Use `@ControllerAdvice` for errors tied to controllers/the API domain, and use `WebExceptionHandler` for handling at the web pipeline level such as filters, global status mapping, or errors that escape dispatch.

## 7. `ServerWebExchange`: the object that runs through the request

`ServerWebExchange` connects the components within one HTTP request-response:

~~~text
WebFilter
  |
  | exchange.getRequest()
  | exchange.getResponse()
  | exchange.getAttributes()
  v
DispatcherHandler / controller
  |
  | same exchange
  v
WebExceptionHandler if an error escapes
~~~

Attributes in `exchange.getAttributes()` are useful when a filter wants to pass information to downstream handlers, for example a request ID or a flag indicating that a check step has passed. They belong to the **current exchange**, not to a field shared across requests.

~~~java
exchange.getAttributes().put("requestId", requestId);

String id = exchange.getAttribute("requestId");
~~~

Do not store a user's request ID in a mutable field of a singleton filter or controller. Many requests run concurrently; exchange attributes help separate state per request.

When creating a new exchange with `exchange.mutate().build()`, you need to understand which parts of the request/response are kept and which are replaced. Do not manually copy the request/response or create an entirely new exchange when you only need to modify one attribute.

## 8. Writing a production filter: request ID, header, and end-of-request log

A filter is often useful for logging/tracing:

~~~java
@Component
@Order(0)
public class RequestIdWebFilter implements WebFilter {

    public static final String REQUEST_ID_ATTRIBUTE =
        RequestIdWebFilter.class.getName() + ".requestId";

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(REQUEST_ID_ATTRIBUTE, requestId);
        exchange.getResponse().getHeaders().set("X-Request-Id", requestId);

        return chain.filter(exchange)
            .doFinally(signal ->
                System.out.println(
                    "requestId=" + requestId + ", signal=" + signal));
    }
}
~~~

The principles:

- Attach the ID before calling the chain so controllers and exception handlers can read it.
- Set response headers before the response is committed.
- Use `doFinally` to observe complete/error/cancel; if you need to measure time, capture the start time with a monotonic clock such as `System.nanoTime()`.
- Do not write tokens, cookies, passwords, or the entire body to logs by default.
- In a distributed system, you can accept a trace/correlation ID from a trusted gateway, but you need to validate/normalize the incoming header and avoid logging data arbitrarily supplied by the client.
- If integrating Spring Security, consider the filter order so the request ID is present in security errors as well; the specific order must be designed together with the security chain.

Do not call `subscribe()` inside a filter. Return the `chain.filter` Publisher so the framework manages lifecycle, errors, and cancellation. If you subscribe yourself, the response may complete before the work, errors become detached from the request, and cleanup becomes hard to predict.

## 9. Writing a production exception handler: classifying errors and returning a safe response

An exception handler should handle known errors with a structured response, while passing the remaining errors on through the chain.

~~~java
@Component
@Order(-2)
public class ApiWebExceptionHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable error) {
        if (error instanceof CatalogUnavailableException) {
            return writeError(
                exchange,
                HttpStatus.SERVICE_UNAVAILABLE,
                "{\"error\":\"CATALOG_UNAVAILABLE\"}"
            );
        }

        if (exchange.getResponse().isCommitted()) {
            return Mono.error(error);
        }

        return Mono.error(error);
    }

    private Mono<Void> writeError(
        ServerWebExchange exchange,
        HttpStatus status,
        String json
    ) {
        ServerHttpResponse response = exchange.getResponse();

        if (response.isCommitted()) {
            return Mono.error(
                new IllegalStateException("Response already committed"));
        }

        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

This is an abbreviated example to illustrate the contract. In a real system:

- Map exceptions to status and error code according to the API contract, not by arbitrarily relying on class names.
- Do not return stack traces, SQL, internal hostnames, tokens, or deployment information to the client.
- Log details on the server with the request ID, but avoid logging the same exception multiple times at every layer.
- If the response is already committed, do not try to write more JSON; write a log/metric and let the connection end according to its actual state.
- Do not catch every `Throwable` and then return 200 OK. Unrecognized errors must continue to be reported to the fallback/error infrastructure.

If you only need to map `ResponseStatusException`, consider Spring's built-in handler instead of rewriting the status logic yourself. For controller errors, `@RestControllerAdvice` can be more readable and provides domain-oriented exception handling mechanisms.

## 10. A complete Spring Boot 3 + Java 17 example

The following example illustrates the three components in a real application:

- `DispatcherHandler` is the target `WebHandler` configured by Spring Boot.
- `RequestIdWebFilter` attaches a request ID and a response header.
- `CatalogWebExceptionHandler` handles a business exception at the WebExceptionHandler layer.
- The controller returns a Publisher and produces both successful and error responses.

It uses Spring Boot **3.5.7**, Java 17, and Maven. This is a standalone project; do not mix `spring-boot-starter-web` into the dependencies, so that Boot does not choose Spring MVC instead of WebFlux.

### 10.1. Project structure

~~~text
webflux-handler-chain/
├── pom.xml
└── src/main/java/example/webflux/
    ├── WebFluxHandlerChainApplication.java
    ├── DemoController.java
    ├── RequestIdWebFilter.java
    ├── CatalogWebExceptionHandler.java
    └── CatalogUnavailableException.java
~~~

### 10.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-handler-chain</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 10.3. `WebFluxHandlerChainApplication.java`

~~~java
package example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxHandlerChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxHandlerChainApplication.class, args);
    }
}
~~~

### 10.4. `RequestIdWebFilter.java`

~~~java
package example.webflux;

import java.util.UUID;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class RequestIdWebFilter implements WebFilter {

    public static final String REQUEST_ID_ATTRIBUTE =
        RequestIdWebFilter.class.getName() + ".requestId";

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(REQUEST_ID_ATTRIBUTE, requestId);
        exchange.getResponse().getHeaders().set("X-Request-Id", requestId);

        System.out.println("before requestId=" + requestId);

        return chain.filter(exchange)
            .doFinally(signal ->
                System.out.println(
                    "after requestId=" + requestId + ", signal=" + signal));
    }
}
~~~

The `Ordered` import is not needed in the class because we use the `@Order` annotation; you can remove that import in your IDE if the compiler/linter reports an unused import. The main point of the example is that the filter registers itself as a bean and is ordered by annotation.

### 10.5. `CatalogUnavailableException.java`

~~~java
package example.webflux;

public class CatalogUnavailableException extends RuntimeException {

    public CatalogUnavailableException(String message) {
        super(message);
    }
}
~~~

### 10.6. `CatalogWebExceptionHandler.java`

~~~java
package example.webflux;

import java.nio.charset.StandardCharsets;

import org.springframework.core.annotation.Order;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;

import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class CatalogWebExceptionHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable error) {
        if (!(error instanceof CatalogUnavailableException)) {
            return Mono.error(error);
        }

        ServerHttpResponse response = exchange.getResponse();
        if (response.isCommitted()) {
            return Mono.error(error);
        }

        response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] bytes =
            "{\"error\":\"CATALOG_UNAVAILABLE\"}".getBytes(StandardCharsets.UTF_8);

        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

`@Order(-2)` places the business handler before Spring Boot's fallback error handler in this example. If the application has many other handlers, check the actual order and avoid creating two handlers that both pick up the error and both write to the same response.

### 10.7. `DemoController.java`

~~~java
package example.webflux;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/demo")
public class DemoController {

    @GetMapping("/ok")
    public Mono<Map<String, String>> ok(ServerWebExchange exchange) {
        String requestId = exchange.getAttribute(
            RequestIdWebFilter.REQUEST_ID_ATTRIBUTE);

        return Mono.just(Map.of(
            "message", "ok",
            "requestId", requestId
        ));
    }

    @GetMapping("/fail")
    public Mono<String> fail() {
        return Mono.error(
            new CatalogUnavailableException("catalog is temporarily unavailable"));
    }

    @GetMapping("/missing")
    public Mono<String> missing() {
        return Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND, "not found"));
    }
}
~~~

### 10.8. Running the application

From the directory containing `pom.xml`, run:

~~~bash
mvn spring-boot:run
~~~

Try the successful endpoint:

~~~bash
curl -i http://localhost:8080/demo/ok
~~~

Main result:

~~~text
HTTP/1.1 200 OK
X-Request-Id: <UUID generated for the request>
Content-Type: application/json

{"message":"ok","requestId":"<same UUID>"}
~~~

Try the business error:

~~~bash
curl -i http://localhost:8080/demo/fail
~~~

Main result:

~~~text
HTTP/1.1 503 Service Unavailable
X-Request-Id: <UUID generated for the request>
Content-Type: application/json

{"error":"CATALOG_UNAVAILABLE"}
~~~

Try the framework status error:

~~~bash
curl -i http://localhost:8080/demo/missing
~~~

The main result is HTTP 404. The detailed error body depends on the error attributes and the Spring Boot configuration; you should not rely on the entire default JSON as a fixed API contract.

The application log looks like this:

~~~text
before requestId=<UUID>
after requestId=<same UUID>, signal=onComplete
~~~

For a failing request, the filter can still observe the error or the terminating signal according to the actual processing path. `CatalogWebExceptionHandler` only handles `CatalogUnavailableException`; a `ResponseStatusException` error is forwarded so that the framework's status handler handles it.

### 10.9. Why does this example illustrate the three contracts correctly?

- `DispatcherHandler` is the target WebHandler; it routes `/demo/ok`, `/demo/fail`, and `/demo/missing` to the controller.
- `RequestIdWebFilter` runs before the target handler and attaches the request ID to the exchange and header. The controller reads the value back from the very same exchange.
- `CatalogWebExceptionHandler` sits at the exception chain layer outside the filter/handler. It handles the business error by writing HTTP 503 and a JSON body.
- When the handler does not recognize an error, it returns `Mono.error(error)`; the next handler can handle it, for example WebFlux's status handler for `ResponseStatusException`.
- The controller returns a `Mono`; it does not `subscribe()` itself, because Spring manages the subscription and the response lifecycle.

## 11. Testing filters and exception handlers

You can use `WebTestClient` for integration testing without writing a manual HTTP client. An example test in an application that has WebFlux configured:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebPipelineIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void requestIdIsAddedToSuccessfulResponse() {
        client.get()
            .uri("/demo/ok")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Request-Id")
            .expectBody()
            .jsonPath("$.message").isEqualTo("ok")
            .jsonPath("$.requestId").exists();
    }

    @Test
    void customExceptionIsMappedTo503() {
        client.get()
            .uri("/demo/fail")
            .exchange()
            .expectStatus().isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
            .expectHeader().exists("X-Request-Id")
            .expectBody()
            .jsonPath("$.error").isEqualTo("CATALOG_UNAVAILABLE");
    }
}
~~~

This is an illustrative test snippet; the project needs to add the `spring-boot-starter-test` dependency and the corresponding JUnit/Spring Boot imports. The assertions focus on the HTTP contract: status, header, and error code. You should not test thread order by comparing thread names or relying on sleep times.

Test cases worth having:

- The filter calls the chain exactly once for a valid request.
- A short-circuiting filter returns the expected status and does not call the inner handler.
- The request ID is attached to both successful and error responses.
- The exception handler correctly handles the chosen exception.
- An unrecognized exception is forwarded and not turned into a 200.
- When the response is already committed, the handler does not try to write an error body a second time.
- Two concurrent requests do not share each other's exchange attributes.

## 12. Common mistakes and how to fix them

**Mistake 1 — Thinking `WebHandler` is the controller.** In a standard application, `DispatcherHandler` is the target WebHandler and the controller is the handler it dispatches to. Distinguish the overall layer from the specific endpoint.

**Mistake 2 — Writing a filter but forgetting to call `chain.filter(exchange)`.** The request is blocked at the filter. Only short-circuit when you truly want to create the response yourself.

**Mistake 3 — Calling `chain.filter(exchange)` twice.** This can cause the same request to be processed multiple times, produce side effects, or lead to an already-committed response. Return a single Publisher chain.

**Mistake 4 — Calling `subscribe()` inside a filter.** The framework no longer manages that work within the same response lifecycle; errors and cancellation are easily detached. Return `chain.filter`.

**Mistake 5 — Using `@ControllerAdvice` to handle errors that arise before DispatcherHandler.** Filters sit outside dispatch; use `WebExceptionHandler` at the WebHandler API layer for filter/global errors.

**Mistake 6 — The exception handler returns `Mono.empty()` but does not write or complete the response.** The framework may consider the error handled while the response has no status/body as expected. Write the response or call `setComplete` before completing.

**Mistake 7 — Returning `Mono.error(error)` for an exception that was already handled.** That signals that the error has not been handled and allows the next handler to run. Once the response has been written successfully, return the Publisher that writes the response so it completes normally.

**Mistake 8 — Writing an error body after the response is committed.** The status/headers cannot be changed and a second body can corrupt the protocol. Check `response.isCommitted()`.

**Mistake 9 — Catching every error and returning 200.** The client cannot distinguish success from failure. Map known errors to the correct status, and let the remaining errors continue to the fallback.

**Mistake 10 — Not configuring order.** Multiple filters/exception handlers may run in an unintended order. Use `@Order`/`Ordered` and also check beans created by the framework/security/Boot.

**Mistake 11 — Reading the request body in a filter and then reading it again in the controller.** The body is usually a one-time stream; the filter may have already consumed the data. Use an appropriate caching API or design body caching explicitly.

**Mistake 12 — Storing request state in a field of a singleton filter.** Many requests run concurrently and may overwrite the data. Use `ServerWebExchange.getAttributes()` or the Reactor Context as appropriate.

**Mistake 13 — Thinking WebExceptionHandler can always change the HTTP status.** If the response is already committed, you cannot change the status or send a new body. For streams, design an error event or accept ending the connection.

**Mistake 14 — Writing an internal exception message directly into the response.** This can leak sensitive information. Use an error code and a safe message; log details with a correlation ID on the server.

**Mistake 15 — Using `block()` or blocking I/O in a filter.** Filters are on the request path; blocking can occupy the event loop. Use reactive APIs or isolate blocking libraries with an appropriate strategy such as boundedElastic when truly necessary.

**Mistake 16 — Confusing `WebFilter` with `HandlerInterceptor`.** WebFilter wraps the entire WebHandler chain; an interceptor belongs to a specific handler mechanism. Choose according to the scope you need to apply.

**Mistake 17 — Creating a WebHandler bean in a Boot application without understanding DispatcherHandler.** It may replace or conflict with the default target handler. Normally use controllers/RouterFunction and register filter/exception handler beans.

**Mistake 18 — Believing `WebExceptionHandler` replaces every `@ExceptionHandler`.** An exception in a controller can be handled inside dispatch; WebExceptionHandler is the outer layer for errors that still escape the chain.

## 13. Self-check exercises

1. What parameter does `WebHandler.handle` take and what does it return? **`ServerWebExchange` and `Mono<Void>`.**
2. Which method must `WebFilter` call to pass the request on to the rest? **`chain.filter(exchange)`.**
3. If a filter does not call the chain and returns `exchange.getResponse().setComplete()`, does the controller run? **No**, the filter has short-circuited.
4. When a `WebExceptionHandler` completes successfully, what does that mean? **The error has been handled.**
5. When the handler returns `Mono.error(ex)`, what happens? **The error continues to the next handler in the chain.**
6. In standard WebFlux, which class is usually the target `WebHandler`? **`DispatcherHandler`.**
7. Which kind of special bean does `DispatcherHandler` use to find an endpoint? **`HandlerMapping`.**
8. How can a `WebFilter` bean be registered in Spring Boot? **Declare a bean/`@Component`; Spring detects it automatically.**
9. How do you specify filter order? **`@Order` or `Ordered`.**
10. Is an exception arising in a filter handled by `@ControllerAdvice` through the normal controller mechanism? **The filter is outside DispatcherHandler; use WebExceptionHandler for this scope.**
11. When the response is already committed, can an exception handler change the status from 200 to 500? **No.**
12. Why should you not call `subscribe()` in a filter? **It detaches the work from the request-response lifecycle managed by the framework.**
13. Why should the request body not be read casually in a filter? **The body can usually be consumed only once; the controller may no longer have data.**
14. What is `ServerWebExchange.getAttributes()` suitable for storing? **Per-request metadata such as the request ID; not global state.**
15. If there is a `ResponseStatusException`, which framework handler can map the status? **`ResponseStatusExceptionHandler`/`WebFluxResponseStatusExceptionHandler`.**
16. In a Boot application, why does a custom WebExceptionHandler need an explicit order? **So it runs at the right position relative to Boot's error fallback and WebFlux's default handler.**
17. Does `WebFilter` apply to functional endpoints? **Yes**, because the filter wraps the target WebHandler, in which DispatcherHandler can dispatch functional routes.
18. If a custom WebExceptionHandler does not recognize the exception type, what should it return? **`Mono.error(error)` to forward it.**

## 14. Key takeaways and references

- **`WebHandler`** is the contract for handling one `ServerWebExchange` and returning `Mono<Void>`.
- **`DispatcherHandler`** is usually the target WebHandler in a standard WebFlux application; it orchestrates `HandlerMapping`, `HandlerAdapter`, and `HandlerResultHandler`.
- **`WebFilter`** wraps the rest of the filter chain and the target handler; use it for logic that cuts across the request.
- **`WebExceptionHandler`** sits outside the filter/handler chain; completing means the error was handled, returning an error means forwarding it.
- **`@ControllerAdvice`** handles errors within the controller dispatch scope; `WebExceptionHandler` covers errors escaping from the web pipeline layer.
- Use `ServerWebExchange` to access the request, response, and per-request attributes; avoid shared mutable state.
- Return a Publisher so the framework manages the lifecycle; do not subscribe/block yourself in a filter or handler.

Official documentation for cross-checking:

1. [Spring Framework Reference — Reactive Core / WebHandler API, Filters and Exceptions](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): `HttpHandler`, `WebHandler`, bean discovery, `WebFilter`, and `WebExceptionHandler`.
2. [Spring Framework Reference — DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): front controller, `HandlerMapping`, `HandlerAdapter`, and `HandlerResultHandler`.
3. [Spring Framework Javadoc — WebHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebHandler.html): the `handle(ServerWebExchange)` contract.
4. [Spring Framework Javadoc — WebFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html) and [WebFilterChain](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilterChain.html): the filter contract and chain forwarding.
5. [Spring Framework Javadoc — WebExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebExceptionHandler.html): the error-handling contract and the meaning of Mono<Void>.
6. [Spring Framework Javadoc — WebHttpHandlerBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html): assembling the WebHandler, filters, exception handlers, and server adapter.
7. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): WebFlux auto-configuration, WebFilter beans, error handling, and reactive application configuration.
