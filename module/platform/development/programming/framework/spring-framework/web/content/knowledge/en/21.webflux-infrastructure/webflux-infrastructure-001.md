# HttpHandler, WebHandler, and ServerWebExchange — HTTP Processing Foundations in Spring WebFlux

## 1. The problem: what layers sit between an HTTP socket and @RestController?

When a client sends `GET /api/exchange/hello/Lan` to a Spring WebFlux application, a controller author usually sees only `@GetMapping` and `Mono<T>`. However, the framework must handle many tasks before and after invoking the controller:

- Receiving the request/response from Reactor Netty, Tomcat, Jetty, or a compatible HTTP runtime.
- Representing the HTTP request/response through a common abstraction independent of the server implementation.
- Providing an object representing **the entire HTTP exchange**: attributes, locale, web session, principal, request path, multipart/form data, and response lifecycle.
- Allowing `WebFilter` to apply logic before/after the handler.
- Routing to an annotated controller, functional endpoint, or custom handler.
- Applying codecs, handling exceptions, writing the body asynchronously, and completing the response.
- Preserving Reactive Streams rules and coordinating when the client is slow, cancels the request, or the socket encounters an error.

The three most important abstractions at the infrastructure layer are:

1. `HttpHandler` — Spring WebFlux's **lowest-level** HTTP contract, receiving `ServerHttpRequest` and `ServerHttpResponse`, returning `Mono<Void>`.
2. `WebHandler` — a higher-level web HTTP processing contract, receiving `ServerWebExchange`, returning `Mono<Void>`.
3. `ServerWebExchange` — a context representing **a single request–response exchange** with associated HTTP/web services.

