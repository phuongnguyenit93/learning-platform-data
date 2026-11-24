# before, after, filter, and HandlerFilterFunction in Spring WebFlux

## 1. Context: Cross-Cutting Processing Around a Functional Endpoint

Spring WebFlux provides the **WebFlux.fn** functional endpoint model alongside annotated controllers. In this model, a request is routed to a handler function, and then the handler creates a reactive response.

Three foundational components:

- **ServerRequest**: represents the HTTP request, allowing you to read method, path, headers, query parameters, principal, and body.
- **HandlerFunction<ServerResponse>**: receives a ServerRequest and returns a `Mono<ServerResponse>`.
- **RouterFunction<ServerResponse>**: selects the HandlerFunction matching the request; if no route matches, it returns `Mono.empty()`.

A minimal handler:

~~~java
HandlerFunction<ServerResponse> hello = request ->
        ServerResponse.ok().bodyValue("Hello WebFlux");
~~~

A route:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
        .GET("/hello", hello)
        .build();
~~~

When an application has many endpoints, repetitive tasks often arise:

- Attaching a correlation/request ID to the request.
- Logging the request and response status.
- Checking an API key or access permissions.
- Adding response headers.
- Recording metrics and processing duration.
- Standardizing certain errors into HTTP responses.
- Applying a policy to a group of routes instead of repeating it in each handler.

**before, after, and filter** let you place these tasks around handlers. They belong to WebFlux.fn's **RouterFunction.Builder** API. **HandlerFilterFunction** is the general filter function type behind the `filter(...)` method.

## 2. Distinguishing the Three Methods

| Method | Input | Output | Suitable work |
| --- | --- | --- | --- |
| `before(...)` | `ServerRequest` | `ServerRequest` | Synchronous request transformation before the handler |
| `after(...)` | `ServerRequest` and the handler's response | Response | Synchronous response observation or transformation after the handler |
| `filter(...)` | `ServerRequest` and the next handler | `Mono<ServerResponse>` | Wrapping the handler; can proceed, block, or process reactively |

Conceptual flow:

~~~text
HTTP request
     |
     v
  before(request)
     |
     v
 HandlerFilterFunction
     |
     +---- check / short-circuit
     |
     v
 HandlerFunction
     |
     v
  after(request, response)
     |
     v
 HTTP response
~~~

The diagram depicts the basic success flow. With `filter`, there can be multiple nested filters; an outer filter invokes the next filter via `next.handle(request)`. If a filter does not call `next` and returns a response itself, subsequent steps in the chain do not run.

### 2.1. before: processing the request before the handler

Conceptual signature:

~~~java
Builder before(Function<ServerRequest, ServerRequest> requestProcessor);
~~~

`before` takes a synchronous function, reads the current request, and returns the request that the handler will receive. Example adding an internal header:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/hello", request ->
        ServerResponse.ok().bodyValue(
            request.headers().firstHeader("X-Request-Source")))
    .before(request -> ServerRequest.from(request)
        .header("X-Request-Source", "router-before")
        .build())
    .build();
~~~

When calling `GET /hello`, the handler reads the `X-Request-Source: router-before` header.

`ServerRequest` has an immutable contract. Therefore, when you want to create a new request with modified headers, use `ServerRequest.from(request)` to create a builder, then call `build()`. Do not mutate the original request object directly.

Applications commonly use `before` to:

- Normalize or enrich request metadata.
- Add attributes for the handler to read.
- Log non-sensitive request information.
- Standardize certain headers according to an internal contract.
- Prepare synchronous data that is already available before the handler runs.

**Important limitation:** `before` is a synchronous `Function<ServerRequest, ServerRequest>`. It does not return a `Mono`, so it is not suitable for calling a database, an HTTP service, or verifying a token asynchronously. Use `HandlerFilterFunction` for that work.

### 2.2. after: processing the response after the handler

Conceptual signature:

~~~java
Builder after(
    BiFunction<ServerRequest, ServerResponse, ServerResponse> responseProcessor);
~~~

`after` receives the original request that passed through earlier steps and the response created by the handler. Example logging status:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/hello", request ->
        ServerResponse.ok().bodyValue("Hello"))
    .after((request, response) -> {
        System.out.println(
            request.method() + " " + request.path()
                + " -> " + response.statusCode());
        return response;
    })
    .build();
~~~

The handler still returns the response as before. `after` only observes the status and returns the response.

