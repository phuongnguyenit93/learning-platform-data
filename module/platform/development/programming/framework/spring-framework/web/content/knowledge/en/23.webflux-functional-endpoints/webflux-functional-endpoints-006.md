# Router Filters, Error Handling, and Unified Responses in Functional WebFlux

> **Scope:** Spring Framework 6.2.x, Spring Boot 3.5.x, Java 17+, and **WebFlux.fn** (`org.springframework.web.reactive.function.server` package). This lesson focuses on `RouterFunctions.Builder.before`, `after`, `filter`, `onError`, standardizing status/headers/JSON errors with a response factory, and the boundary between router-local filters and application-wide `WebFilter`/`ErrorWebExceptionHandler`. The complete demo uses `Mono<ServerResponse>`, Spring Reactive Web, cURL, and `WebTestClient`. Do not confuse with **WebMvc.fn**: MVC handlers return synchronous `ServerResponse` and run on the Servlet stack.

## 1. Why do routers need filters and an error policy?

When an API has many handlers, cross-cutting concerns such as request IDs, status logging, policy-based request blocking, input error classification, and error response formatting tend to get duplicated across methods. Using filters and a response factory avoids duplicate logic and provides a consistent HTTP contract for mobile and web clients.

```text
HTTP request
     |
WebFilter / Spring Security            [application-wide]
     |
DispatcherHandler
     |
RouterFunctionMapping
     |
RouterFunction + RequestPredicate     [only when route matches]
     |
  before / filter
     |
  next.handle(ServerRequest)
     |
  Mono<ServerResponse>
     |
  onError -> Mono<ServerResponse>      [if error within scope]
     |
  after (observe response object)
     |
ServerResponseResultHandler + codecs
     |
HTTP response bytes
```

This diagram is a **responsibility model**, not a guarantee that every filter runs in the exact drawn order. Spring composes filters by registration order and builder scope; whenever ordering is a business requirement, make it explicit and test it. Moreover, constructing a `ServerResponse` does not mean the body has finished transmitting to the client.

### 1.1. Desired outcomes

- Success: accurate HTTP statuses (200, 201, 204), clean DTO/JSON responses, and `X-Request-Id`.
- Business failures: realistic HTTP 400/404/409 or 5xx statuses with a stable `application/problem+json` body.
- Machine-readable error codes (`code`) so frontends can branch without parsing English `detail` text.
- Never leak raw exceptions, stack traces, passwords, SQL connection strings, or tenant data in responses.
- Unmatched paths, decoder failures, security rejections, and mid-stream errors require a **global** strategy for system-wide consistency.

**Standardizing responses does not mean always returning HTTP 200 with `{"success":false}`.** HTTP status codes are part of your API contract and monitoring.

## 2. WebFlux.fn foundations

Functional WebFlux expresses routing and behavior using interfaces:

| Component | Meaning | Representative API |
| --- | --- | --- |
| `RouterFunction<ServerResponse>` | Selects handler when request matches | `RouterFunctions.route()` |
| `HandlerFunction<ServerResponse>` | Handles request, returns reactive response | `Mono<ServerResponse> handle(ServerRequest)` |
| `ServerRequest` | URI/method/headers/query/body/attributes | `pathVariable`, `queryParam`, `bodyToMono` |
| `ServerResponse` | Status, headers, and response body | `status`, `ok`, `created`, `bodyValue`, `body` |
| `RequestPredicate` | Route condition | `accept`, `contentType`, `method`, `path` |
| `HandlerFilterFunction` | Wraps handler chain | `filter((request, next) -> ...)` |

Example router bean:

```java
@Bean
RouterFunction<ServerResponse> routes(BookHandler handler) {
    return RouterFunctions.route()
            .GET("/api/books", handler::list)
            .GET("/api/books/{id}", handler::get)
            .POST("/api/books", handler::create)
            .build();
}
```

This is a snippet in a configuration class requiring `BookHandler` and imports. Handler methods have the signature:

```java
Mono<ServerResponse> get(ServerRequest request) {
    // Combine data and build ServerResponse asynchronously.
}
```

In WebFlux.fn, **`RouterFunction`s are evaluated in order**, so static routes like `/api/books/stats` must come before `/api/books/{id}`. Do not rely on annotated `@GetMapping` comparator rules assuming Spring reorders routes automatically.

## 3. Scope: router filters vs. WebFilter

| Tool | Where does it operate? | Recommended use |
| --- | --- | --- |
| `RouterFunctions.Builder.before` | Matched handlers in the builder | Attach request metadata, request attributes |
| `RouterFunctions.Builder.after` | Response object from builder routes | Logging/tracing response metadata |
| `RouterFunctions.Builder.filter` | Functional handler chain in the builder | Precondition checks, short-circuiting, wrapping |
| `RouterFunctions.Builder.onError` | Matching errors raised inside handler/filter chain | Map domain exceptions to HTTP errors |
| `RouterFunction.filter(...)` | An existing `RouterFunction` | Apply a reusable handler filter |
| `WebFilter` | Application-wide reactive HTTP handler chain | Auth, global request ID, CORS, observation |
| `ErrorWebExceptionHandler` | Unhandled errors from the `WebHandler` chain | Fallback, codec/routing errors |
| `@RestControllerAdvice` | Primarily annotation-based controller methods | Annotation exception handling |