These three concepts are **not equivalent** to `HandlerFunction` (functional routing) or `DispatcherHandler` (WebFlux's front controller). They sit at different layers and connect via `HttpWebHandlerAdapter` / `WebHttpHandlerBuilder`.

**Article scope:** Spring Framework **6.1.x**, Spring Boot **3.3.5**, Java **17**, **Spring WebFlux** stack. The article uses Reactor `Mono`/`Flux`, `WebFilter`, `WebExceptionHandler`, `WebTestClient`, and mock HTTP classes. It does not assume only Reactor Netty runs WebFlux; WebFlux has adapters for Spring-supported runtimes.

### After this article you will know

- How to trace the exact path from an HTTP adapter to `DispatcherHandler` and result handlers.
- How to read the Java signatures of `HttpHandler`, `WebHandler`, and `WebFilter`.
- Why `ServerWebExchange` differs from request/response objects and from `ServerRequest` in functional endpoints.
- How to use request attributes, headers, query, session, principal, locale, and response in accordance with their lifecycle.
- The ordering of `WebFilter`, `WebExceptionHandler`, routing, and serialization.
- How to assemble an `HttpHandler` from a `WebHandler` manually and when not to do so.
- How to build a WebFlux application with WebFilter/controller, run curl, and test end-to-end with `WebTestClient`.
- How to avoid event-loop blocking, double-subscribed bodies, already-committed responses, ignored cancellation, and DataBuffer leaks.

## 2. The big picture of WebFlux

A Spring Boot WebFlux application using the Reactor Netty runtime typically follows this path:

```text
HTTP client
   |
   v
Runtime HTTP server: Reactor Netty / supported adapter
   |
   v
ServerHttpRequest + ServerHttpResponse
   |
   v
HttpHandler (low-level reactive HTTP contract)
   |
   v
HttpWebHandlerAdapter
   |  creates ServerWebExchange, sets up services
   v
WebExceptionHandler chain
   |
   v
WebFilter chain
   |
   v
WebHandler
   |
   +--- DispatcherHandler (WebFlux front controller, commonly used)
   |      |
   |      +--> HandlerMapping finds endpoint
   |      +--> HandlerAdapter invokes handler
   |      +--> HandlerResultHandler writes result
   |
   +--- or a custom WebHandler if the application builds low-level
   |
   v
Response commit + write + completion signals
   |
   v
HTTP client
```

The diagram describes **logical** responsibilities, not a dedicated thread per box. `WebHttpHandlerBuilder` assembles the chain of components; surrounding decorators/filters/exception handlers affect signal propagation on success or error.

**Key distinction:** `DispatcherHandler` **is an implementation of WebHandler**. It does not replace the `HttpHandler` abstraction; the outer adapter still receives the request/response from the HTTP server. Annotated controllers and WebFlux.fn routes are placed underneath `DispatcherHandler` via HandlerMapping/Adapter/ResultHandler.

### Four layers not to confuse

| Layer | Contract | What does it know? | Role |
| --- | --- | --- | --- |
| Server adapter | Reactor Netty API, Servlet async/non-blocking bridge, etc. | Socket/server-specific events | Translates server I/O to Spring HTTP |
| `HttpHandler` | `handle(ServerHttpRequest, ServerHttpResponse)` | Reactive HTTP request/response | Server-independent entry point |
| `WebHandler` | `handle(ServerWebExchange)` | Web context with request, response, and services | Executes the web handling chain |
| WebFlux programming model | Annotated controllers or `RouterFunction`/`HandlerFunction` | Route, DTO, return values | Application endpoint logic |

Even though the name "handler" appears in multiple places, the APIs and hook points are completely different.

## 3. HttpHandler: the lowest-level HTTP contract

### 3.1. Core signature

`HttpHandler` belongs to package `org.springframework.http.server.reactive`:

```java
@FunctionalInterface
public interface HttpHandler {
    Mono<Void> handle(
            ServerHttpRequest request,
            ServerHttpResponse response);
}
```

This is the meaningful signature of the interface, not a source file you need to define yourself.

- `ServerHttpRequest` represents the method, URI, headers, path, body as `Flux<DataBuffer>`, cookies, remote address, and HTTP metadata.
- `ServerHttpResponse` allows setting status/headers/cookies and writing the response body using `Publisher<? extends DataBuffer>`.
- `Mono<Void>` represents the **completion signal** of request processing. It can complete successfully, complete with an error, or be canceled; it does not carry a Java DTO directly.

**Not equivalent to a sync void method:** `Mono<Void>` carries no value, yet it still must be **subscribed to by the framework/runtime**. If you invoke a handler manually in a test or custom adapter, you must subscribe/verify completion; otherwise, a reactive chain may not run and the response may not be written.

### 3.2. Simple HttpHandler example

```java
HttpHandler handler = (request, response) -> {
    response.setStatusCode(HttpStatus.OK);
    response.getHeaders().setContentType(
            MediaType.TEXT_PLAIN);

    byte[] bytes = "hello-low-level"
            .getBytes(StandardCharsets.UTF_8);
    DataBuffer body = response.bufferFactory().wrap(bytes);

    return response.writeWith(Mono.just(body));
};
```

This is a snippet with imports `HttpHandler`, `HttpStatus`, `MediaType`, `DataBuffer`, `Mono`, and `StandardCharsets`. In a real app, an HTTP runtime must be wired to the HttpHandler; this snippet **does not start a server listening on a port**.

Note:

- Do not call `response.getOutputStream().write(...)` like synchronous Servlet code.
- `writeWith` accepts a `Publisher<DataBuffer>`; the framework/container coordinates writing/completion according to the reactive contract.
- Do not retain and reuse a `DataBuffer` across requests or pass the same buffer to multiple consumers.
- With special buffer allocation (pooled buffers), ownership and release are critical; see section 16.
- Low-level logic does not come with controller mapping, DTO validation, handler adapters, or WebSession services unless you assemble them yourself.
- In a typical Spring Boot application, you **do not need to register an HttpHandler manually** just to build a REST API.

### 3.3. Why does Spring need a common contract?

HTTP runtimes have different socket/stream APIs. Spring defines `HttpHandler` so the framework can process reactive requests without forcing annotated controllers to depend directly on a Netty channel or Servlet response object. A server-side adapter converts request bytes into `ServerHttpRequest`/`ServerHttpResponse` and invokes `HttpHandler`; the Spring framework handles the rest.

Thanks to this layer, WebFlux web-layer concepts do not have to change when the runtime changes from Netty to another supported server. Even so, specific behavior regarding HTTP/2, TLS, compression, connection timeouts, and native buffers still depends on server/proxy configuration; the abstraction does not give every runtime the same performance profile.

## 4. WebHandler: a higher-level web context than HttpHandler

`WebHandler` resides in `org.springframework.web.server`:

```java
@FunctionalInterface
public interface WebHandler {
    Mono<Void> handle(ServerWebExchange exchange);
}
```

This is a representative API signature, not a custom application interface you need to write.

Unlike `HttpHandler`, WebHandler does **not** take the two request and response arguments directly. It receives `ServerWebExchange`, which holds both the request/response and web infrastructure.

Example:

```java
WebHandler handler = exchange -> {
    ServerHttpResponse response = exchange.getResponse();
    response.setStatusCode(HttpStatus.OK);
    response.getHeaders().setContentType(
            MediaType.TEXT_PLAIN);

    String path = exchange.getRequest()
            .getPath().value();

    DataBuffer bytes = response.bufferFactory()
            .wrap(path.getBytes(StandardCharsets.UTF_8));

    return response.writeWith(Mono.just(bytes));
};
```

This is a **WebHandler snippet**; you can wrap it with `WebHttpHandlerBuilder.webHandler(handler).build()` to build a real HttpHandler, as shown in the complete test in section 11.

### WebHandler is not HandlerFunction

There are two names that are easily confused:

| Type | Package | Method | Location |
| --- | --- | --- | --- |
| `WebHandler` | `org.springframework.web.server` | `handle(ServerWebExchange) -> Mono<Void>` | WebFlux infrastructure |
| `HandlerFunction<T>` | `org.springframework.web.reactive.function.server` | `handle(ServerRequest) -> Mono<ServerResponse>` | WebFlux.fn programming model |
| `HandlerMethod` | Spring web method metadata | Java method of an annotated controller | MVC/WebFlux annotated mapping |
| `HttpHandler` | `org.springframework.http.server.reactive` | `handle(ServerHttpRequest,ServerHttpResponse) -> Mono<Void>` | Low-level HTTP layer |

`HandlerFunction` produces a `ServerResponse` as a function-level result; `WebHandler` is responsible for completing the HTTP exchange (or delegating to `DispatcherHandler` to process results). WebFlux.fn's `ServerRequest` is also different from the low-level `ServerHttpRequest` and `ServerWebExchange`.

## 5. ServerWebExchange: the center of an HTTP exchange

`ServerWebExchange` belongs to `org.springframework.web.server` and represents an ongoing request/response exchange.

Commonly used APIs:

| Component | Example | Purpose |
| --- | --- | --- |
| Request | `exchange.getRequest()` | Method, URL, headers, cookies, body publisher |
| Response | `exchange.getResponse()` | Status, headers, cookies, write/commit |
| Attributes | `exchange.getAttributes()` | Mutable map of data attached to the current exchange |
| Attribute | `exchange.getAttribute("key")` | Retrieves an attribute with the type expected by the caller |
| Default attribute | `exchange.getAttributeOrDefault("key", fallback)` | Provides a fallback value when the key does not exist |
| Web session | `exchange.getSession()` | `Mono<WebSession>`, reactive session access |
| Principal | `exchange.getPrincipal()` | `Mono<Principal>` or subtype, depending on authentication |
| Locale | `exchange.getLocaleContext()` | LocaleContext from the resolver |
| Form data | `exchange.getFormData()` | `Mono<MultiValueMap<String,String>>` |
| Multipart data | `exchange.getMultipartData()` | `Mono<MultiValueMap<String,Part>>` |
| URL transform | `exchange.transformUrl(String)` | Applies URL transformer if configured |
| Conditional request | `exchange.checkNotModified(...)` | Supports conditional GET evaluation per API |
| Request mutation | `exchange.mutate().request(...).build()` | Creates an exchange wrapper for filters |

### 5.1. Attributes live for the scope of the exchange

```java
exchange.getAttributes().put(
        "requestMarker", "from-filter");

String marker = exchange.getAttributeOrDefault(
        "requestMarker", "absent");
```

**This is not an HTTP header, not a Session, and not a Reactor Context.** Attributes are an internal map, convenient for filters to pass information to handlers within a single request. Do not put secrets into logs just because they are in attributes. With logic spanning multiple async publishers, the exchange may be seen concurrently across stages; writing to a mutable map from multiple threads requires synchronization/happens-before consideration.

Different libraries using the same key name can collide; use constants/namespaced keys like `com.example.trace.correlationId` instead of generic `id` or `user`.

### 5.2. getSession() returns a publisher

```java
Mono<WebSession> sessionMono =
        exchange.getSession();
```

Do not do:

```java
// ANTI-PATTERN: may block the event loop.
WebSession session = exchange.getSession().block();
```

Better:

```java
return exchange.getSession()
        .flatMap(session -> {
            String value = session.getAttribute("theme");
            return buildResponse(value);
        });
```

This is a **snippet** because `buildResponse` is implemented by the application. Session is an asynchronous abstraction that may interact with a session store. Calling `getSession()` **does not necessarily create a new session cookie**; starting/committing the session depends on usage and the session manager.

### 5.3. Principal is also reactive

```java
return exchange.getPrincipal()
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");
```

`getPrincipal()` returns `Mono<Principal>`; it can be empty when unauthenticated. Do not arbitrarily use `getAttribute("user")` to replace authentication; when adding Spring Security, use the framework's security context/principal and check permissions per resource/tenant.

**Important:** If the application uses Spring Security WebFlux, authentication/authorization sits in the reactive `WebFilter` chain managed by Spring Security. Do not trust a client-supplied `X-User` header as identity just because a WebFilter can set an attribute.

### 5.4. Request path and URI are not like servletRequest

In WebFlux, `ServerHttpRequest` provides `getPath()` and `getURI()`. A request path may have a context path and pathWithinApplication; raw/decoded HTTP URI segments must be handled properly during routing/security. Do not assume `HttpServletRequest` is available in an app running on Netty. `jakarta.servlet.http.HttpServletRequest` APIs belong to the Servlet stack and are not portable WebFlux code.

### 5.5. One exchange, one response lifecycle

`ServerWebExchange` is bound to a single HTTP exchange. It must not be stored in a singleton field or held indefinitely in a queue to be reused for another request. A response has a **committed** phase: once status/headers/body have been committed, changing status/headers or sending a new error JSON may no longer be possible.

Check:

```java
if (exchange.getResponse().isCommitted()) {
    return Mono.error(error);
}
```

This is a snippet with an existing `error`. Checking `isCommitted()` does not eliminate all races; sometimes commit happens right after the check. Error policy design should handle errors **before** starting to stream the body or accept that only closing the connection is possible once a streaming response has partially sent data.

## 6. HttpWebHandlerAdapter: bridging the two contracts

`HttpWebHandlerAdapter` belongs to `org.springframework.web.server.adapter`. By role, it **receives** the low-level request/response from `HttpHandler` and **adapts** them into a `ServerWebExchange` to invoke a `WebHandler`.

```text
HttpHandler.handle(ServerHttpRequest, ServerHttpResponse)
                 |
                 v
         HttpWebHandlerAdapter
                 |
                 +-- creates ServerWebExchange
                 +-- session manager
                 +-- codec config for form/multipart
                 +-- locale resolver
                 +-- forwarded-header handling if configured
                 |
                 v
WebHandler.handle(ServerWebExchange)
                 |
                 v
          Mono<Void> completion
```

It also participates in HTTP lifecycle handling such as response logging, request details, session save, cleanup, and errors depending on the specific integration. At the application API level, **let `WebHttpHandlerBuilder` or Spring Boot build the adapter**; do not instantiate the adapter manually without understanding its dependencies/chain.

### Why does the builder reduce mistakes?

A standalone WebHandler does not indicate whether filters/exceptions/session/codecs are wired in. `WebHttpHandlerBuilder` gathers the relevant configuration to assemble a complete HttpHandler, avoiding forgetting a WebFilter or WebExceptionHandler when building a custom reactive HTTP server adapter.

## 7. WebHttpHandlerBuilder assembles the processing chain

`org.springframework.web.server.adapter.WebHttpHandlerBuilder` has two notable ways to initialize:

```java
HttpHandler fromContext =
        WebHttpHandlerBuilder
                .applicationContext(applicationContext)
                .build();

HttpHandler manual =
        WebHttpHandlerBuilder
                .webHandler(webHandler)
                .filter(myWebFilter)
                .exceptionHandler(myErrorHandler)
                .build();
```

This is a **snippet**: `applicationContext`, `webHandler`, `myWebFilter`, and `myErrorHandler` are pre-supplied instances. Use static `applicationContext(...)` when you want the builder to discover Spring-managed beans automatically; use `webHandler(...)` when supplying the target explicitly.

As of Spring 6.1, the builder can recognize the following bean types/configuration points:

| Bean or dependency | Conceptual count/condition | Responsibility |
| --- | --- | --- |
| `WebHandler` named `webHandler` | One target | In Boot WebFlux, typically DispatcherHandler |
| `WebFilter` | 0..N, ordered | Intercepts/wraps the request chain |
| `WebExceptionHandler` | 0..N, ordered | Handles errors from the filter/handler chain |
| `WebSessionManager` named `webSessionManager` | Optional | Manages WebSession |
| `ServerCodecConfigurer` named `serverCodecConfigurer` | Optional | Readers for form/multipart and codec settings |
| `LocaleContextResolver` named `localeContextResolver` | Optional | Locale context |
| `ForwardedHeaderTransformer` with framework's standard name | Optional | Processes Forwarded/X-Forwarded-* from proxies per trust policy |
| HTTP handler decorators / observation support | Depends on version/config | Overall HttpHandler decoration, observability |

`WebHttpHandlerBuilder.applicationContext(context)` looks up the `WebHandler` by the standard infrastructure name `webHandler`, usually declared by WebFlux config for `DispatcherHandler`; filters/exception handlers are looked up by type and ordered. In a standard Boot app, **you do not need to manually define an HttpHandler bean of the same name** because Boot/WebFlux configuration already assembles the pipeline.

### Order of WebFilter and WebExceptionHandler

In essence, the builder takes a **target WebHandler**, wraps it with `WebFilter`s, and then wraps that with `WebExceptionHandler`s. This allows exception handlers to see errors raised when either an inner filter or handler signals an error.

```text
WebExceptionHandler A
   |
   +--> WebExceptionHandler B
          |
          +--> WebFilter A
                 |
                 +--> WebFilter B
                        |
                        +--> WebHandler
```

The diagram only illustrates **nesting**. Actual ordering depends on `Ordered`/`@Order` and component registration; do not infer the exact sequence from class names A/B. Verify filter/chain order with tests when business/security correctness depends on it.

### Do not unintentionally define a custom WebHandler bean named webHandler

In Boot WebFlux, `DispatcherHandler` is usually the central WebHandler with bean name `webHandler`. If you define your own `WebHandler` bean named `webHandler` without intending to replace the entire dispatch pipeline, you may lose route discovery for annotated controllers/functional endpoints or cause a bean collision. For typical custom APIs, use `@RestController`, `RouterFunction`, `WebFilter`, or WebFlux config instead of overriding the front controller.

## 8. DispatcherHandler: the WebHandler that performs web routing

`org.springframework.web.reactive.DispatcherHandler` is the front controller of WebFlux. It implements `WebHandler` and can be discovered under the bean name `webHandler`.

Three main extension groups:

1. **HandlerMapping**: finds the first handler matching the request (annotated controller, functional route, or another handler).
2. **HandlerAdapter**: executes the selected handler and returns a `HandlerResult`.
3. **HandlerResultHandler**: processes the result to produce the HTTP response (body, `ResponseEntity`, functional `ServerResponse`, or view).

```text
DispatcherHandler.handle(exchange)
            |
            v
HandlerMapping(s): matching handler?
            |
            v
HandlerAdapter: invoke handler -> HandlerResult
            |
            v
HandlerResultHandler: render response
            |
            v
          Mono<Void>
```

### Types of handler mappings

- `RequestMappingHandlerMapping`: annotated `@RequestMapping`, `@GetMapping`, `@PostMapping`.
- `RouterFunctionMapping`: WebFlux.fn `RouterFunction<ServerResponse>`.
- `SimpleUrlHandlerMapping`: explicit URL → WebHandler/other handler mappings.

### Types of result handlers

- `ResponseEntityResultHandler` for `ResponseEntity`.
- `ServerResponseResultHandler` for WebFlux functional `ServerResponse`.
- `ResponseBodyResultHandler` for `@ResponseBody`/`@RestController` objects.
- `ViewResolutionResultHandler` for HTML views/models per configuration.

The goal is to support multiple programming models on top of a unified WebHandler/HttpHandler pipeline.

**Do not confuse:** WebFlux `DispatcherHandler` is **different** from Spring MVC `DispatcherServlet`. WebFlux can run on Servlet containers via a non-blocking I/O bridge, yet it still uses **reactive WebFlux processing contracts**, and does not automatically become MVC DispatcherServlet.

## 9. WebFilter: pre/post processing at the exchange layer

`WebFilter` has the signature:

```java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
```

You normally return `chain.filter(exchange)` to continue. You can:
- Read request metadata and attach attributes for downstream.
- Set headers before the response commits.
- Perform logging/tracing/metrics/correlation or clearly scoped policy enforcement.
- Short-circuit the chain early with a `Mono<Void>` returning a specific response.
- Use reactive operators `doOnError`, `doFinally`, `contextWrite` according to Reactor semantics.

Example:

```java
@Component
@Order(-10)
public class MarkerWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        exchange.getAttributes().put(
                "demo.marker", "from-web-filter");

        exchange.getResponse().getHeaders()
                .set("X-WebFilter", "active");

        return chain.filter(exchange);
    }
}
```

This is a **complete class snippet in logic**; it requires imports `Component`, `Order`, `WebFilter`, `ServerWebExchange`, `WebFilterChain`, `Mono`. The runnable version in section 11 has an explicit `/api/exchange/**` scope.

### Invoke the chain exactly once

```java
return chain.filter(exchange);
```

Do not do:

```java
// ANTI-PATTERN: multiple subscriptions may execute processing a second time.
chain.filter(exchange).subscribe();
return chain.filter(exchange);
```

The Spring/HTTP runtime subscribes to the outer Mono. Calling `subscribe()` manually can trigger a second request execution, lose context/cancellation, race the response, and corrupt data. Also, never call `block()` on the WebFilter event loop.

### Blocking a request from a filter

A filter can return 403/429 without calling downstream handlers:

```java
if (blockedByServerSidePolicy(exchange)) {
    exchange.getResponse().setStatusCode(
            HttpStatus.TOO_MANY_REQUESTS);
    return exchange.getResponse().setComplete();
}
return chain.filter(exchange);
```

This is a snippet where `blockedByServerSidePolicy` must be implemented in business/security policy. **Do not use a client-asserted header to confirm the user is an admin**. Production authn/authz should be placed in the Spring Security reactive security chain, combined with service-level permission checks.

### WebFilter vs GatewayFilter, HandlerFilterFunction, and Servlet Filter

| API | Stack/scope | Key difference |
| --- | --- | --- |
| `WebFilter` | WebFlux WebHandler chain | Before/around DispatcherHandler or target WebHandler |
| `HandlerFilterFunction` | WebFlux.fn router/handler | Wraps only the corresponding functional router/handler |
| `GlobalFilter`/`GatewayFilter` | Spring Cloud Gateway | Gateway-specific abstractions, not every WebFlux app |
| `jakarta.servlet.Filter` | Servlet stack | Filter chain in the Servlet container |
| `HandlerInterceptor` | Spring MVC | Based on MVC HandlerMapping lifecycle |

A WebFlux app can run on a Servlet container, yet WebFilter remains a reactive API on the WebHandler chain; it **does not behave like** a Servlet Filter using `doFilter`.

## 10. WebExceptionHandler: intercepting errors in the reactive chain

`WebExceptionHandler` belongs to `org.springframework.web.server`:

```java
public interface WebExceptionHandler {
    Mono<Void> handle(
            ServerWebExchange exchange,
            Throwable ex);
}
```

It handles error signals at the WebHandler chain layer. If it **does not handle** the error, return `Mono.error(ex)` so subsequent error handlers have a chance to handle it or the runtime terminates with the error. If handled successfully, set appropriate status/headers/body and return a completing Mono.

Example for an internal custom exception:

```java
WebExceptionHandler handler = (exchange, ex) -> {
    if (!(ex instanceof IllegalArgumentException)) {
        return Mono.error(ex);
    }
    if (exchange.getResponse().isCommitted()) {
        return Mono.error(ex);
    }

    exchange.getResponse().setStatusCode(
            HttpStatus.BAD_REQUEST);
    exchange.getResponse().getHeaders().setContentType(
            MediaType.TEXT_PLAIN);

    byte[] bytes = "bad request"
            .getBytes(StandardCharsets.UTF_8);
    DataBuffer body = exchange.getResponse()
            .bufferFactory().wrap(bytes);
    return exchange.getResponse()
            .writeWith(Mono.just(body));
};
```

This is a **handler snippet**; do not add it indiscriminately to production. `IllegalArgumentException` can represent a programmer bug, not just bad user input; use specific domain exceptions, a consistent status/`ProblemDetail` contract, and security-safe logging. Once the response is committed, do not try to change 200 to 400 and write new JSON.

### WebExceptionHandler vs @ExceptionHandler

`@ExceptionHandler`/`@RestControllerAdvice` normally belongs to exception handling within the annotated controller adapter. `WebExceptionHandler` sits **outside** on the WebHandler chain and can catch errors from filters or handlers not handled at inner layers. That does not mean every exception must reach a global handler: exceptions may already be handled by annotated advice, result adapters, or WebFlux infrastructure earlier.

Spring Boot also auto-configures error web exception handlers to generate responses for unhandled application errors. If adding a custom WebExceptionHandler, verify `@Order`/status/error body so it does not overwrite/hide framework errors or leak information.

## 11. Runnable Spring Boot 3.3.5 project with ServerWebExchange

The demo project illustrates:

1. WebFlux running on **Reactor Netty** via `spring-boot-starter-webflux`.
2. A `@RestController` using `ServerWebExchange` to read request path/method and attributes.
3. A `WebFilter` marking the exchange and adding a response header.
4. An endpoint returning `Mono.delay` to demonstrate reactive async completion (without `Thread.sleep`).
5. An endpoint creating `ResponseStatusException` to test error status.
6. `WebTestClient` testing against a **real embedded HTTP server** on a random port.
7. A low-level test creating an `HttpHandler` from a `WebHandler` via `WebHttpHandlerBuilder`, without opening a real socket.

There is no database, OAuth, Spring Security, or PII logging; the program is solely for learning abstractions/lifecycle.

### 11.1. Project structure

```text
webflux-infra-demo/
├── pom.xml
└── src/
    ├── main/java/demo/webflux/
    │   ├── WebFluxInfraApplication.java
    │   ├── ExchangeController.java
    │   └── MarkerWebFilter.java
    └── test/java/demo/webflux/
        ├── ExchangeControllerTest.java
        └── LowLevelHttpHandlerTest.java
```

### 11.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webflux-infra-demo</artifactId>
    <version>1.0.0</version>
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
```

Do not add `spring-boot-starter-web`, so Boot selects the reactive web application type from the WebFlux starter. If both Servlet MVC and WebFlux starters are added together, Boot typically prefers the Servlet MVC application type unless configured otherwise; **do not use a mixed classpath as evidence that WebFlux is active**.

### 11.3. Main application

**`src/main/java/demo/webflux/WebFluxInfraApplication.java`**

```java
package demo.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxInfraApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxInfraApplication.class, args);
    }
}
```

### 11.4. WebFilter setting a marker on ServerWebExchange

**`src/main/java/demo/webflux/MarkerWebFilter.java`**

```java
package demo.webflux;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-10)
public class MarkerWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest()
                .getPath().value();

        if (!path.startsWith("/api/exchange/")) {
            return chain.filter(exchange);
        }

        exchange.getAttributes().put(
                "demo.marker", "from-web-filter");
        exchange.getResponse().getHeaders()
                .set("X-WebFilter", "active");

        return chain.filter(exchange);
    }
}
```

**Explanation:**

- `@Component` registers the WebFilter in the Spring context; the framework can include it in the WebHandler chain.
- `@Order(-10)` specifies relative ordering compared to other filters; it does not mean it is safe to allow/block security on its own.
- `exchange.getAttributes()` shares data within one exchange; it does not send the marker as a request header to another server.
- `X-WebFilter` is written before the response commits.
- The filter only affects paths starting with `/api/exchange/` and always calls the downstream chain **once**.
- There is no manual `block()` or `subscribe()`.
- If streaming body has already committed, modifying headers afterward is not guaranteed to take effect; the example sets it beforehand for predictability.

### 11.5. REST controller receiving ServerWebExchange

**`src/main/java/demo/webflux/ExchangeController.java`**

```java
package demo.webflux;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/exchange")
public class ExchangeController {