If a handler needs to add a header, create the header along with the response **before** writing the body. `after` uses a synchronous callback and does not return a `Mono<ServerResponse>`:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/hello", request ->
        ServerResponse.ok()
            .header("X-Response-Stage", "handler")
            .bodyValue("Hello"))
    .after((request, response) -> {
        System.out.println("Response status: " + response.statusCode());
        return response;
    })
    .build();
~~~

If you want to add a header **across all HTTP responses**, place a `WebFilter` to manipulate `ServerWebExchange.getResponse().getHeaders()` before the response commits. `ServerResponse.from(response)` only copies the status and headers, **and does not copy the body automatically**; calling `build()` on that builder does not preserve the old response's body. `HandlerFilterFunction.ofResponseProcessor` is suitable for handling responses as a `Mono` but does not solve body copying on its own.

`after` only receives a response when the handler chain completes with a normal response. If the handler emits an error instead of creating a response, there is no response for the `after` callback to process. To observe errors, use `filter` with `doOnError`/`onErrorResume` or configure error handling at the appropriate layer.

### 2.3. filter: wrapping the handler

`filter(...)` takes a `HandlerFilterFunction`. This is a functional interface with two parameters:

- `ServerRequest request`: the request after earlier steps.
- `HandlerFunction<T> next`: the next handler or filter in the chain.

Core signature:

~~~java
Mono<R> filter(
    ServerRequest request,
    HandlerFunction<T> next);
~~~

`T` and `R` are the response types; in almost all applications both are `ServerResponse`.

Example blocking requests missing an API key:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> apiKeyFilter =
    (request, next) -> {
        String apiKey = request.headers().firstHeader("X-Api-Key");

        if ("demo-secret".equals(apiKey)) {
            return next.handle(request);
        }

        return ServerResponse.status(HttpStatus.UNAUTHORIZED)
            .header(HttpHeaders.WWW_AUTHENTICATE, "ApiKey")
            .bodyValue("unauthorized");
    };
~~~

Attach the filter to the router:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/private", request ->
        ServerResponse.ok().bodyValue("private-data"))
    .filter(apiKeyFilter)
    .build();
~~~

Result:

- Request with `X-Api-Key: demo-secret`: the filter calls `next.handle(request)`; the handler executes and returns the response.
- Request missing or with a wrong API key: the filter itself returns HTTP 401; the handler does not run.

**`next.handle(request)` is the continuation point of the chain.** Calling it is optional. If not called, the filter can terminate early with its own response, such as 401, 403, or a cached response.

`filter` is more powerful than `before` and `after` because it can work reactively: call an authentication service, wait for a `Mono<Boolean>`, and only then decide whether to call the handler.

## 3. What Is HandlerFilterFunction?

`HandlerFilterFunction<T extends ServerResponse, R extends ServerResponse>` represents a handler filter function. It lets you write a lambda or method reference and reuse the same policy across multiple routers.

Notable APIs:

| API | Meaning |
| --- | --- |
| `filter(request, next)` | Applies the filter to the next handler |
| `apply(handler)` | Wraps a HandlerFunction into a filtered HandlerFunction |
| `andThen(after)` | Combines the current filter with the next filter; the current filter runs first |
| `ofRequestProcessor(...)` | Converts a request processor returning Mono<ServerRequest> into a filter |
| `ofResponseProcessor(...)` | Converts a response processor returning Mono<R> into a filter |

### 3.1. Lambda-style filter

This is the most direct way:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> logFilter =
    (request, next) -> {
        System.out.println("before: " + request.path());

        return next.handle(request)
            .doOnNext(response ->
                System.out.println(
                    "after: " + response.statusCode()));
    };
~~~

This example logs before the handler is invoked and when the response is emitted. `doOnNext` only observes the response signal; it does not change the status or body.

If you need to measure duration, use `Mono.defer` to start measuring when the subscription actually runs:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> timingFilter =
    (request, next) -> Mono.defer(() -> {
        long start = System.nanoTime();

        return next.handle(request)
            .doFinally(signal -> {
                long elapsed = System.nanoTime() - start;
                System.out.println(
                    request.path() + " completed in " + elapsed + " ns");
            });
    });
~~~

`doFinally` is called when the chain ends with complete, error, or cancel. This snippet is an instrumentation example; do not log every request with sensitive data or excessive detail if the system has high traffic.

### 3.2. ofRequestProcessor