**Boundary to remember:** router filters generally run only if that router **found a matching handler**. A request like `GET /path-not-exist` can bypass `before`, `filter`, and `onError` on that router completely. Therefore, do not document in a README or API spec that "all 404s have the same Problem Details schema as router-local 404s" unless global error handling is configured.

### 3.1. Nested filters apply only to their group

```java
RouterFunction<ServerResponse> router = RouterFunctions.route()
        .path("/api", api -> api
                .GET("/public", handler::publicData)
                .path("/private", secured -> secured
                        .GET("/account", handler::account)
                        .filter(privateFilter)))
        .filter(commonFilter)
        .build();
```

This is a snippet requiring handlers and filters to be defined. The filter inside the nested `private` builder applies only to private routes, whereas the outer filter wraps all routes on the outer builder. Whenever adding a new route, verify it falls within the intended filter scope. Production authentication/authorization must be enforced by the Spring Security reactive filter chain and object-level checks, not solely by an easily overlooked router-local lambda.

## 4. before: transforming ServerRequest

`before` takes a `ServerRequest -> ServerRequest` function:

```java
.before(request -> ServerRequest.from(request)
        .header("X-Internal-Mode", "demo")
        .build())
```

This snippet transforms the request abstraction for matched handlers. Never overwrite `Authorization`, `Host`, or `X-Forwarded-*` casually and treat the result as trusted. Request headers can still originate from clients.

### 4.1. Generating a request ID

`ServerRequest.attributes()` returns a mutable map of request attributes. You can use:

```java
.before(request -> {
    request.attributes().computeIfAbsent(
            "demoRequestId",
            ignored -> UUID.randomUUID().toString());
    return request;
})
```

This snippet requires importing `java.util.UUID`. The request ID is stored in the map, yet **does not appear automatically on the response header**. The response factory must read and write `X-Request-Id`. When multiple filters exist with complex ordering, `computeIfAbsent` ensures the same request keeps one consistent ID if none was set earlier.

### 4.2. Do not block in before

This is an anti-pattern:

```java
// Wrong: blocks reactive event loop and consumes body outside main lifecycle.
.before(req -> {
    CreateBook body = req.bodyToMono(CreateBook.class).block();
    return req;
})
```

`before` should perform cheap metadata operations. If you need to decode and validate JSON, do so inside the handler's reactive pipeline or a filter designed to consume/decorate the body **exactly once**. Never call `bodyToMono()` in a filter and read the body a second time in the handler without an explicitly designed replay mechanism.

## 5. filter: wrapping and short-circuiting

`filter` takes a `HandlerFilterFunction`:

```java
.filter((request, next) -> {
    if (shouldReject(request)) {
        return ServerResponse.status(HttpStatus.SERVICE_UNAVAILABLE)
                .build();
    }
    return next.handle(request);
})
```

This is a snippet: `shouldReject` must be defined. If `next.handle(request)` is not invoked, the business handler never runs. `next.handle(...)` returns `Mono<ServerResponse>`; filters can compose via `map`/`flatMap`/`doFinally` without calling `block()`.

### 5.1. A clear short-circuit example

```java
.filter((request, next) -> {
    if ("yes".equalsIgnoreCase(
            request.headers().firstHeader("X-Demo-Block"))) {
        return ApiHttp.problem(request,
                HttpStatus.SERVICE_UNAVAILABLE,
                "DEMO_BLOCKED",
                "Demo request was blocked");
    }
    return next.handle(request);
})
```

`X-Demo-Block` is a **client-controlled** header used purely for illustration. Never use this header as proof of user privileges or as a production maintenance switch. For real maintenance mode, read state from trusted server-side configuration.

### 5.2. Observation does not mean the body has finished sending

```java
.filter((request, next) -> {
    long begin = System.nanoTime();
    return next.handle(request)
            .doOnNext(response -> recordStatus(
                    response.statusCode().value()))
            .doFinally(signal -> recordTime(
                    System.nanoTime() - begin, signal));
})
```

This is a snippet requiring `recordStatus` and `recordTime` functions. It tracks the lifecycle of the **`Mono` building `ServerResponse`**, not necessarily the entire HTTP body transmission. An SSE stream can continue emitting for minutes after the response object is created. End-to-end metrics should integrate at the proper HTTP/server Observation layer.

### 5.3. When not to use a router filter?

Never replace Spring Security `SecurityWebFilterChain` with logic inspecting client-supplied `X-Role` headers. Authentication, sessions, CSRF, and CORS belong in the global reactive web/security layer. Router filters fit route-specific preconditions, scoped policies, logging, and response preparation.

## 6. after: observing ServerResponse

`after` takes `(ServerRequest, ServerResponse) -> ServerResponse`.

```java
.after((request, response) -> {
    System.out.printf("path=%s status=%d%n",
            request.path(),
            response.statusCode().value());
    return response;
})
```

In production, use SLF4J/Micrometer instead of stdout; redact logs and never record tokens, cookies, or sensitive bodies. Do not interpret the moment `after` runs as "the client has received all bytes".

**Body-loss trap:** to add a header, do not hastily write `ServerResponse.from(response).header(...).build()`. Constructing a new response from status/headers and calling `build()` without copying the body publisher drops the payload. The demo uses **response factories** that set status and headers as each response is built rather than mutating an existing response object.