    @GetMapping("/hello/{name}")
    public Mono<ResponseEntity<Map<String, String>>> hello(
            @PathVariable String name,
            ServerWebExchange exchange) {

        String marker = exchange.getAttributeOrDefault(
                "demo.marker", "missing");
        String method = exchange.getRequest()
                .getMethod().name();

        Map<String, String> body = Map.of(
                "name", name,
                "marker", marker,
                "method", method);

        return Mono.just(ResponseEntity.ok(body));
    }

    @GetMapping("/async")
    public Mono<Map<String, String>> async() {
        return Mono.delay(Duration.ofMillis(20))
                .map(tick -> Map.of("state", "ready"));
    }

    @GetMapping("/fail")
    public Mono<String> fail() {
        return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "invalid request"));
    }
}
```

**What the code demonstrates:**

- `@RestController` is just a programming model on top of WebFlux `DispatcherHandler`; underneath there are still HttpHandler, WebHandler, and exchange.
- `ServerWebExchange` is injected into the controller argument by the framework without manual instantiation.
- The filter puts `demo.marker` into the attributes map, and the controller reads that marker back.
- `getRequest().getMethod()` obtains the request's `HttpMethod`; since the endpoint is GET, the expected method is "GET".
- `Mono<ResponseEntity<Map<...>>>` is a reactive single-value response; Jackson serializes the Map to JSON.
- `Mono.delay(...)` emits a signal after a duration without holding a dedicated sleeping thread per subscription like `Thread.sleep`. However, the demo is not a benchmark and the runtime still needs scheduler/event-loop threads.
- `Mono.error(new ResponseStatusException(...))` leads to HTTP 400 via WebFlux error machinery. Response body/error details can vary with Boot configuration; tests only assert status to avoid depending on default formats.
- The application does not perform blocking JDBC calls, does not manually subscribe, and does not store `ServerWebExchange` in a singleton field.

### 11.6. Running with Maven and curl

From the `webflux-infra-demo` directory with Java 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

These are two **sequential commands**. Once Boot starts on default port 8080:

```bash
curl -i 'http://localhost:8080/api/exchange/hello/Lan'
```

Main parts of the response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-WebFilter: active

{"name":"Lan","marker":"from-web-filter","method":"GET"}
```