`HandlerFilterFunction.ofRequestProcessor(...)` is suitable when the logic only needs to transform the request with a function returning `Mono<ServerRequest>`.

Signature:

~~~java
static HandlerFilterFunction<?, ?> ofRequestProcessor(
    Function<ServerRequest, Mono<ServerRequest>> requestProcessor);
~~~

Example processor:

~~~java
Function<ServerRequest, Mono<ServerRequest>> addHeader =
    request -> Mono.just(
        ServerRequest.from(request)
            .header("X-Processed-By", "request-processor")
            .build());
~~~

It represents a reactive request transformation. If preparing the request requires asynchronous I/O, you can return the corresponding Publisher from the processor instead of performing blocking inside the callback.

Because the factory returns a wildcard generic type, when assigning it to a variable with a concrete response type, you need to let Java infer it at a suitable call site or cast explicitly. In many cases, a lambda `(request, next) -> processor.apply(request).flatMap(next::handle)` is easier to read and clearer with generic types.

### 3.3. ofResponseProcessor

`ofResponseProcessor` is suitable when you only need to transform the response with a function returning `Mono<R>`.

Signature:

~~~java
static <T extends ServerResponse, R extends ServerResponse>
HandlerFilterFunction<T, R> ofResponseProcessor(
    Function<T, Mono<R>> responseProcessor);
~~~

Example of reactively observing the response **without rebuilding/losing the body** (the snippet needs `import reactor.core.publisher.Mono;`):

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> auditResponse =
    HandlerFilterFunction.ofResponseProcessor(response ->
        Mono.just(response)
            .doOnNext(res ->
                System.out.println("status=" + res.statusCode())));
~~~

Attach to the router:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/hello", request ->
        ServerResponse.ok().bodyValue("Hello"))
    .filter(auditResponse)
    .build();
~~~

`ofResponseProcessor` takes a processor returning `Mono<ServerResponse>` so it can do asynchronous work, record metrics, or handle errors appropriately; here it returns **the exact original response** to preserve the body. If you need to add a header to every response without rebuilding the body, use a `WebFilter` at the exchange layer; do not just do `ServerResponse.from(response).header(...).build()`.

### 3.4. Combining multiple HandlerFilterFunctions

`andThen` creates a combined filter. The Javadoc defines the order: **the current filter runs first, followed by the filter passed to andThen**.

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> first =
    (request, next) -> {
        System.out.println("filter-1");
        return next.handle(request);
    };

HandlerFilterFunction<ServerResponse, ServerResponse> second =
    (request, next) -> {
        System.out.println("filter-2");
        return next.handle(request);
    };

HandlerFilterFunction<ServerResponse, ServerResponse> combined =
    first.andThen(second);
~~~

`combined` can be attached to a router with `.filter(combined)`. For filters before/after a handler, write tests to verify execution order and avoid relying on an unverified assumption when a chain has multiple nested layers.

## 4. Filter Scope: Top-Level and Nested Routes

An important point in WebFlux.fn is that **a filter only applies to routes built within the corresponding RouterFunction.Builder scope**.

Example:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .path("/people", people -> people
        .GET("/{id}", handler::getPerson)
        .GET(handler::listPeople)
        .before(request -> ServerRequest.from(request)
            .header("X-Group", "people")
            .build()))
    .GET("/health", handler::health)
    .after((request, response) -> {
        logResponse(response);
        return response;
    })
    .build();
~~~

In the example:

- `before` sits inside `/people`'s builder, so it only applies to the two GET routes in that group.
- `after` sits on the outer builder, so it applies to the routes created by the outer builder, including nested routes.
- `/health` is a top-level route; it does not receive the `X-Group` header.
- `after` still observes responses of `/health` and nested routes.

Model:

~~~text
Outer builder
  |
  +-- path("/people")
  |      |
  |      +-- GET /people/{id}
  |      +-- GET /people
  |      +-- before: X-Group=people
  |
  +-- GET /health
  |
  +-- after: log responses for routes of the outer builder
  +-- build()
~~~

If you add a `filter` to a nested builder, that filter only applies to routes belonging to that nested builder. If you add a `filter` on the outer builder, it applies to all routes created by the outer builder.

This is why you should group routes by business scope or shared policy:

- `/admin/**`: requires admin authorization.
- `/internal/**`: adds trace metadata or checks network policy.
- `/public/**`: has its own cache/headers policy.
- Top-level `/health`: may not need business filters.