### 6.1. Exceptions in after

If `after` throws an exception, the outcome depends on filter composition and whether the response has committed. Logging/observation helpers must never break responses; avoid blocking I/O or error-prone work inside `after`. Test callback/filter ordering when adding nested builders.

## 7. onError: classifying exceptions within router scope

A router-level error mapper:

```java
.onError(BadInputException.class,
        (ex, request) -> ApiHttp.problem(
                request, HttpStatus.BAD_REQUEST,
                "INVALID_INPUT", ex.getMessage()))
```

The response provider signature in **WebFlux.fn** is a function returning `Mono<ServerResponse>`. In **WebMvc.fn**, it returns synchronous `ServerResponse`. This is a very common reason code copied between the two modules fails to compile.

### 7.1. Three error categories to separate

```text
BadInputException          -> HTTP 400 + INVALID_INPUT
ItemMissingException       -> HTTP 404 + ITEM_NOT_FOUND
IllegalStateException      -> HTTP 500 + INTERNAL_ERROR (demo)
```

These mappings are application-designed; Spring does not automatically assign statuses to custom exceptions. For domain conflicts you can add `ConflictException -> 409`, backed by a specific cause such as duplicate resource name or optimistic locking failure. Never map **every `IllegalArgumentException`** to 400 in production, because programming bugs can also throw `IllegalArgumentException`.

### 7.2. onError vs. onErrorResume

- `onErrorResume` inside a service/publisher handles a specific business failure: falling back to a remote source, converting a missing value into a typed exception, or controlled cleanup.
- `RouterFunctions.Builder.onError` converts errors in the functional handler chain into a **consistent HTTP response** for that group of routes.
- `ErrorWebExceptionHandler` handles **global** unhandled exceptions from the web handler chain.

Service fallback example:

```java
return service.find(id)
        .onErrorResume(RemoteTimeoutException.class,
                ex -> cachedService.find(id))
        .flatMap(book -> ServerResponse.ok().bodyValue(book));
```

This snippet applies only when cached results are genuinely allowed. Never fall back authorization data to broadened permissions, and never add `onErrorResume(ex -> Mono.empty())` across all errors, which causes silent partial results.

### 7.3. Synchronous vs. reactive errors

A handler can throw `BadInputException` synchronously while parsing parameters:

```java
long id = Long.parseLong(request.pathVariable("id"));
return service.find(id).flatMap(item -> ServerResponse.ok().bodyValue(item));
```

Or receive `Mono.error(...)` after an async operation:

```java
return service.find(id)
        .switchIfEmpty(Mono.error(new ItemMissingException()))
        .flatMap(item -> ServerResponse.ok().bodyValue(item));
```

These occur at two different moments. Route `onError` is designed to handle errors from the handler chain, though you should always test both synchronous exceptions and reactive error signals on your target Spring version.

## 8. A unified RFC 9457 error contract

**RFC 9457 Problem Details** defines standard fields for error representations. The demo uses a custom record with these fields:

| Field | Role |
| --- | --- |
| `type` | URI reference identifying the error type, e.g., `about:blank` |
| `title` | Stable error title matching the HTTP status |
| `status` | Numeric status matching the HTTP response status |
| `detail` | Client-safe details without leaking secrets |
| `instance` | Resource/request path where the error occurred |
| `code` | Stable custom error code for programmatic client handling |
| `requestId` | Correlation ID for logs and support |