JSON key ordering is decided by the serializer; do not use full-string equality on JSON unnecessarily.

```bash
curl -i 'http://localhost:8080/api/exchange/async'
```

Expected status 200, header `X-WebFilter: active`, and JSON:

```json
{"state":"ready"}
```

```bash
curl -i 'http://localhost:8080/api/exchange/fail'
```

Expected HTTP status **400 Bad Request**. The header from the filter may still be sent if the response is not yet committed; the error body depends on `ErrorWebExceptionHandler` configuration and content negotiation.

With `curl -i`, there is no default browser-equivalent caching/retry. If running behind a proxy, also observe forwarded headers, idle timeout, `Content-Length`/chunked transfer, and Content-Encoding; those values depend on the runtime.

## 12. WebTestClient test: real path through HttpHandler to Controller

**`src/test/java/demo/webflux/ExchangeControllerTest.java`**

```java
package demo.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ExchangeControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void exchangeAttributesFlowFromWebFilterToHandler() {
        client.get()
              .uri("/api/exchange/hello/Lan")
              .exchange()
              .expectStatus().isOk()
              .expectHeader().valueEquals(
                      "X-WebFilter", "active")
              .expectBody()
              .jsonPath("$.name").isEqualTo("Lan")
              .jsonPath("$.marker")
                  .isEqualTo("from-web-filter")
              .jsonPath("$.method").isEqualTo("GET");
    }

    @Test
    void asynchronousPublisherCompletesWithBody() {
        client.get()
              .uri("/api/exchange/async")
              .exchange()
              .expectStatus().isOk()
              .expectHeader().valueEquals(
                      "X-WebFilter", "active")
              .expectBody()
              .jsonPath("$.state").isEqualTo("ready");
    }

    @Test
    void errorSignalBecomesBadRequestStatus() {
        client.get()
              .uri("/api/exchange/fail")
              .exchange()
              .expectStatus().isBadRequest();
    }
}
```