Do not place a sensitive filter on an overly broad builder if public routes or health endpoints sit in the same scope.

## 5. Route Order and Filter Order Are Two Different Things

**RouterFunction** evaluates routes in composition order. The first matching route is used; if it does not match, the next route is tried. Therefore, specific routes should be declared before general routes.

Example:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/users/me", handler::currentUser)
    .GET("/users/{id}", handler::userById)
    .GET("/users/**", handler::fallback)
    .build();
~~~

`/users/me` should come before `/users/{id}` and catch-all. This mechanism differs from annotated controllers, where Spring uses a comparator to pick the more specific mapping.

Filter order is the order of wrapping around the handler. You can picture it as:

~~~text
Filter A enters
    Filter B enters
        Handler runs
    Filter B receives response
Filter A receives response
~~~

When filter A calls `next.handle(request)`, it transfers control to the next part. When the Publisher returns the response, the filter's post-processing steps run in reverse order.

With `HandlerFilterFunction.andThen`, the order is clearly defined: the current filter first, the second filter next. With a builder that has multiple filters and nested builders, verify scope and order with integration tests rather than inferring from text placement in a file.

## 6. Choosing before, after, or filter?

| Requirement | Suitable choice | Reason |
| --- | --- | --- |
| Add a synchronous header/attribute to the request | `before` | A request → request function is enough |
| Log method/path before the handler | `before` | Only needs to observe the request |
| Log status after the response | `after` | Has both request and response |
| Add a response header with synchronous processing | Can use `after` if there is a way to create the response synchronously; usually use filter when a reactive builder is needed | `after` does not return Mono |
| Verify a token via a reactive service | `filter` | Can wait for Mono before invoking the handler |
| Block a request and return 401/403 | `filter` | No need to call next |
| Handle errors from the handler into a fallback response | `filter` with onErrorResume or builder `onError` | Can observe error signals |
| Add a response header with the ServerResponse builder | `ofResponseProcessor` | Response builder returns Mono |
| Measure complete, error, and cancel together | `filter` with `doFinally` | Wraps the Publisher's lifecycle |
| CORS for the whole WebFlux app | `CorsWebFilter` or WebFlux CORS configuration | CORS is a web-filter-layer concern |
| Security for the entire application | Spring Security/WebFilter chain | Protection scope is broader than functional routers |

Practical rules:

- Use **before** for simple, synchronous request transformations.
- Use **after** for synchronous response observation/transformation.
- Use **HandlerFilterFunction** when you need chain control, asynchronous processing, or replacing the response.
- Use **WebFilter** when a policy must apply across the entire WebFlux application, not only functional routes.

## 7. Asynchronous Processing in HandlerFilterFunction

A filter can call a reactive service to decide whether to let the request proceed:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> authorizationFilter =
    (request, next) -> request.principal()
        .flatMap(principal ->
            authorizationService.canAccess(principal, request.path()))
        .flatMap(allowed -> {
            if (allowed) {
                return next.handle(request);
            }
            return ServerResponse.status(HttpStatus.FORBIDDEN).build();
        });
~~~

This is an **illustrative snippet**, assuming `authorizationService.canAccess(...)` returns `Mono<Boolean>`. The filter reads the principal from the request, checks permissions asynchronously, and then:

- `true`: calls the next handler.
- `false`: returns 403.
- Error from the authorization service: the error travels down the chain, unless the filter has its own error handling.

Do not use `block()` to wait for the authorization result. Blocking can stall the event loop and break WebFlux's non-blocking benefits.

Do not call `subscribe()` manually in a filter. Return the Publisher to the chain so Reactor manages cancellation, errors, completion, and backpressure.

### 7.1. 401 and 403

- **401 Unauthorized**: the request is not authenticated or credentials are invalid; the system usually needs an appropriate challenge in `WWW-Authenticate`.
- **403 Forbidden**: the identity is known or lacks permission to perform the operation.

An illustrative filter does not replace full Spring Security. In production, use a standard authentication/authorization chain, not just comparing a free-form header against a fixed secret string.

### 7.2. Filters can short-circuit

Cache example:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> cacheFilter =
    (request, next) -> cache.find(request.path())
        .flatMap(cached -> ServerResponse.ok().bodyValue(cached))
        .switchIfEmpty(Mono.defer(() -> next.handle(request)));
~~~