Sample response:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
X-Request-Id: <server-generated-id>

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Item not found",
  "instance": "/api/items/999",
  "code": "ITEM_NOT_FOUND",
  "requestId": "<same-server-generated-id>"
}
```

This is an illustrative shape, not a fixed `requestId`. The two extension members `code` and `requestId` are valid under RFC 9457 and should be documented in your API contract. When no dedicated problem type URI exists, `about:blank` is appropriate.

### 8.1. Should you use Spring's ProblemDetail?

Spring Framework provides `org.springframework.http.ProblemDetail`, for example:

```java
ProblemDetail pd = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "Item not found");
pd.setTitle("Not Found");
pd.setType(URI.create("about:blank"));
pd.setInstance(URI.create("/api/items/999"));
pd.setProperty("code", "ITEM_NOT_FOUND");
```

This is a snippet requiring imports. It can be written via `ServerResponse.status(NOT_FOUND).contentType(APPLICATION_PROBLEM_JSON).bodyValue(pd)` with a suitable codec. The demo uses an `ApiProblem` record to keep JSON fields transparent without extra Bean Validation/exception abstractions.

### 8.2. Internal errors must be masked at the HTTP edge

Never return:

```json
{"error":"database at 10.0.0.5 refused connection; secret=..."}
```

Return instead:

```json
{
  "type":"about:blank",
  "title":"Internal Server Error",
  "status":500,
  "detail":"Unexpected server error",
  "instance":"/api/items/boom",
  "code":"INTERNAL_ERROR",
  "requestId":"..."
}
```

Log the full exception (after redaction) on the server correlated with `requestId`. Never send stack traces, raw SQL, JWTs, or connection details to clients.

## 9. Boundaries: which errors does onError not cover?

A request can fail **before** or **after** the functional handler:

| Error source | Handled by router-local `onError`? | Things to note |
| --- | --- | --- |
| Bad input in matched handler | Yes | Use typed 400 exception |
| Missing record in handler | Yes | Typed 404 exception |
| Service failure in returned `Mono` | Can be caught in router filter chain | Generic 500, no leaks |
| Router does not match URL | **No** | Global 404 error handling |
| CORS/CSRF/auth fail before router | **No** | Reactive Security/CORS filters |
| `Content-Type`/`Accept` predicate mismatch | May have no matched handler | Test 404/406/415 per policy |
| Malformed JSON decoder error in handler | Depends on where error originates | Global codec handling or typed mapping |
| Exception after body writer flushes data | Cannot reliably change status | Streaming error strategy |
| Client disconnects | Cannot always send an error body | Cancel/log/cleanup |

### 9.1. ErrorWebExceptionHandler

Spring WebFlux defines `ErrorWebExceptionHandler` as the global web exception boundary. Spring Boot auto-configures error handling for WebFlux, and you can customize `ErrorAttributes` or extend `AbstractErrorWebExceptionHandler` when you need application-wide uniform error responses. Reference interface signature:

```java
// Reference signature, not a complete compilable implementation.
Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
```

A real implementation must set HTTP status and headers and write JSON bytes via reactive APIs/codecs **before committing**, respecting `DataBuffer` lifecycles, handler ordering, and Boot's default handlers. Never write a half-baked global error handler that calls `writeWith` on unreleased buffers, causing leaks or double writes.

### 9.2. Errors vs. security policy

401 Unauthorized (unauthenticated) and 403 Forbidden (insufficient permissions) are normally generated by `SecurityWebFilterChain`/reactive exception handlers, not business routers. To emit the same `ApiProblem` schema for security errors, configure `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler` in reactive Spring Security, ensuring you never accidentally return 200/400 instead of 401/403.

### 9.3. Annotation advice is not a universal router filter

`@RestControllerAdvice`/`@ExceptionHandler` is tailored for annotated WebFlux controllers; do not assume it automatically covers all functional router filters, CORS, static resources, security, and unmatched requests. Keep error boundaries clear in your architecture and verify with `WebTestClient`.

### 9.4. Errors after HTTP commit

Once an SSE/NDJSON response has sent headers and initial chunks, HTTP status cannot reliably switch from 200 to 500, nor can a clean Problem JSON object be injected mid-stream. For streams, design an event protocol such as `event:app-error`, connection closure, retry/backoff, resume IDs, and cancellation. Filtering `Mono<ServerResponse>` is not equivalent to filtering the entire body publisher.

## 10. Request IDs without losing the response body

A convenient helper:

```java
static String requestId(ServerRequest request) {
    return (String) request.attributes().computeIfAbsent(
            "demoRequestId",
            ignored -> UUID.randomUUID().toString());
}
```

Inside the response factory, reuse that same value:

```java
String id = requestId(request);
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", id)
        .bodyValue(value);
```

Both successes and errors therefore write the request ID when constructing the response, avoiding any attempt to copy the body into a new response inside `after`.

**Note:** If a URL fails to match the router, the local `requestId` helper never runs, so Boot's global 404 may lack the header. To assign a trace ID to every request—including auth rejections and unmatched routes—generate the ID in a global `WebFilter` or unified observability middleware. Request IDs do not replace bearer tokens or authorization.

## 11. Complete application: Spring Boot 3.5 and Java 17

The demo API provides:
- `GET /api/items` returning 200 JSON list;
- `GET /api/items/{id}` returning 200 or 404;
- `POST /api/items` reading a JSON body and returning 201 + `Location`;
- `DELETE /api/items/{id}` returning 204 or 404;
- `GET /api/items/boom` intentionally throwing a 500 error, for testing only;
- `before` assigning a request ID;
- `filter` rejecting requests with `X-Demo-Block: yes` to demonstrate short-circuiting;
- `onError` mapping domain errors into a unified `ApiProblem`;
- `after` logging the response status object.

### 11.1. Spring Initializr / Maven

Create a Java 17+, Spring Boot **3.5.x** Maven project with the **Spring Reactive Web** dependency via [Spring Initializr](https://start.spring.io/). The project's `pom.xml` includes the fragment:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
```

The Spring Boot parent/BOM generated by Initializr manages Reactor, Netty, Jackson, and Spring Framework versions. Do not add `spring-boot-starter-web` to this demo, because Boot 3.x typically prefers Servlet MVC when both MVC and WebFlux starters are present.

Layout:

```text
src/main/java/com/example/demo/DemoApplication.java
src/test/java/com/example/demo/RouterErrorTest.java
```

### 11.2. Standalone Java source