These three tests start an embedded HTTP server on a random port. `WebTestClient` sends requests to the real server, so they pass through the reactive server adapter and the full WebFlux infrastructure. This is **different** from invoking a controller method directly without a dispatcher, filter, or serializer.

Do not assert that error bodies like `{"message":"invalid request"}` will always appear: in Boot defaults and depending on `server.error.include-message`, error response details may vary. Focus on checking status and declared behavior.

## 13. Testing HttpHandler below DispatcherHandler, without opening a port

To distinguish `HttpHandler` and `WebHandler`, we build a low-level pipeline in a standalone test: no `@RestController`, no `DispatcherHandler`, yet still `ServerWebExchange`/`WebFilter` because `WebHttpHandlerBuilder` creates the adapter.

**`src/test/java/demo/webflux/LowLevelHttpHandlerTest.java`**

```java
package demo.webflux;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.HttpHandler;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpResponse;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebHandler;
import org.springframework.web.server.adapter.WebHttpHandlerBuilder;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LowLevelHttpHandlerTest {

    @Test
    void adapterBuildsExchangeAndRunsWebFilter() {
        WebHandler target = exchange -> {
            String marker = exchange.getAttributeOrDefault(
                    "demo.marker", "missing");

            exchange.getResponse().setStatusCode(HttpStatus.OK);
            exchange.getResponse().getHeaders().setContentType(
                    MediaType.TEXT_PLAIN);

            DataBuffer buffer = exchange.getResponse()
                    .bufferFactory()
                    .wrap(marker.getBytes(StandardCharsets.UTF_8));

            return exchange.getResponse()
                    .writeWith(Mono.just(buffer));
        };

        WebFilter markerFilter = (exchange, chain) -> {
            exchange.getAttributes().put(
                    "demo.marker", "seen-by-web-handler");
            return chain.filter(exchange);
        };

        HttpHandler handler = WebHttpHandlerBuilder
                .webHandler(target)
                .filter(markerFilter)
                .build();

        MockServerHttpRequest request =
                MockServerHttpRequest.get("/raw/demo").build();
        MockServerHttpResponse response =
                new MockServerHttpResponse();

        handler.handle(request, response)
                .block(Duration.ofSeconds(2));

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("seen-by-web-handler",
                response.getBodyAsString()
                        .block(Duration.ofSeconds(2)));
    }
}
```