This is an illustrative example; assuming `cache.find(path)` returns `Mono<String>`. If the cache has data, the handler does not run. If the cache is empty, the filter calls the handler.

In practice, consider cache keys by query, user/tenant, Accept header, and authorization. Do not return a shared cache to different users solely because the URL matches.

## 8. Error Handling in Filters and RouterFunctions.Builder

`after` receives a successful response; it is not the right place to convert exceptions into HTTP error responses. There are several options:

### 8.1. Using onErrorResume in HandlerFilterFunction

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> errorFilter =
    (request, next) -> next.handle(request)
        .onErrorResume(IllegalArgumentException.class, error ->
            ServerResponse.badRequest()
                .bodyValue("invalid request"));
~~~

If the handler emits `IllegalArgumentException`, the filter replaces that error with HTTP 400. Other error types continue to propagate.

### 8.2. Using onError on RouterFunctions.Builder

The builder also has `onError` overloads by exception class or predicate:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/items/{id}", handler::getItem)
    .onError(IllegalArgumentException.class,
        (error, request) ->
            ServerResponse.badRequest().build())
    .build();
~~~

This mechanism attaches an error-to-response policy to the router builder. Choose a narrow enough scope and do not turn every system error into 400.

### 8.3. When application-wide error handling is needed

If exceptions can arise from multiple routes, annotated controllers, or WebFlux infrastructure, use an application-wide error handling mechanism such as `WebExceptionHandler`, Spring Security, or appropriate configuration. Do not duplicate the same policy across multiple filters if it can be handled at a shared boundary.

Do not include internal errors, stack traces, or credentials in the response body. Log with a correlation ID and return a safe error representation.

## 9. Distinguishing HandlerFilterFunction and WebFilter

The two APIs have similar names but different scopes:

| Criterion | HandlerFilterFunction | WebFilter |
| --- | --- | --- |
| Layer | WebFlux.fn / RouterFunction | WebFlux WebHandler chain |
| Scope | Routes attached to the RouterFunction/builder | All requests passing through the WebFlux filter chain |
| Function signature | `ServerRequest` + next `HandlerFunction` → `Mono<ServerResponse>` | `ServerWebExchange` + next `WebFilterChain` → `Mono<Void>` |
| Suitable for | Per-route filters, groups of functional endpoints, ServerResponse-style responses | Security, CORS, tracing, request-wide policies |
| Applies to annotated controllers? | Not automatically | Yes, if the request passes through the WebFlux chain |

WebFilter example:

~~~java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
class RequestIdWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = exchange.getRequest()
            .getHeaders()
            .getFirst("X-Request-Id");

        if (requestId == null || requestId.isBlank()) {
            requestId = UUID.randomUUID().toString();
        }

        exchange.getResponse().getHeaders()
            .set("X-Request-Id", requestId);

        return chain.filter(exchange);
    }
}
~~~

This is **illustrative code** that requires importing `WebFilter`, `WebFilterChain`, `ServerWebExchange`, `Mono`, `Component`, `Order`, `Ordered`, and `UUID`. WebFilter intervenes at the WebExchange level and applies to requests passing through WebFlux, including functional endpoints and annotated controllers.

**Do not register the same policy as both a global WebFilter and a per-route HandlerFilterFunction** if not needed. That can cause logging, auth, or response headers to run twice.

### CORS

Spring WebFlux provides a dedicated `CorsWebFilter` for CORS on functional endpoints. Do not write a small filter yourself just to add `Access-Control-Allow-Origin` while ignoring preflight, credentials, allowed headers, and Spring Security policies. CORS is a policy at the web boundary, so configure it using the standard CORS mechanism.

## 10. Things to Be Careful About with Request Bodies and Response Bodies

### 10.1. The request body is a stream

In WebFlux, a request body is represented by a Publisher such as `Mono` or `Flux`. A filter should not arbitrarily read the body just to log it and then continue calling the handler, because reading can consume the stream. If you need to inspect the payload, you must design caching/replay or use a reading mechanism appropriate for the body and size limits.

Avoid:

~~~java
// Illustrative anti-pattern: read the body to log it and expect the handler to read it again.
request.bodyToMono(String.class)
    .doOnNext(System.out::println)
    .then(next.handle(request));
~~~

The snippet above does not automatically recreate the request body for the handler. The handler may no longer be able to read the data as expected.

If you truly need to inspect the body, use an explicit solution to buffer/rebuild the request, set byte limits, and consider sensitive data. Do not log passwords, access tokens, or personal information.