Put all of the following into `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> routes(ItemHandler handler) {
        return RouterFunctions.route()
                // Place specific route before /{id}.
                .GET("/api/items/boom",
                        req -> Mono.error(
                                new IllegalStateException("internal demo")))
                .GET("/api/items", handler::list)
                .GET("/api/items/{id}", handler::get)
                .POST("/api/items", handler::create)
                .DELETE("/api/items/{id}", handler::delete)

                .before(req -> {
                    ApiHttp.requestId(req);
                    return req;
                })

                // Real permission checks must use Spring Security.
                .filter((req, next) -> {
                    if ("yes".equalsIgnoreCase(
                            req.headers().firstHeader("X-Demo-Block"))) {
                        return ApiHttp.problem(
                                req, HttpStatus.SERVICE_UNAVAILABLE,
                                "DEMO_BLOCKED", "Demo request was blocked");
                    }
                    return next.handle(req);
                })

                .onError(BadInputException.class,
                        (ex, req) -> ApiHttp.problem(
                                req, HttpStatus.BAD_REQUEST,
                                "INVALID_INPUT", ex.getMessage()))
                .onError(ItemMissingException.class,
                        (ex, req) -> ApiHttp.problem(
                                req, HttpStatus.NOT_FOUND,
                                "ITEM_NOT_FOUND", "Item not found"))
                .onError(IllegalStateException.class,
                        (ex, req) -> ApiHttp.problem(
                                req, HttpStatus.INTERNAL_SERVER_ERROR,
                                "INTERNAL_ERROR", "Unexpected server error"))

                .after((req, response) -> {
                    System.out.printf("route=%s status=%d%n",
                            req.path(), response.statusCode().value());
                    return response;
                })
                .build();
    }
}

record Item(long id, String name) {
}

record CreateItem(String name) {
}

record ApiProblem(
        String type,
        String title,
        int status,
        String detail,
        String instance,
        String code,
        String requestId) {
}

class BadInputException extends RuntimeException {
    BadInputException(String message) {
        super(message);
    }
}

class ItemMissingException extends RuntimeException {
}

final class ApiHttp {

    private ApiHttp() {
    }

    static String requestId(ServerRequest req) {
        return (String) req.attributes().computeIfAbsent(
                "demoRequestId",
                key -> UUID.randomUUID().toString());
    }

    static Mono<ServerResponse> ok(ServerRequest req, Object value) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", requestId(req))
                .bodyValue(value);
    }

    static Mono<ServerResponse> created(ServerRequest req, Item value) {
        return ServerResponse.created(
                        URI.create("/api/items/" + value.id()))
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", requestId(req))
                .bodyValue(value);
    }

    static Mono<ServerResponse> noContent(ServerRequest req) {
        return ServerResponse.noContent()
                .header("X-Request-Id", requestId(req))
                .build();
    }

    static Mono<ServerResponse> problem(
            ServerRequest req, HttpStatus status,
            String code, String safeDetail) {

        String id = requestId(req);
        ApiProblem body = new ApiProblem(
                "about:blank",
                status.getReasonPhrase(),
                status.value(),
                safeDetail,
                req.path(),
                code,
                id);

        return ServerResponse.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .header("X-Request-Id", id)
                .bodyValue(body);
    }
}

@Component
class ItemHandler {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, Item> items =
            new ConcurrentHashMap<>();

    Mono<ServerResponse> list(ServerRequest req) {
        int limit = parseLimit(req.queryParam("limit").orElse("20"));

        List<Item> result = items.values().stream()
                .sorted(Comparator.comparingLong(Item::id))
                .limit(limit)
                .toList();

        return ApiHttp.ok(req, result);
    }

    Mono<ServerResponse> get(ServerRequest req) {
        long id = parseId(req.pathVariable("id"));

        return Mono.defer(() -> Mono.justOrEmpty(items.get(id)))
                .switchIfEmpty(Mono.error(new ItemMissingException()))
                .flatMap(item -> ApiHttp.ok(req, item));
    }

    Mono<ServerResponse> create(ServerRequest req) {
        return req.bodyToMono(CreateItem.class)
                .switchIfEmpty(Mono.error(
                        new BadInputException("JSON body required")))
                .flatMap(input -> {
                    if (input.name() == null
                            || input.name().isBlank()
                            || input.name().length() > 80) {
                        return Mono.error(new BadInputException(
                                "Name must contain 1 to 80 characters"));
                    }

                    return Mono.fromSupplier(() -> {
                        long id = nextId.incrementAndGet();
                        Item created =
                                new Item(id, input.name().trim());
                        items.put(id, created);
                        return created;
                    });
                })
                .flatMap(item -> ApiHttp.created(req, item));
    }

    Mono<ServerResponse> delete(ServerRequest req) {
        long id = parseId(req.pathVariable("id"));

        return Mono.fromSupplier(() -> items.remove(id) != null)
                .flatMap(deleted -> deleted
                        ? ApiHttp.noContent(req)
                        : Mono.error(new ItemMissingException()));
    }

    private static long parseId(String raw) {
        try {
            long id = Long.parseLong(raw);
            if (id < 1) {
                throw new BadInputException("ID must be positive");
            }
            return id;
        } catch (NumberFormatException ex) {
            throw new BadInputException("ID must be numeric");
        }
    }

    private static int parseLimit(String raw) {
        try {
            int value = Integer.parseInt(raw);
            if (value < 1 || value > 100) {
                throw new BadInputException("Limit must be 1 to 100");
            }
            return value;
        } catch (NumberFormatException ex) {
            throw new BadInputException("Limit must be numeric");
        }
    }
}
```

### 11.3. Explaining runnability and limitations