**What the test proves:**

1. The test defines a **WebHandler** directly rather than an annotated controller.
2. A **WebFilter** adds the `demo.marker` attribute to the exchange.
3. `WebHttpHandlerBuilder.webHandler(target).filter(markerFilter).build()` builds an **HttpHandler** from web-layer classes.
4. The test invokes `HttpHandler.handle(MockServerHttpRequest, MockServerHttpResponse)` — the lowest layer after the HTTP server adapter.
5. `HttpWebHandlerAdapter` creates the exchange internally, and WebFilter runs before target.
6. `getBodyAsString()` verifies the bytes written as the HTTP response.
7. `block()` is **only inside the test** to wait for completion; do not use `block()` in a server handler/WebFilter running on the event loop.

When running Maven with both `ExchangeControllerTest` and `LowLevelHttpHandlerTest`, the project has **4 test methods**. When all pass, Maven exits with code `0`; the typical summary will total `Tests run: 4, Failures: 0, Errors: 0, Skipped: 0`. This article provides code statically reviewed against Spring Boot 3.3.5 APIs; it does not claim Maven was run during authoring on Google Sheets.

### When is building HttpHandler manually reasonable?

- When integrating Spring WebFlux with a custom HTTP runtime/adapter.
- When unit testing a WebHandler/filter chain below DispatcherHandler.
- When building a reusable reactive HTTP infrastructure module needing control over session/codec/exception chains.
- When observing/instrumenting the entire HTTP exchange at a low level.

It is **not** the default choice for adding a REST endpoint: `@RestController` or WebFlux.fn `RouterFunction` is easier to maintain and provides JSON codecs, validation/route tooling, and richer error handling.

## 14. ServerWebExchange in filters: mutating requests properly

Exchange wrappers support mutating request metadata in a functional style:

```java
ServerWebExchange updated = exchange.mutate()
        .request(builder -> builder.header(
                "X-Internal-Trace", "trace-generated-server-side"))
        .build();

return chain.filter(updated);
```

This is a snippet placed inside `WebFilter.filter(...)`. Note:

- The `X-Internal-Trace` header here is only an **example**; auth/identity must never be taken from an arbitrary client header.
- When creating a request wrapper, you must pass the **updated exchange** to the chain, not ignore the updated variable.
- Mutation does not automatically decode/re-encode request bytes. For body transformations, you need `ServerHttpRequestDecorator`, `DataBuffer`, codecs, and proper cancellation/backpressure handling.
- Do not rewrite URI/Host/Forwarded headers from user input to redirect routes to admin resources.
- When the framework already provides Spring Security/tracing gateway integration, prefer the official tools over a complex hand-rolled filter.

### Attributes or Reactor Context?

`exchange.getAttributes()` holds data attached to **a single exchange object**. `reactor.util.context.Context` is the context carried alongside a reactive subscription, used for cross-cutting data such as tracing/security/reactive transactions.

```java
return chain.filter(exchange)
        .contextWrite(context ->
                context.put("auditTag", "from-webfilter"));
```

The snippet above adds `auditTag` to the Reactor Context for publishers **upstream of contextWrite per Reactor Context propagation rules**. It does not automatically modify `exchange.getAttributes()`, nor does `ThreadLocal` automatically sync with Reactor Context. Accessing Context inside a reactive chain commonly uses `Mono.deferContextual(...)`; do not use `Thread.currentThread()` as request identity.

**Do not confuse the three places:**
- Request headers: HTTP data sent by client/proxy (may be untrusted).
- Exchange attributes: mutable map of the web exchange.
- Reactor Context: subscription-scoped context propagated through reactive operators, used by many infrastructure integrations.

## 15. Form/multipart data, body publisher, and single subscription

`ServerWebExchange` has `getFormData()` and `getMultipartData()`, returning `Mono<MultiValueMap<...>>`. They provide a parsed/cached view according to the request content type, relying on configured readers. However, the raw `ServerHttpRequest.getBody()` is a `Flux<DataBuffer>`, usually a **one-shot stream**.

### 15.1. Do not read the body twice arbitrarily

Anti-pattern:

```java
// ANTI-PATTERN: subscribe to raw body for logging while downstream reads it again.
exchange.getRequest().getBody()
        .subscribe(buffer -> logBuffer(buffer));
return chain.filter(exchange);
```

This code can consume the stream before the controller's body decoder, causing unreadable/empty body errors, losing cancellation context, and leaking DataBuffers if unreleased. Do not log raw bodies containing passwords/tokens/PII.

For request body observability, use framework tooling designed for streaming, or write a `ServerHttpRequestDecorator` with maximum byte limits, buffering/ref-counting, and backpressure, tested for content-length/transfer-encoding, slow clients, errors, and cancellation. Do not assume "a WebFilter can always read the body without affecting the controller".

### 15.2. Do not block when reading multipart/form data

```java
return exchange.getMultipartData()
        .flatMap(parts -> {
            // validate metadata/Part, enforce limits
            return processParts(parts);
        });
```

This is a snippet because `processParts` is defined by the application. Multipart bodies can be large; you must enforce upload size limits, part counts, file names/path traversal checks, content types, temp storage, and virus/malware scanning per your threat model. Reactive multipart APIs do not make files safe automatically.

### 15.3. Streaming responses and cancellation

If the client disconnects during a large stream, the reactive pipeline may receive a **cancel signal**. Data sources must properly release subscriptions, file handles, Netty buffers, and remote connections. With `Flux<DataBuffer>`, backpressure expresses demand, yet it is only effective when the source actually respects demand; an unbounded `Flux.create` pushing into memory can still OOM even though the interface is reactive.

## 16. Response commit, headers, and beforeCommit

`ServerHttpResponse` has a commit state. For normal responses, status/headers must be set **before** the body starts writing. To attach final logic just before commit, the response supports `beforeCommit(Supplier<? extends Mono<Void>>)`:

```java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .add("X-Before-Commit", "yes");
    return Mono.empty();
});

return chain.filter(exchange);
```

This is a snippet inside a WebFilter. The callback must return a **deferred Mono** if it performs async side effects; the callback only takes effect before commit and cannot alter status/headers after the response has been sent. Avoid blocking work in the callback; the response commit phase is not the place for long DB calls or sync remote APIs.

### Errors after part of the body has been written

Suppose a stream has already sent half of a CSV and then the publisher emits an error. `WebExceptionHandler` may see the error signal, yet the response may already have committed 200 and sent bytes. It cannot guarantee switching to a 500 JSON error matching the contract; usually it can only terminate/close the connection or handle it according to a streaming protocol (a separate SSE event if still writable).