### 10.2. The response body can also be a stream

A response can contain a `Flux<DataBuffer>` or a large data Publisher. Ordinary response filters should modify status/headers/metadata; they should not subscribe to or read the body for logging because doing so will consume the stream or alter backpressure.

If you need to log response content, you need a bounded decorator/buffering strategy and must consider memory, streaming, cancellation, latency, and privacy.

## 11. Complete Java 17+ Spring Boot WebFlux Program

The example below creates three routes:

- `GET /api/hello`: `before` adds a request header for the handler to read.
- `GET /api/private`: nested `HandlerFilterFunction` checks an API key and can block.
- `GET /public`: top-level route that does not receive the request header applied only inside the `/api` group.
- `after` on the outer builder logs responses for the routes belonging to the builder.
- A response filter adds the `X-Response-Filter` header for routes created by the outer builder.

Requirements: **Java 17+**, **Maven 3.6.3+**, and Spring Boot 4.1.2. Use a patch release supported by your organization in a real project; the Boot BOM manages Spring Framework and Reactor.

### 11.1. Project structure

~~~text
functional-filter-demo/
  pom.xml
  src/main/java/example/filterdemo/FilterDemoApplication.java
  src/main/java/example/filterdemo/FunctionalRoutes.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>functional-filter-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

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

### 11.3. Startup class

**src/main/java/example/filterdemo/FilterDemoApplication.java**

~~~java
package example.filterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
~~~

### 11.4. Router and filters

**src/main/java/example/filterdemo/FunctionalRoutes.java**

~~~java
package example.filterdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.server.HandlerFilterFunction;
import org.springframework.web.reactive.function.server.HandlerFunction;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.WebFilter;

@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> routes() {

        HandlerFunction<ServerResponse> hello = request -> {
            String source = request.headers()
                    .firstHeader("X-Request-Source");

            return ServerResponse.ok()
                    .bodyValue("hello; source=" + source);
        };

        HandlerFunction<ServerResponse> privateData = request ->
                ServerResponse.ok().bodyValue("private-data");

        HandlerFilterFunction<ServerResponse, ServerResponse> apiKeyFilter =
                (request, next) -> {
                    String key = request.headers()
                            .firstHeader("X-Api-Key");

                    if ("demo-secret".equals(key)) {
                        return next.handle(request);
                    }

                    return ServerResponse.status(HttpStatus.UNAUTHORIZED)
                            .header(HttpHeaders.WWW_AUTHENTICATE, "ApiKey")
                            .bodyValue("unauthorized");
                };

        return RouterFunctions.route()
                .path("/api", api -> api
                        .GET("/hello", hello)
                        .path("/private", privateRoute -> privateRoute
                                .GET(privateData)
                                .filter(apiKeyFilter))
                        .before(request -> ServerRequest.from(request)
                                .header("X-Request-Source", "router-before")
                                .build())
                )
                .GET("/public", request ->
                        ServerResponse.ok().bodyValue("public"))
                .after((request, response) -> {
                    System.out.println(
                            request.method() + " " + request.path()
                                    + " -> " + response.statusCode());
                    return response;
                })
                .build();
    }

    @Bean
    WebFilter responseHeaderFilter() {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders()
                    .set("X-Response-Filter", "applied");
            return chain.filter(exchange);
        };
    }
}
~~~

**Scope explanation:**

- `before` sits inside the `/api` builder, so `/api/hello` and `/api/private` receive `X-Request-Source`.
- The `apiKeyFilter` filter sits inside the `/private` builder, so it only protects the `/api/private` route.
- `after` sits on the outer builder, so it logs responses from both nested routes and `/public`.
- The `responseHeaderFilter` bean is a `WebFilter` at the HTTP exchange layer, applying to `/api` and `/public`, setting the header before the response commits **without changing the body**.
- `/public` does not have `X-Request-Source` because it sits outside the `/api` builder.

### 11.5. Running the application

In the directory containing `pom.xml`:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

The application runs on port 8080 by default.

**Request 1 — before added the header:**

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Expected body:

~~~text
hello; source=router-before
~~~

The response has the header:

~~~text
X-Response-Filter: applied
~~~

**Request 2 — missing API key, filter blocks:**

~~~bash
curl -i http://localhost:8080/api/private
~~~

Expected result:

~~~text
HTTP/1.1 401 Unauthorized