- Java 17 supports records. The file has one public class `DemoApplication`; the other classes/records in the same package are package-private.
- `@SpringBootApplication` scans `@Component ItemHandler` and the `RouterFunction<ServerResponse>` bean.
- All functional endpoint imports come from `web.reactive.function.server`; WebMvc.fn lacks the same reactive return signatures.
- `ApiHttp` produces consistent headers and error bodies; 204 uses `noContent().build()` with no body.
- `before` assigns the ID; `filter` can short-circuit; `onError` maps typed errors; `after` only logs the response object.
- `Mono.defer`/`Mono.fromSupplier` keep operations lazy, yet do not turn blocking JDBC calls into non-blocking I/O. The demo store uses only very short in-memory operations.
- Request bodies use the Jackson codec from the WebFlux starter; manual validation checks the `name` field.
- The demo has no authentication, authorization, CORS, CSRF, database durability, transactions, or rate limiting; **do not deploy it publicly**.
- `GET /api/items/boom` is a simulated server error endpoint that must be removed before production.
- `X-Demo-Block` is a client test switch, not a production security or maintenance mechanism.

### 11.4. Running the project

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / CMD
mvnw.cmd spring-boot:run
```

If `server.port` is not set, the server normally runs on `http://localhost:8080`.

### 11.5. Successful GET list

```bash
curl -i 'http://localhost:8080/api/items?limit=10'
```

When the store is empty:
- HTTP 200;
- `Content-Type: application/json`;
- `X-Request-Id` contains the request UUID;
- body `[]`.

### 11.6. POST creating an item

```bash
curl -i -X POST 'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  --data-binary '{"name":"Spring WebFlux"}'
```

On a freshly started project, the first POST typically creates ID 1:

```http
HTTP/1.1 201 Created
Location: /api/items/1
Content-Type: application/json
X-Request-Id: ...

{"id":1,"name":"Spring WebFlux"}
```

The request ID header, header ordering, and JSON whitespace are not fixed. Across multiple runs, IDs increment; never hardcode IDs in tests.

### 11.7. GET non-existent item

```bash
curl -i 'http://localhost:8080/api/items/999999'
```

Expected 404, `Content-Type: application/problem+json`, and JSON including:

```json
{
  "type":"about:blank",
  "title":"Not Found",
  "status":404,
  "detail":"Item not found",
  "instance":"/api/items/999999",
  "code":"ITEM_NOT_FOUND",
  "requestId":"..."
}
```

The `X-Request-Id` header and the `requestId` field in the same response must match.

### 11.8. Invalid ID/limit

```bash
curl -i 'http://localhost:8080/api/items/abc'
curl -i 'http://localhost:8080/api/items?limit=0'
curl -i 'http://localhost:8080/api/items?limit=abc'
```

Expected HTTP 400 Problem Details with `code=INVALID_INPUT`; `detail` is generated safely by domain exceptions: "ID must be numeric", "Limit must be 1 to 100", "Limit must be numeric".

### 11.9. Blocked by filter

```bash
curl -i 'http://localhost:8080/api/items' \
  -H 'X-Demo-Block: yes'
```

Expected HTTP 503, Problem body with `code=DEMO_BLOCKED` and `X-Request-Id`. The filter returns early **without calling `next.handle(req)`**, so the `list` handler never executes.

### 11.10. Safe 500 error

```bash
curl -i 'http://localhost:8080/api/items/boom'
```

Expected HTTP 500 with `code=INTERNAL_ERROR`, `detail=Unexpected server error`. The error body must not expose the raw `"internal demo"` message. In real systems, redacted internal logs preserve stack traces, diagnostic metadata, and `requestId`.

### 11.11. Invalid body and decoder errors

```bash
curl -i -X POST 'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  --data-binary '{"name":" "}'
```

Expected 400 with `code=INVALID_INPUT`. However, for malformed JSON like `{"name":` or `Content-Type: text/plain`, errors can originate from the HTTP decoder or route matching; **do not** claim local `onError` always produces the same schema without global error handling.

### 11.12. DELETE and 204

```bash
curl -i -X DELETE 'http://localhost:8080/api/items/1'
```

If item ID=1 exists: status 204, no body, `X-Request-Id` header. Subsequent call: HTTP 404 Problem Details. In automated tests, obtain the ID from the POST `Location` header rather than assuming a freshly booted store.

### 11.13. PowerShell

```powershell
curl.exe -i "http://localhost:8080/api/items"
curl.exe -i "http://localhost:8080/api/items?limit=0"
curl.exe -i "http://localhost:8080/api/items/boom"
curl.exe -i -H "X-Demo-Block: yes" "http://localhost:8080/api/items"
```

For POST JSON on PowerShell, create a UTF-8 `request.json` file containing `{"name":"Spring WebFlux"}` and run `curl.exe -i -X POST ... -H "Content-Type: application/json" --data-binary "@request.json"`; this avoids quote-escaping differences across shells.

## 12. WebTestClient testing

With Boot 3.5, add the test dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

### 12.1. Complete test file