For file download, SSE, or chunked response endpoints:
- Set headers/status/authorization before the body.
- Handle errors/cancellation, body buffers, and timeouts.
- If a content checksum is needed, return clearly designed metadata/streaming protocols.
- Do not promise clients that every error will be mapped to JSON 500 once streaming has begun.

## 17. WebFlux backpressure and non-blocking: what is actually guaranteed

`HttpHandler.handle(...)` returns `Mono<Void>` and request/response bodies use Reactive Streams. This **enables** the runtime/pipeline to perform non-blocking I/O and propagate backpressure signals. However, you cannot conclude that all Spring WebFlux code is non-blocking merely because signatures use Mono/Flux.

Anti-pattern:

```java
@GetMapping("/broken")
public Mono<String> broken() {
    String result = blockingJdbcRepository.load();
    return Mono.just(result);
}
```

This is a snippet with an undefined repository, intentionally illustrating the bug. The synchronous JDBC call runs **immediately when the controller method is invoked** and can block the event loop.

A bounded offload approach if you temporarily must use a blocking library:

```java
return Mono.fromCallable(
            () -> blockingJdbcRepository.load())
        .subscribeOn(Schedulers.boundedElastic());
```

This is also a snippet, using `reactor.core.scheduler.Schedulers`. It **moves where the blocking work runs** to a boundedElastic worker, **it does not make JDBC non-blocking**. You must configure connection pools, statement timeouts, bounds, transaction context, and measure throughput; avoid excessive blocking jobs/queues causing latency.

### Resources that still exist

While a request is waiting on a reactive signal:
- Sockets/connections and HTTP exchange state still exist.
- Buffers, codec objects, subscriptions, and timeouts can still consume memory.
- Scheduler/event-loop threads still run callbacks/serialization.
- DB/network pool bottlenecks do not disappear on their own.

Reactive helps handle many pending operations with fewer blocked threads **when the entire pipeline is non-blocking and backpressure-aware**. It does not automatically increase throughput for CPU-bound work or slow downstreams.

## 18. Spring Security, CORS, forwarded headers, and privacy

### 18.1. Where does Security live?

In Spring Security WebFlux, the security chain sits inside the **WebFilter chain**. A SecurityWebFilterChain contains rules for authentication, authorization, CSRF, CORS, and exception handling. It protects requests **before annotated controllers/WebFlux.fn**, regardless of route style.

Do not use:

```java
// ANTI-PATTERN: client-supplied header.
String user = exchange.getRequest()
        .getHeaders().getFirst("X-User");
exchange.getAttributes().put("authenticatedUser", user);
```

to replace Spring Security. This header is controlled by the client and proves no identity. When a principal is needed, access `exchange.getPrincipal()` or the reactive SecurityContext via the framework and enforce resource/tenant permissions in services.

### 18.2. CORS at the WebFlux layer

CORS affects browsers. It can be handled via WebFlux CORS configuration or `CorsWebFilter`, and when Security is added it requires proper integration order. Do not write a custom WebFilter that always returns `Access-Control-Allow-Origin: *` for endpoints with credentials. CORS **is not authentication**; command-line HTTP clients can send requests even if browser cross-origin policy prevents reading the response.

### 18.3. Forwarded/X-Forwarded-* headers

`ServerWebExchange` uses request metadata passed through the server/proxy adapter. If the system sits behind a reverse proxy, the public scheme/host/prefix may come from `Forwarded` or `X-Forwarded-*`; `ForwardedHeaderTransformer` needs a clear trust model. A trusted proxy must **strip spoofed headers from the Internet and then set canonical values**. If you trust client-supplied `X-Forwarded-Host`, the app may generate wrong URLs/redirects, leading to phishing, open redirects, or cache poisoning.

### 18.4. Session and caching

`WebSession` can carry user state, yet it does not make HTTP responses private automatically. Personalized endpoints need `Cache-Control: private` or `no-store` depending on sensitivity and CDN policy. Do not call `exchange.getSession()` and assume shared proxies will distinguish users properly.

## 19. Logging, observability, and debugging

A reactive pipeline can switch execution threads across multiple schedulers; therefore, attaching a correlation ID via plain `ThreadLocal` is not guaranteed to survive across async operators.

Prefer:
- Framework-supported Spring/Micrometer observation integration and tracing context propagation.
- Reactor Context for subscription-scoped data.
- Exchange attributes for short-lived request-scoped information.
- Sanitized logs: method, route template, status, latency, correlation ID; **do not log tokens, raw cookies, or sensitive request bodies**.
- Ordered WebFilters and error handlers with clear responsibilities, without letting a logging filter swallow all exceptions.

### Debugging steps

1. **Verify the real stack**: ensure the Spring Boot app has WebFlux active, not MVC `DispatcherServlet` accidentally selected due to the classpath.
2. Verify the `WebHandler` bean named `webHandler` and `DispatcherHandler` are discovered by WebFlux configuration; do not override them by mistake.
3. Trace from `HttpHandler` to `WebHttpHandlerBuilder`/`HttpWebHandlerAdapter` and then WebFilters; write a low-level test if needed.
4. Check which `HandlerMapping` matches the route and which `HandlerResultHandler` writes the response.
5. For missing headers, check whether they are set before commit and whether the filter calls the chain.
6. For 404s, inspect path mapping/controller/functional predicates before blaming Netty.
7. For empty bodies, check who subscribes to/consumes the request body before the converter.
8. For timeouts, inspect downstream client/database calls, event-loop blocking, queues, and network idle timeouts.
9. For 500s, determine whether the exception occurred before or after response commit.
10. For memory leaks, check `DataBuffer` pooling, body caching, and cancellation cleanup.
11. For lost principal/MDC, check SecurityContext/Reactor Context and scheduler boundaries.
12. For CORS errors, test real OPTIONS/preflight Origin requests through the security filter chain.

## 20. Common pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| Importing `web.servlet.function.ServerRequest` in WebFlux | Confusing MVC.fn with WebFlux.fn | Use `web.reactive.function.server` |
| Creating a WebHandler and expecting automatic routing/JSON | WebHandler only receives the exchange | Use DispatcherHandler/config or handle the full pipeline yourself |
| Overriding the `webHandler` bean makes annotated controllers disappear | Overwriting WebFlux's front controller | Do not override unless building low-level infrastructure |
| Adding both starter-web and starter-webflux causes controllers to run on MVC | Boot prefers MVC app type in typical cases | Explicitly specify stack, dependencies, and integration tests |
| `Mono<Void>` does nothing in a custom test | Not subscribed/awaited for completion | Use WebTestClient or `block` in tests, never on the event loop |
| Filter runs twice | Calling `subscribe()` and then returning the chain | Return the chain once, do not subscribe manually |
| `block()` error on the event loop | Calling a blocking API in a reactive callback | Non-blocking client or bounded offload |
| Empty request body | WebFilter reads the raw body before the decoder | Do not consume raw body twice; decorate/cache properly |
| Malformed JSON returns 500 with wrong schema | Different error handler/codecs/advice than expected | Test status/content-type, consistent errors |
| Cannot set status in WebExceptionHandler | Response is already committed | Handle errors early, streaming-specific policy |
| Missing response header | Attached after the body has committed | Set earlier or use `beforeCommit` |
| Filter order causes security bypass | Unclear trust boundary/order | Spring Security reactive chain + tests |
| ThreadLocal loses traceId | Reactive scheduler switches | Reactor Context/context propagation |
| Multipart OOM | Buffering entire body into memory without limits | Max in-memory size, streaming, upload limits |
| DataBuffer memory leak | Pooled buffers not released when manipulated by filters | Use framework operators/`DataBufferUtils.release` with proper ownership |
| `getSession().block()` causes stalls | Blocking the event loop | flatMap/reactive composition |
| `ServerWebExchange` stored in a singleton | Mixing requests, retaining resources too long | Keep only necessary data with short lifecycle |
| Wrong Host in URLs | Untrusted forwarded headers/proxy config | Sanitize at ingress, canonical base |
| Slow SSE, rising memory | Producer ignores demand/cancel | Backpressure, buffer bounds, proper disposal |
| HTTP response differs between Netty/Servlet bridge | Server-specific behavior / proxy | Integration tests against the real runtime |