unauthorized
~~~

The `privateData` handler does not run because the filter does not call `next.handle(request)`.

**Request 3 — with API key:**

~~~bash
curl -i http://localhost:8080/api/private \
  -H "X-Api-Key: demo-secret"
~~~

Body:

~~~text
private-data
~~~

**Request 4 — top-level route:**

~~~bash
curl -i http://localhost:8080/public
~~~

Body:

~~~text
public
~~~

The response still has `X-Response-Filter` and the outer builder's `after` log, but does not have the `X-Request-Source` header because `before` only sits inside the `/api` builder.

The status log lines look like:

~~~text
GET /api/hello -> 200 OK
GET /api/private -> 401 UNAUTHORIZED
GET /api/private -> 200 OK
GET /public -> 200 OK
~~~

The exact status formatting depends on the `HttpStatusCode.toString()` implementation; this is the expected log shape, not a production log-format contract.

**Demo note:** the fixed API key is only used to illustrate short-circuiting. Do not store secrets directly in source code, and do not build a production authentication system out of a single header comparison.

## 12. Testing with WebTestClient

You can test filters at the HTTP level instead of calling the handler directly:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FunctionalFilterTests {

    @Autowired
    WebTestClient client;

    @Test
    void beforeAndResponseFilterAreApplied() {
        client.get()
                .uri("/api/hello")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("X-Response-Filter", "applied")
                .expectBody(String.class)
                .isEqualTo("hello; source=router-before");
    }

    @Test
    void apiKeyFilterCanShortCircuit() {
        client.get()
                .uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectBody(String.class)
                .isEqualTo("unauthorized");
    }

    @Test
    void validApiKeyCallsTheHandler() {
        client.get()
                .uri("/api/private")
                .header("X-Api-Key", "demo-secret")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("private-data");
    }

    @Test
    void topLevelRouteIsOutsideApiBeforeScope() {
        client.get()
                .uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("X-Response-Filter", "applied")
                .expectBody(String.class)
                .isEqualTo("public");
    }
}
~~~

This is an **illustrative test snippet** requiring JUnit, `@Autowired`, `@SpringBootTest`, `WebTestClient`, and Spring Boot's test dependencies. It assumes the application and route bean from the previous section are in the same application context.

These tests verify:

- Headers from `before` reach the handler.
- The response filter adds headers properly.
- The filter can return 401 without running the handler.
- Valid credentials allow the handler to run.
- Nested builder scope is preserved properly.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `before` to call a database or WebClient | Callback does not support Publisher; easy to block the event loop | Use HandlerFilterFunction with Mono/Flux |
| Thinking `after` can handle exceptions | No response is passed to the callback if the handler errors | Use filter onErrorResume or RouterFunctions.Builder.onError |
| Forgetting to call `next.handle(request)` | Handler does not run; filter may short-circuit unintentionally | Call next on allowed branches |
| Calling `next.handle(request)` multiple times | Can execute the handler multiple times and repeat side effects | Design one clear forwarding call |
| Calling `subscribe()` in a filter | Loses chain lifecycle/error/cancel/backpressure | Return Mono from the filter and compose |
| Using `block()` to wait for an auth service | Blocks the thread, can stall the Netty event loop | Compose with flatMap |
| Placing a filter on an overly broad top-level builder | Public/health routes may have unnecessary policies applied | Place the filter in a properly scoped nested builder |
| Thinking a nested filter automatically applies to top-level routes | Top-level routes are not inside the nested scope | Attach the filter on the builder containing the routes to filter |
| Mutating ServerRequest/ServerResponse directly | Immutable contract; copying status/headers does not copy the body | Use `ServerRequest.from`; create a response with an explicit body or add global headers with `WebFilter` |
| Reading the request body in a filter to log it and then calling next | The body stream may have already been consumed | Design bounded buffer/replay or do not read the body |
| Logging the full request/response | May expose passwords, tokens, personal data | Choose safe fields, redaction, and log limits |
| Using HandlerFilterFunction for all controllers | Filter only applies to RouterFunction, does not automatically cover annotated controllers | Use WebFilter when full WebFlux scope is needed |
| Handling CORS manually with arbitrary headers | Misses preflight, credentials, and policies | Use standard CorsWebFilter/CORS config |
| Treating a demo API key filter as production security | Lacks rotation, secret storage, identity, and authorization | Use Spring Security and appropriate authentication mechanisms |
| Testing only the handler, not the filter chain | Misses scope, order, and short-circuit bugs | Test HTTP with WebTestClient |