Create `src/test/java/com/example/demo/RouterErrorTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class RouterErrorTest {

    @Autowired
    WebTestClient client;

    @Test
    void listHasRequestIdAndJsonBody() {
        client.get().uri("/api/items")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().exists("X-Request-Id")
                .expectBody()
                .json("[]");
    }

    @Test
    void invalidLimitHasStandardProblemBody() {
        client.get().uri("/api/items?limit=0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader().contentType(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectHeader().exists("X-Request-Id")
                .expectBody()
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.code").isEqualTo("INVALID_INPUT");
    }

    @Test
    void missingItemReturnsProblem404() {
        client.get().uri("/api/items/999999")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
    }

    @Test
    void filterCanShortCircuitWith503() {
        client.get().uri("/api/items")
                .header("X-Demo-Block", "yes")
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectBody()
                .jsonPath("$.code").isEqualTo("DEMO_BLOCKED");
    }

    @Test
    void internalErrorUsesSafeMessage() {
        client.get().uri("/api/items/boom")
                .exchange()
                .expectStatus().is5xxServerError()
                .expectBody()
                .jsonPath("$.status").isEqualTo(500)
                .jsonPath("$.code").isEqualTo("INTERNAL_ERROR")
                .jsonPath("$.detail")
                .isEqualTo("Unexpected server error");
    }

    @Test
    void postCreatesResourceWithLocation() {
        client.post().uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":\"demo item\"}")
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectHeader().exists("X-Request-Id")
                .expectBody()
                .jsonPath("$.name").isEqualTo("demo item");
    }

    @Test
    void blankNameIsRejected() {
        client.post().uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":\"  \"}")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_INPUT");
    }
}
```

These tests only verify **router-matched** paths and declared logic. They do not guarantee the same JSON format for `/not-a-route`, CORS preflight, Spring Security 401/403, unsupported media types, or malformed JSON if those errors come from other layers. Add integration tests when configuring a global error policy.

### 12.2. Comparing header and JSON requestId

You can capture `EntityExchangeResult<byte[]> result = ...expectBody().returnResult()`, parse `requestId` with Jackson `ObjectMapper`, and assert it equals `result.getResponseHeaders().getFirst("X-Request-Id")`. This is an additional **test extension** to write yourself, not a method already present in the file above. Never hardcode UUIDs or reuse IDs from prior requests.

### 12.3. Router-only vs. HTTP integration tests

`WebTestClient.bindToRouterFunction(router).build()` lets you test routing and filters quickly without opening a socket. However, it does not prove Netty, proxy, security chain, or global error behavior. Public APIs need both Boot HTTP integration tests and end-to-end tests through your gateway/ingress.

### 12.4. Running

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

The examples here are written against Spring Boot 3.5.x / Spring Framework 6.2.x; authoring a guide is not equivalent to actually starting the server and executing tests in a Maven project.

## 13. Production: designing layered error boundaries

A real-world architecture can be structured as:

```text
Incoming HTTP request
       |
Global WebFilter: request ID + observation + CORS
       |
SecurityWebFilterChain: 401/403
       |
Routing
  |          \
  |           \ no route -> global error 404
  v
Router-local filters + typed domain onError
       |
Reactive handlers and services
       |
Codec/body write
       |
Client/network
       |
Late write error -> logs/cancel/stream event protocol
```

### 13.1. One contract, multiple producers

A single error model/problem factory can be shared across producers:
- Router `onError` for domain failures;
- Global `ErrorWebExceptionHandler` for fallbacks, unmatched routes, and codecs;
- Security entry point and access-denied handler for 401/403;
- Gateway/proxy contracts if infrastructure generates 413/429/502/503 responses.

**Avoid circular dependencies:** a global handler may not have a functional `ServerRequest` when no route matched; therefore, the factory should accept a context-neutral request path, request ID, and status instead of forcing every error through `RouterFunction`.

### 13.2. Ordering and double writes

When registering a custom global `ErrorWebExceptionHandler`, define its priority relative to Boot's default, check `response.isCommitted()`, and write at most once. If a filter writes an error and also returns `Mono.error`, a downstream handler trying to write again can corrupt the response. Once an error response is created, the terminal path should complete cleanly.

### 13.3. Problem title/detail i18n

Machine-readable error codes should stay stable; localized client messages should be separated or translated by policy. Never use raw `detail` strings as identifiers. Bound lengths and echoed paths/parameters in error bodies to prevent log injection, reflected content, and PII exposure.

### 13.4. Security and backpressure

- Input DTOs must validate allowed fields, string lengths, batch sizes, and request body limits.
- WebFlux codec buffering can be configured via `spring.codec.max-in-memory-size` in Boot 3.5 for certain scenarios; it is **not** a limit on all streaming requests.
- Never call `block()` or run blocking JDBC directly on the event loop.
- Large `Flux` sources need limits and backpressure; avoid unbounded `collectList()`.
- Partially streamed bodies must signal errors via application-level semantics or connection closure.
- Never use custom error filters as a substitute for authorization checks.

## 14. Common mistakes table