## 21. Which API level to choose when building an application?

| Need | Integration point to choose |
| --- | --- |
| Normal CRUD REST JSON | `@RestController` or WebFlux.fn `RouterFunction` |
| Applying common policies before routes | `WebFilter` or Spring Security WebFilter chain |
| Mapping unhandled HTTP errors | `WebExceptionHandler` or appropriate Boot/WebFlux error mechanisms |
| Sharing request state across filters/controllers | `ServerWebExchange.getAttributes()` with clear keys |
| Reading body/multipart in business logic | Annotated binding/WebFlux.fn readers/codecs; avoid raw buffers unnecessarily |
| Observing the entire handler pipeline | Observability / WebFilter / HttpHandler decorators when needed |
| Changing the HTTP runtime implementation | Adapter integration based on `HttpHandler` |
| Building a custom routing engine | `WebHandler`/`HandlerMapping` when genuinely required |
| Testing the full HTTP chain | `WebTestClient` bound to server/context |
| Testing lower-layer WebHandler/HttpHandler | `MockServerHttpRequest` + `MockServerHttpResponse` + WebHttpHandlerBuilder |

**Principle:** choose the highest-level abstraction that satisfies the requirement. Controller/router APIs are far less prone to low-level body handling bugs. Only build an HttpHandler manually when there is a real infrastructure need.

## 22. Self-check questions

1. What parameters does `HttpHandler.handle` take and what type does it return?
2. How does `WebHandler.handle` differ from `HttpHandler.handle` in its input?
3. What does `ServerWebExchange` provide besides `ServerHttpRequest` and `ServerHttpResponse`?
4. What two main jobs does `WebHttpHandlerBuilder` perform?
5. Which abstraction does `HttpWebHandlerAdapter` create for WebHandler to process?
6. Is `DispatcherHandler` an implementation of WebHandler?
7. Distinguish `HandlerMapping`, `HandlerAdapter`, and `HandlerResultHandler`.
8. May a `WebFilter` manually call `subscribe()` to run the chain?
9. Why might `WebExceptionHandler` be unable to change the HTTP status when an error occurs mid-response stream?
10. Is `exchange.getAttributes()` equivalent to Reactor Context or WebSession?
11. Why do `exchange.getSession()` and `exchange.getPrincipal()` return a Mono?
12. Is `WebMvc.fn HandlerFunction` the same as WebFlux's `WebHandler`?
13. If an application uses Spring Boot WebFlux with annotated controllers, should you define your own `WebHandler` bean named `webHandler`?
14. `Mono<Void>` emits no value, so what role does it play in response completion?
15. If a WebFilter reads raw `getBody()` and the controller also reads JSON, what is the risk?
16. If `DataBuffer` is pooled, why is reference counting/releasing important?
17. When should you use `beforeCommit`?
18. Does wrapping JDBC with `subscribeOn(Schedulers.boundedElastic())` make JDBC non-blocking?
19. Why should a WebFilter not replace Spring Security for authentication/authorization?
20. How do you test a low-level HttpHandler without starting a Netty server?
21. Why does `ForwardedHeaderTransformer` need a trust boundary?
22. When handling query/form/multipart data, why must max size and cancellation be controlled?
23. If a filter writes an error response, must it always continue calling `chain.filter(exchange)`?
24. If an endpoint returns `Mono.error`, is the error response body guaranteed to be identical across all Boot configurations?

**Hints:** (1) ServerHttpRequest, ServerHttpResponse → Mono<Void>. (2) Exchange wraps request, response, and web services. (3) Attributes, session, principal, form/multipart, locale, conditionals. (4) Assembles filter/error chain and adapts to HttpHandler. (5) ServerWebExchange. (6) Yes. (7) Select handler, execute, render result. (8) No. (9) Response is already committed. (10) No. (11) Reactive asynchronous services. (12) No, different packages and abstractions. (13) Avoid overriding the front controller. (14) Completion/error/cancel signals. (15) One-shot body gets consumed or leaks. (16) Pooled memory must be returned. (17) Header logic right before commit. (18) No, it only moves where blocking happens. (19) Insufficient trust/security policies. (20) WebHttpHandlerBuilder + mock HTTP request/response. (21) Clients can spoof headers. (22) Prevent OOM/slow clients. (23) Once short-circuited, do not call downstream. (24) No, depends on error handlers and Boot config.

## 23. Official references

- [Spring Framework 6.1 — WebFlux: Reactive Core / HttpHandler & WebHandler](https://docs.spring.io/spring-framework/reference/6.1/web/webflux/reactive-spring.html)
- [Spring Framework 6.1 — DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.1/web/webflux/dispatcher-handler.html)
- [Spring Framework 6.1 — WebHttpHandlerBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html)
- [Spring Framework 6.1 — HttpWebHandlerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/adapter/HttpWebHandlerAdapter.html)
- [Spring Framework 6.1 — ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/ServerWebExchange.html)
- [Spring Framework 6.1 — WebHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/WebHandler.html)
- [Spring Framework 6.1 — WebFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/WebFilter.html)
- [Spring Framework 6.1 — WebExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/WebExceptionHandler.html)
- [Spring Framework 6.1 — HttpHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/http/server/reactive/HttpHandler.html)
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html)
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — Reactive Web Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)

**Summary:** `HttpHandler` is the lowest-level reactive HTTP entry point, handling `ServerHttpRequest` and `ServerHttpResponse`. `HttpWebHandlerAdapter` adapts them into a `ServerWebExchange` and invokes `WebHandler`; `WebHttpHandlerBuilder` wires WebFilters, WebExceptionHandlers, and required services. In a standard WebFlux application, `DispatcherHandler` serves as the central WebHandler executing annotated controllers/WebFlux.fn routes. Understanding these layers helps you write filters, handle errors, integrate Security, observe HTTP requests, and debug reactive I/O without confusing WebFlux with Servlet MVC or assuming any Mono/Flux is automatically non-blocking.