## 14. Filter Design Checklist Before Production

- [ ] Determine whether the filter applies to one route, a group of nested routes, or the whole application.
- [ ] Choose `before` if only transforming the request synchronously.
- [ ] Choose `after` if only observing/transforming the response synchronously.
- [ ] Choose `HandlerFilterFunction` if reactive I/O, short-circuiting, response mapping, or error handling is needed.
- [ ] Verify every authorized branch calls `next.handle(request)` exactly once.
- [ ] Do not call `subscribe()` or `block()` in a filter.
- [ ] Do not consume the request/response body just to log it without a safe replay/buffering mechanism.
- [ ] Use WebFilter for application-wide WebFlux policies.
- [ ] Use Spring Security for real authentication and authorization.
- [ ] Use standard CORS infrastructure.
- [ ] Do not put secrets or sensitive payloads in logs/responses.
- [ ] Test nested scope, top-level routes, response headers, 401/403, errors, and cancellation.
- [ ] Verify filter order when there are multiple layers or `andThen`.
- [ ] Measure filter latency and overhead under production-like workloads.

## 15. Self-Check

**Question 1.** Can `before` return `Mono<ServerRequest>`?

No. It takes a synchronous `Function<ServerRequest, ServerRequest>`. If you need an asynchronous request processor, use `HandlerFilterFunction` or an appropriate adapter.

**Question 2.** Can `after` call the handler again?

It should not. `after` receives the response already created by the handler and processes that response. Controlling handler invocation belongs to `filter`.

**Question 3.** Must `filter` always call `next.handle(request)`?

No. A filter can return a response itself to block the request. If it allows processing to continue, it calls next.

**Question 4.** Does `HandlerFilterFunction` apply to all annotated controllers?

No. It belongs to WebFlux.fn and RouterFunction. To apply across the WebFlux request chain for the entire application, use WebFilter.

**Question 5.** Why is filter more suitable than before when checking permissions via Mono<Boolean>?

Because `filter` returns `Mono<ServerResponse>` and can compose asynchronously; `before` is only a synchronous request → request function.

**Question 6.** Does a filter inside the nested builder `/admin` affect `/public`?

No. The filter only applies to routes created by that builder. `/public` sits on the outer builder.

**Question 7.** Does `after` run if the handler emits an error?

Usually not, because the callback requires a successful response as input. To observe errors, use filter/error handling.

**Question 8.** What should you do if you want to add a header to `ServerResponse` after the handler returns a response?

Set the header in `ServerResponse` when the handler creates the response; for global headers, use `WebFilter` before commit. `ofResponseProcessor` is suitable for reactive observation/transformation, but `ServerResponse.from(response)` does not automatically preserve the body.

**Question 9.** Why not read the body in a filter and then call next as usual?

The body is a stream; reading can consume the data. To read and forward, you need a bounded buffer/replay strategy and resource management.

**Question 10.** When do you use WebFilter instead of HandlerFilterFunction?

When the policy must apply to the entire WebFlux WebHandler chain, including both functional endpoints and annotated controllers.

## 16. Official References

- [Spring Framework — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): RouterFunction, HandlerFunction, nested routes, and filtering handler functions.
- [Spring Framework — HandlerFilterFunction JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/HandlerFilterFunction.html): filter signatures, apply, andThen, ofRequestProcessor, and ofResponseProcessor.
- [Spring Framework — RouterFunctions.Builder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html): before, after, filter, onError, path, nest, and build.
- [Spring Framework — ServerRequest JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): request access and ServerRequest.from.
- [Spring Framework — ServerResponse JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): response builder and ServerResponse.from.
- [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): WebFilter, WebHandler chain, and CORS.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): how Spring Boot registers WebFilter and filter ordering.
- [Spring Security — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): securing WebFlux applications with the security chain.

**Key takeaway:** `before` transforms the request synchronously, `after` processes the response synchronously, and `HandlerFilterFunction` wraps the handler and can process asynchronously, short-circuit, or replace the response. A filter's scope depends on the RouterFunction.Builder where it is registered: nested filters only apply to nested routes, while an outer builder's filter covers routes belonging to that builder. Use WebFilter for WebFlux-wide policies, Spring Security for authentication/authorization, and standard CORS infrastructure for CORS.