| Symptom | Cause | Remediation |
| --- | --- | --- |
| Router filter does not run on unknown URLs | No route matched | Global `WebFilter`/`ErrorWebExceptionHandler` |
| 401/403 lacks the same Problem schema | Security rejects before router | Custom reactive entry point/denied handler |
| `onError` fails to compile after copying MVC code | WebMvc.fn returns synchronous response | WebFlux.fn returns `Mono<ServerResponse>` |
| Filter blocks request yet handler still runs | Still calling `next.handle(req)` | Return early from the filter |
| Filter does not protect another router module | Scoped to a single `RouterFunction` | Compose routers properly or use global `WebFilter` |
| `after` logs before SSE finishes | Sees only response descriptor creation | HTTP network instrumentation |
| Modifying headers drops the body | Built new response via `from(...).build()` | Set headers in response factory |
| 400 returned for a 500 DB failure | Catch-all too broad or wrong status mapping | Typed exceptions, generic 500 fallback |
| Stack trace returned in `detail` | Copied raw exception message | Client-safe details and internal logs |
| `Mono.empty()` does not produce 404 | Absence not mapped | `switchIfEmpty` with typed missing exception |
| Malformed JSON lacks expected schema | Codec error differs from domain error | Global codec/error policy |
| Wrong `Content-Type` returns 404 | Predicate fails to match route | Test 404/415/406 contracts |
| Missing `X-Request-Id` on global 404 | Request ID generated only in local `before` | Global trace `WebFilter` |
| 204 body is non-empty | Attached response DTO | `noContent().build()` |
| `X-Demo-Block` abused | Client-controlled test header | Remove in production |
| Error after first SSE event does not become JSON | Response already committed | Stream error/cancel/reconnect protocol |
| Router calls `subscribe()` manually | Work detached from HTTP lifecycle | Return `Mono`/`Flux` |
| MDC/tenant trace lost across threads | Reactive context differs from `ThreadLocal` | Context propagation |
| Tests depend on hardcoded UUIDs/IDs | Generated per request | Assert patterns/`Location` instead of fixed IDs |

## 15. Completion checklist

1. [ ] Correct WebFlux stack with imports from `web.reactive.function.server`.
2. [ ] Router functions ordered properly, static paths before variable paths.
3. [ ] Nested/builder filter scopes reviewed whenever adding endpoints.
4. [ ] `before` handles fast metadata only, never consuming bodies or blocking I/O.
5. [ ] `filter` returns `Mono` and short-circuits without calling `next` when rejecting.
6. [ ] `after` logs response metadata only, without assuming network completion.
7. [ ] `onError` handles typed domain errors; unknown 500s never leak internals.
8. [ ] Statuses/bodies/headers follow 200/201/204/400/404/500/503 semantics.
9. [ ] `application/problem+json` error bodies match RFC 9457 with stable `code`s.
10. [ ] Request IDs in headers and bodies match and contain no sensitive data.
11. [ ] Global error policy covers unknown routes, codecs, and security failures.
12. [ ] `SecurityWebFilterChain`, CORS/CSRF, tenant ACLs, and rate limits are explicit.
13. [ ] No `Mono.block`, `Thread.sleep`, or blocking JDBC on the event loop.
14. [ ] Post-commit streaming errors have a protocol, cleanup/cancel, and retry policy.
15. [ ] `WebTestClient` covers success, bad input, missing item, 500, filter 503, and header correlation.
16. [ ] Dedicated tests cover global 404/401/403/415, malformed JSON, and proxy CORS.
17. [ ] Remove test-only `/api/items/boom` and `X-Demo-Block` before production.
18. [ ] When upgrading to Spring Framework 7/Boot 4, verify new starter/test imports before reusing code.

## 16. Review questions

**1. How does a WebFlux.fn filter differ from a `WebFilter`?** Router filters apply only to matched functional routes within their scope; `WebFilter` sits in the application-wide HTTP handler chain.

**2. What does `before` return?** `ServerRequest`; it does not return `Mono<ServerRequest>` in the 6.2 Java builder API.

**3. What does `filter` return?** `Mono<ServerResponse>`, either calling `next.handle(req)` or returning an early response.

**4. Does `after` mean the entire response body has been sent?** No; it operates on the `ServerResponse` object, while the body publisher may stream afterward.

**5. What does `onError` in WebFlux.fn return?** The response provider returns `Mono<ServerResponse>`, unlike synchronous WebMvc.fn.

**6. Should every `Exception` be mapped to 400?** No; classify client, domain, server, and security errors separately and preserve appropriate statuses.

**7. Why does an unmatched URL lack a local request ID?** Because local `before`/filters never ran; assign request IDs in a global `WebFilter` to cover all routes.

**8. Does HTTP 204 carry a JSON body indicating success?** No; 204 responses have no body.

**9. Can an error after sending an SSE event change the HTTP status to 500?** Not reliably, because headers are already committed; use a stream protocol or close the connection.

**10. Is `X-Request-Id` authentication?** No. It is used for correlation and debugging support.

## 17. Official documentation

- [Spring Framework 6.2 — Functional WebFlux Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): `before`/`after`/`filter`, nested scopes, `RouterFunction`/`HandlerFunction`.
- [Spring Framework 6.2 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html): `filter`/`onError`/`before`/`after` methods.
- [Spring Framework 6.2 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): mutable attributes, headers, `bodyToMono`.
- [Spring Framework 6.2 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): status, headers, `bodyValue`, `body`.
- [Spring Framework 6.2 — Reactive Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): `ProblemDetail`/RFC 9457, `ErrorResponse`, annotation-handling boundaries.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): starter, error configuration, routing.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): reactive `SecurityWebFilterChain`, 401/403.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): `CorsWebFilter`.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): `Mono` error signaling, `doFinally`, cancellation.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standardized error JSON body and extension fields.

**Conclusion:** `before` enriches request metadata, `filter` wraps or short-circuits handlers, `after` observes the response object, and `onError` translates domain exceptions into `Mono<ServerResponse>`. Use a response factory for consistent HTTP statuses, headers, and Problem JSON, while remembering that router-local filters **do not replace** global error or security handling. Errors occurring after a body starts streaming require a dedicated streaming strategy.
