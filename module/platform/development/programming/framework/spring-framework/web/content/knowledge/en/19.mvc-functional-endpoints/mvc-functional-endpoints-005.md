# HandlerFilterFunction, Error Handling, and Organizing Functional Routes in Spring MVC

## 1. The Problem: Avoiding Duplicate Logic When an API Has Many Functional Routes

Spring MVC does not require every HTTP endpoint to be a method annotated with `@GetMapping` or `@PostMapping`. Alongside annotated controllers, Spring supports **WebMvc.fn**, where routes and handlers are functions with clear contracts:

- `RouterFunction<ServerResponse>` selects a handler matching the request.
- `HandlerFunction<ServerResponse>` receives a `ServerRequest` and returns a `ServerResponse`.
- `HandlerFilterFunction<ServerResponse, ServerResponse>` wraps the handler invocation to address shared concerns such as logging, timing, input gating, or business-level short-circuiting.
- `RouterFunctions.Builder` lets you group routes by prefix/path/predicate, attach `before`/`after`/`filter`, and declare scoped `onError` handlers.

As an API grows, three issues typically emerge:

1. Ten routes all need logging or header checks, duplicating code across individual handlers.
2. A business exception must map to the same HTTP status/body, yet every handler has its own `try/catch`.
3. Routes for `/api/v1/notes`, `/api/v1/orders`, and `/admin/**` are declared out of order, causing route shadowing or filters leaking onto unrelated endpoints.

The solution is not putting everything into one giant filter. You need to understand **router function scopes**, where each filter sits, and where exceptions are handled.

**Baseline:** Java 17+, Spring Framework **6.2.x** / Spring Boot **3.5.x**, Spring MVC on the Servlet stack. All imports for the functional API belong to **`org.springframework.web.servlet.function`**; **do not** use WebFlux's `org.springframework.web.reactive.function.server`. The sample code uses an in-memory repository to focus on route organization; it omits a production database and authentication.

## 2. WebMvc.fn Processing Flow in DispatcherServlet

Functional MVC does not create a separate HTTP server outside Spring MVC. It runs inside the Servlet/`DispatcherServlet` infrastructure:

```text
HTTP Request
     |
     v
Servlet FilterChain
     |
     v
DispatcherServlet
     |
     v
HandlerMappings
  RouterFunctionMapping -> find matching RouterFunction
     |
     v
HandlerFunctionAdapter
     |
     v
HandlerFilterFunction(s)
  pre logic -> next.handle(request) -> post logic
     |
     v
HandlerFunction(ServerRequest) -> ServerResponse
     |
     v
HttpMessageConverter / Servlet response writer
     |
     v
HTTP status + headers + body
```

If a `RouterFunction` does not match, routing returns **`Optional.empty()`** and DispatcherServlet can check other mappings. Only when a handler is selected do the filters attached to that router get a chance to execute.

In WebMvc.fn:

```java
@FunctionalInterface
interface HandlerFunction<T extends ServerResponse> {
    T handle(ServerRequest request) throws Exception;
}
```

This is the **conceptual signature** of the Spring API; you do not declare this interface in your project. `ServerRequest` and `ServerResponse` follow an immutable-style contract; you return a response object created by a builder rather than writing raw Servlet output directly as in low-level code.

Short example:

```java
RouterFunction<ServerResponse> router =
        RouterFunctions.route()
                .GET("/hello", request ->
                        ServerResponse.ok()
                                .contentType(MediaType.TEXT_PLAIN)
                                .body("Hello WebMvc.fn"))
                .build();
```

This is a **fragment**, requiring WebMvc.fn and `MediaType` imports and registration as a `@Bean` if DispatcherServlet is to discover it. It lacks filters/error handling yet serves as a starting point.

## 3. What Arguments Does `HandlerFilterFunction` Actually Receive?

In Spring MVC:

```java
import org.springframework.web.servlet.function.HandlerFilterFunction;
import org.springframework.web.servlet.function.HandlerFunction;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;
```

Main method contract:

```java
R filter(ServerRequest request, HandlerFunction<T> next)
        throws Exception;
```

Where:

- `request` is the functional request for the matched route.
- `next` represents **the next handler or filter** in the chain.
- `next.handle(request)` proceeds with executing the next stage.
- The returned `ServerResponse` is the final response for handling the route after surrounding filters.
- A filter can **skip** calling next and return a response itself, e.g., rejecting requests missing a required header.
- A filter can use `try/finally` to clean up context or measure duration even when downstream throws an exception.
- A filter can catch **specific exceptions**, return an alternate response, or let exceptions propagate to `onError`/MVC exception resolvers.

### 3.1. Basic pattern: before → next → after

```java
HandlerFilterFunction<ServerResponse, ServerResponse> timer =
        (request, next) -> {
            long started = System.nanoTime();
            try {
                return next.handle(request);
            } finally {
                long elapsedNanos = System.nanoTime() - started;
                // Record normalized metric.
            }
        };
```

This is a **fragment**, not a runnable class; no metrics sink is defined. `finally` is important so cleanup/recording still runs when downstream throws an exception.

Example illustrating a filter that can return an early error:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> requireDemoHeader =
        (request, next) -> {
            String value = request.headers()
                    .firstHeader("X-Demo-Client");
            if (!"learning".equals(value)) {
                return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(new ApiError(
                                "DEMO_HEADER_REQUIRED",
                                "Missing demo client header"));
            }
            return next.handle(request);
        };
```

The fragment assumes record `ApiError` exists. The `X-Demo-Client` header **is strictly a simulated rule for this lesson** and must never be used as authentication. Any client can fabricate headers freely. In real APIs, authentication/authorization are handled by **Spring Security `SecurityFilterChain`**, paired with resource-level permissions.

### 3.2. A filter is neither a Servlet Filter nor an MVC HandlerInterceptor

| Layer | API | Timing / Scope |
| --- | --- | --- |
| **Servlet container** | `jakarta.servlet.Filter` | Before/around Servlet, with URL mapping + dispatcher types |
| **Spring Security** | `FilterChainProxy` / `SecurityFilterChain` | HTTP request protection, authentication, authorization, CSRF |
| **Spring MVC functional route** | `HandlerFilterFunction` | After a router function matches; scoped only to the attached router |
| **Spring MVC annotated controller** | `HandlerInterceptor` | On MVC-selected handlers via interceptor registrations |
| **Exception infrastructure** | `HandlerExceptionResolver`, `@ControllerAdvice` | Has distinct error-handling contracts and precedence rules |

Because a handler filter lives **inside functional routing**, it does not automatically run on:

- Annotated `@RestController` endpoints outside that router function.
- Static resources served by another resource handler.
- Other Servlets or the filter chain before `DispatcherServlet`.
- Requests that **do not match** any route in the router carrying the filter.
- Requests rejected by Spring Security **before** reaching the handler.

**Do not use `HandlerFilterFunction` instead of Spring Security** on mandatory application-wide security boundaries.

## 4. `RouterFunctions.route()`: Builder and Route Order

Building a router with HTTP routes:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/v1/notes", handler::list)
                .GET("/api/v1/notes/{id}", handler::get)
                .POST("/api/v1/notes", handler::create)
                .build();
```

This is a fragment assuming `handler` exposes methods matching `ServerRequest -> ServerResponse`.

### 4.1. The first matching route wins

**Important:** WebMvc.fn evaluates `RouterFunction` **in declaration order**. If a general route matches first, a specific route declared later may never be selected:

```java
// Error-prone: the variable route can match "stats" first.
RouterFunctions.route()
        .GET("/api/v1/notes/{id}", handler::get)
        .GET("/api/v1/notes/stats", handler::stats)
        .build();
```

In the example above, `GET /api/v1/notes/stats` can enter `get` with `id="stats"` and fail when parsing the ID. Declare static routes first:

```java
RouterFunctions.route()
        .GET("/api/v1/notes/stats", handler::stats)
        .GET("/api/v1/notes/{id}", handler::get)
        .build();
```

This differs from the annotated controller model, where the framework has an algorithm to pick the most specific mapping. **Do not rely on a "Spring will pick static paths first" heuristic in WebMvc.fn**. With overlapping predicates such as `accept`, `contentType`, or nested wildcards, the first-matching-route rule must still be verified with tests.

### 4.2. Route predicates and HTTP media types

`RequestPredicates` supports composite conditions:

```java
import static org.springframework.web.servlet.function.RequestPredicates.accept;
import static org.springframework.web.servlet.function.RequestPredicates.contentType;
```

Example:

```java
RouterFunctions.route()
        .GET("/notes", accept(MediaType.APPLICATION_JSON),
                handler::list)
        .POST("/notes", contentType(MediaType.APPLICATION_JSON),
                handler::create)
        .build();
```

This is a fragment. `accept` checks what the client can receive in the response; `contentType` checks the request body format. A request failing a predicate can fall through to other routes or receive 404/405/406/415 depending on mappings/resolvers; **do not** assume a wrong Content-Type returns 415 under every configuration.

If the API contract explicitly mandates JSON-only POSTs, use the predicate and add an unsupported-media-type error contract via exception handling or infrastructure. The handler must still validate deserialized contents.

## 5. Organizing Routes with `path` and `nest`

Instead of repeating `/api/v1` on every route, group by prefix:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/v1", api -> api
                        .GET("/notes/stats", handler::stats)
                        .GET("/notes/{id}", handler::get)
                        .GET("/notes", handler::list)
                        .POST("/notes", handler::create))
                .build();
```

`path("/api/v1", consumer)` creates a nested builder. Inner route suffixes are combined according to `RequestPredicate` semantics. Reviewing is easier when the entire API version sits in one group.

### 5.1. Nesting by a predicate other than path

For example, multiple GET routes intended only for JSON-accepting clients:

```java
RouterFunctions.route()
        .path("/api/v1/notes", notes -> notes
                .nest(
                    RequestPredicates.accept(
                            MediaType.APPLICATION_JSON),
                    json -> json
                            .GET("/stats", handler::stats)
                            .GET("/{id}", handler::get)))
        .build();
```

Here, `nest` groups routes sharing a common predicate. It does **not** automatically enforce JSON payload validation or add Security. `accept` is a match condition on the Accept header; to constrain POST JSON bodies, use `contentType` accordingly.

### 5.2. Group-scoped filters

Consider two routes:

```java
RouterFunctions.route()
        .GET("/health", healthHandler)
        .path("/api/v1", api -> api
                .GET("/notes", notesHandler)
                .filter(notesFilter))
        .build();
```

`notesFilter` belongs to the nested `/api/v1` builder and does **not** apply to `GET /health`. If `.filter(notesFilter)` is instead attached to the outer builder after `path(...)`, the filter can apply to **both /health and the API group**.

Spring documentation emphasizes that filters added to nested routes do not run on top-level routes. This enables clean separation of responsibilities:

- Shared API filter for `/api/v1/**`.
- Narrow filter for `/api/v1/admin/**`.
- No auth/business-header requirement on `/health`.
- Outer builder filter only when it truly applies to all constructed routes.

Never assume any filter "automatically applies app-wide." Check the exact builder/RouterFunction to which you attach the filter.

## 6. Three Ways to Add Shared Behavior: `before`, `after`, `filter`

### 6.1. `before(Function<ServerRequest,ServerRequest>)`

Used to process/transform the functional request before the handler:

```java
.before(request -> {
    audit.info("route={} method={}",
            request.path(), request.method());
    return request;
})
```

The fragment assumes an `audit` logger exists. Log controlled paths/route templates when possible, avoiding raw queries or tokens.

You can use `ServerRequest.from(request)` to build an immutable request wrapper:

```java
.before(request -> ServerRequest.from(request)
        .header("X-Lesson-Scope", "notes")
        .build())
```

This illustrates request transformation. **Do not treat a header injected onto the functional request as authentication proof.** For trusted data, use services/validated contexts and proper authorization policies.

### 6.2. `after(BiFunction<ServerRequest,ServerResponse,ServerResponse>)`

After the handler returns `ServerResponse`, process the response object:

```java
.after((request, response) -> {
    audit.info("mvc_fn_status={}",
            response.statusCode().value());
    return response;
})
```

This form helps record metrics/statuses for successful responses or early filter returns. **Do not treat `after` as a `finally` block for all exceptions:** if downstream throws before producing a `ServerResponse`, error handling or `filter` with `try/finally` is the right place. When returning a streaming response, **actual body** writing can happen after `after` returns; timing recorded here does not necessarily include sending all bytes to the client.

### 6.3. `filter(HandlerFilterFunction<...>)`

Use when you need explicit control to invoke or skip `next.handle`:

```java
.filter((request, next) -> {
    String gate = request.headers()
            .firstHeader("X-Demo-Client");

    if (!"learning".equals(gate)) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of(
                        "code", "DEMO_HEADER_REQUIRED"));
    }

    return next.handle(request);
})
```

`before` and `after` suit simple request/response transformations; `filter` is more flexible when you need to **short-circuit**, coordinate before/after inside `try/finally`, or catch a specific exception type.

### 6.4. Using static adapters for existing filters

`HandlerFilterFunction` provides:

- `ofRequestProcessor(Function<ServerRequest,ServerRequest>)`.
- `ofResponseProcessor(BiFunction<ServerRequest,T,R>)`.
- `ofErrorHandler(Predicate<Throwable>, BiFunction<Throwable,ServerRequest,T>)`.
- `andThen(...)` to compose type-compatible filters.
- `apply(handler)` to apply a filter to a handler.

Fragment example:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> passThrough =
        HandlerFilterFunction.ofRequestProcessor(
                request -> request);

HandlerFilterFunction<ServerResponse, ServerResponse> trace =
        passThrough.andThen((request, next) -> {
            long started = System.nanoTime();
            try {
                return next.handle(request);
            } finally {
                long nanos = System.nanoTime() - started;
                // Record bounded metric only.
            }
        });
```

`andThen` composes in the declared order per the `HandlerFilterFunction` contract; when multiple nested/outer builders exist, **do not guess the order purely from intuition about decorators**. Write an integration test recording event order if business logic depends on it.

## 7. Error Handling with `RouterFunctions.Builder.onError`

A handler can throw an exception because a resource does not exist, input is invalid, or the server fails. In WebMvc.fn, the builder supports error mapping directly in the router:

```java
.onError(NoteNotFoundException.class, (error, request) ->
        ServerResponse.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ApiError(
                        "NOTE_NOT_FOUND", "Note does not exist")))
```

This is a builder fragment assuming `NoteNotFoundException`/`ApiError` are defined. `onError` takes:

1. A `Class<? extends Throwable>`, or
2. A `Predicate<Throwable>` deciding which errors to handle,

and a function producing a `ServerResponse` from the `Throwable` and `ServerRequest`.

### 7.1. Class-based mapping

```java
.onError(InvalidNoteException.class,
        (error, request) ->
                ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError(
                            "NOTE_INVALID", "Invalid note input")))
.onError(NoteNotFoundException.class,
        (error, request) ->
                ServerResponse.status(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError(
                            "NOTE_NOT_FOUND", "Note not found")))
```

Advantage: typed business exceptions, less reliance on parsing messages; easy to test error contracts. Use **stable application error codes** and safe client messages, never returning raw SQL, stack traces, or tokens.

### 7.2. Predicate-based mapping

```java
.onError(error ->
        error instanceof IllegalArgumentException,
        (error, request) ->
                ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError(
                            "INVALID_ARGUMENT",
                            "Invalid request argument")))
```

Use a predicate when matching a group of errors or specific conditions, but avoid `error -> true` for everything and turning **internal bugs into HTTP 400**. A catch-all can mask programming errors and cause monitoring to miss 500s.

### 7.3. `ofErrorHandler(...)` without builder.onError

From the filter API:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> notFound =
        HandlerFilterFunction.ofErrorHandler(
            error -> error instanceof NoteNotFoundException,
            (error, request) ->
                ServerResponse.status(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError(
                        "NOTE_NOT_FOUND", "Note not found")));
```

This filter can be added via `RouterFunction.filter(...)` or builder `.filter(notFound)`. Choose **one structured error-mapping strategy**, avoiding handling the same error across multiple layers with unclear precedence.

### 7.4. Which exceptions fall under `onError`?

`onError` is a filter wrapping **handler functions** within the router's scope. It fits errors thrown **while a handler/filter processes a request after the router matches**.

It is not a global exception handler for everything:

- Errors occurring **before route matching** (Servlet filters, Security, request parsing/dispatch prior to the functional handler) may fall outside scope.
- Errors from annotated controllers in other routers do not necessarily flow through the functional builder's `onError`.
- Errors while **serializing/writing the HTTP body after the response is committed** may not be convertible into a new JSON error, depending on the message converter/container.
- An **unmatched** router has no exception for `onError` to catch; it typically becomes a 404 or another mapping/exception handled by MVC.
- An invalid JSON body can raise a conversion exception; unless matched by custom types/predicates, it passes through MVC exception infrastructure.
- Once part of a streaming response has been sent, you cannot promise changing 200 to 500.

`@RestControllerAdvice` / `@ExceptionHandler` / `HandlerExceptionResolver` are separate mechanisms. For functional endpoints, **the clearest approach for local domain errors is usually `onError`**; global MVC exception resolvers may participate depending on exception/adapter flow and Spring configuration. Do not assume annotated controller advice automatically replaces all functional error mapping.

### 7.5. Do not leak sensitive details in errors

Avoid:

```java
.onError(Throwable.class, (error, request) ->
        ServerResponse.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("debug", error.toString())))
```

This is an **anti-pattern**: exception messages can contain DB paths, SQL, request bodies, credentials, or private implementation details. Return a standard error instead:

```json
{"code":"INTERNAL_ERROR","message":"Unexpected server error"}
```

Internal logs still need classification/limits for investigation. Never log entire `Authorization` headers, Cookies, raw JSON bodies, or untrusted path values.

## 8. Code Structure When an Application Has Many Functional Route Groups

A scalable structure:

```text
src/main/java/demo/webfn/
├─ WebFnApplication.java
├─ routes/
│  ├─ PublicRoutes.java
│  ├─ NotesRoutes.java
│  └─ OrdersRoutes.java
├─ handlers/
│  ├─ NotesHandler.java
│  └─ OrdersHandler.java
├─ service/
│  ├─ NoteService.java
│  └─ OrderService.java
├─ model/
│  └─ ApiError.java
└─ filters/
   ├─ RequestMetricsFilter.java
   └─ CorrelationIdFilter.java
```

This is an **illustrative structure**; not all these files need to exist in the single-file demo in section 10. Division of responsibilities:

- **Routes** declare only HTTP paths/methods/predicates, attach filters, and set onError.
- **Handlers** decode `ServerRequest`, invoke services, and build `ServerResponse`.
- **Services** hold business logic, persistence, transactions, and validations.
- **Filters** handle only shared concerns within a clear scope.
- **Error mapping** turns exception types into HTTP contracts; avoid building responses from raw exception messages.
- **Spring Security** handles mandatory authorization and CSRF/CORS by architecture rather than offloading them to the route builder.

### 8.1. Composing router functions

Valid ways:

```java
RouterFunction<ServerResponse> combined =
        notesRouter.and(ordersRouter);
```

Or:

```java
RouterFunction<ServerResponse> combined =
        RouterFunctions.route()
                .add(notesRouter)
                .add(ordersRouter)
                .build();
```

These are **fragments**, assuming both routers exist. Ordered composition means whichever router matches first wins. If URL patterns overlap, composition order is part of the contract that must be tested.

### 8.2. Multiple `RouterFunction` beans and @Order

In Boot MVC, a `RouterFunction<ServerResponse>` declared as `@Bean` is discovered by `RouterFunctionMapping`. When multiple router function beans exist, the framework orders/combines them. If routing priority matters, configure explicit ordering on the beans/routers, check bean ordering/`@Order` for your version, and avoid unintended overlapping routes across routers.

Example **fragment**:

```java
@Bean
@Order(10)
RouterFunction<ServerResponse> publicRouter() {
    return RouterFunctions.route()
            .GET("/public/status",
                request -> ServerResponse.ok().body("ready"))
            .build();
}
```

When the same request could match multiple router beans, test precedence directly instead of assuming Spring selects the "more specific" one like annotated controllers. Within a single domain group, merging into **one router bean** reduces ambiguity risks and makes order easier to control.

### 8.3. Prefix/version organization for API contracts

Group `/api/v1`, `/api/v2` separately to:

- Avoid accidentally falling through to another version's handler.
- Have independent error envelopes/route filters when needed.
- Allow migrating each version with independent tests.
- Avoid accidentally applying a filter meant for `/api/v2` onto `/health` or `/api/v1`.

If versions are negotiated via headers/media types instead of paths, use the corresponding contract predicates; do not assume a `/v2` prefix alone solves schema changes and version compatibility.

## 9. Notes on HandlerFunction and ServerResponse

### 9.1. Reading path variables, queries, and bodies

```java
String id = request.pathVariable("id");

String search = request.param("q").orElse("");

NewNote input = request.body(NewNote.class);
```

This is a fragment inside a handler with `ServerRequest request`. `pathVariable` is valid only after a route with `{id}` matches; `param` returns `Optional<String>`. `body(Class)` uses message converters to read the request body according to media type/content negotiation.

Do not trust data merely because it became a Java object: domain validation, length limits, and authorization are still needed. `NumberFormatException` while parsing `id` should map to an appropriate 400; a non-existent resource after parsing should map to 404.

### 9.2. ServerResponse types

```java
ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Note(42, "Hello"));

ServerResponse.status(HttpStatus.NOT_FOUND)
        .contentType(MediaType.APPLICATION_JSON)
        .body(new ApiError("NOTE_NOT_FOUND", "Note not found"));

ServerResponse.created(URI.create("/api/v1/notes/42"))
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Note(42, "Hello"));

ServerResponse.noContent().build();
```

These fragments illustrate the response builder API. `ServerResponse.created(uri)` produces 201 + Location; a root-relative URI assumes the app is at the context root. For apps behind a proxy/context path, use appropriate URI generation such as `ServletUriComponentsBuilder` or a canonical base.

### 9.3. Do not confuse functional ServerResponse with reactive Mono

In Servlet WebMvc.fn:

```java
HandlerFunction<ServerResponse> hello =
        request -> ServerResponse.ok().body("Hello");
```

Whereas WebFlux.fn typically uses `Mono<ServerResponse>` from Reactor and imports `org.springframework.web.reactive.function.server`. **Do not copy reactive `Mono` signatures** into MVC samples unless intentionally integrating reactive adapters.

## 10. Runnable Application: Spring Boot 3.5 + Java 17

The demo uses a single `RouterFunction` bean to avoid ordering dependencies across multiple beans. Endpoints:

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Returns `OK`; **not blocked by the notes filter** |
| `GET /api/v1/notes` | List of notes in memory |
| `GET /api/v1/notes/stats` | Returns note count; placed **before** `/{id}` |
| `GET /api/v1/notes/{id}` | 200 if found; 404 if missing; 400 if ID is invalid |
| `POST /api/v1/notes` | Accepts JSON, validates title, creates record, returns 201 + Location |
| Notes routes | Require `X-Demo-Client: learning` from the demo filter; returns 400 if missing |

**Important limitation:** the demo header has no security value; clients can send it themselves. There is no real Spring Security/DB/transactions/tracing. This is an educational demo of functional routes/filters/error mapping, not a production system.

### 10.1. Dependencies

Use Spring Initializr with Java 17+, Spring Boot **3.5.x**, Gradle, and **Spring Web**. In a project that already has the Boot plugin and repository/dependency management, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a `build.gradle` fragment; a complete Gradle build file from Spring Initializr or your project is needed. The web starter includes the Spring MVC Servlet stack and Jackson JSON converter.

### 10.2. Full Java source

Create file **`src/main/java/demo/webfn/WebFnApplication.java`**:

```java
package demo.webfn;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.HandlerFilterFunction;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
public class WebFnApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFnApplication.class, args);
    }
}

record NewNote(String title) {}

record Note(long id, String title) {}

record ApiError(String code, String message) {}

class InvalidNoteException extends RuntimeException {
    InvalidNoteException() {
        super("Invalid note");
    }
}

class NoteNotFoundException extends RuntimeException {
    NoteNotFoundException() {
        super("Note not found");
    }
}

class NotesHandler {
    private final AtomicLong sequence = new AtomicLong(1000);
    private final ConcurrentMap<Long, Note> notes =
            new ConcurrentHashMap<>();

    ServerResponse list(ServerRequest request) {
        List<Note> result = notes.values().stream()
                .sorted(Comparator.comparingLong(Note::id))
                .toList();

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(result);
    }

    ServerResponse stats(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("count", notes.size()));
    }

    ServerResponse get(ServerRequest request) {
        long id;
        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException ex) {
            throw new InvalidNoteException();
        }

        Note note = notes.get(id);
        if (note == null) {
            throw new NoteNotFoundException();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }

    ServerResponse create(ServerRequest request) throws Exception {
        NewNote input = request.body(NewNote.class);
        if (input == null || input.title() == null
                || input.title().isBlank()
                || input.title().length() > 100) {
            throw new InvalidNoteException();
        }

        long id = sequence.incrementAndGet();
        Note note = new Note(id, input.title().trim());
        notes.put(id, note);

        // Request URI contains /api/v1/notes, drop old query.
        URI location = UriComponentsBuilder
                .fromUri(request.uri())
                .replaceQuery(null)
                .pathSegment("{id}")
                .encode()
                .buildAndExpand(id)
                .toUri();

        return ServerResponse.created(location)
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }
}

@Configuration
class FunctionalRoutesConfig {
    private static final Logger log =
            LoggerFactory.getLogger(FunctionalRoutesConfig.class);

    @Bean
    NotesHandler notesHandler() {
        return new NotesHandler();
    }

    private HandlerFilterFunction<ServerResponse, ServerResponse>
    notesDemoFilter() {
        return (request, next) -> {
            String client = request.headers()
                    .firstHeader("X-Demo-Client");

            if (!"learning".equals(client)) {
                return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(new ApiError(
                                "DEMO_HEADER_REQUIRED",
                                "X-Demo-Client must be learning"));
            }

            long started = System.nanoTime();
            try {
                return next.handle(request);
            } finally {
                long elapsed = System.nanoTime() - started;
                log.info("notes_route durationMicros={}",
                        elapsed / 1_000L);
            }
        };
    }

    @Bean
    RouterFunction<ServerResponse> applicationRoutes(
            NotesHandler handler) {

        return RouterFunctions.route()
                // Exempt from notes filter.
                .GET("/health", request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .body("OK"))

                // All inner routes use shared policies.
                .path("/api/v1", api -> api

                    // Static path before path variable.
                    .GET("/notes/stats", handler::stats)
                    .GET("/notes/{id}", handler::get)
                    .GET("/notes", handler::list)
                    .POST("/notes", handler::create)

                    .before(request -> {
                        log.info("notes_request method={}",
                                request.method());
                        return request;
                    })

                    .filter(notesDemoFilter())

                    .after((request, response) -> {
                        log.info("notes_response status={}",
                                response.statusCode().value());
                        return response;
                    })

                    .onError(InvalidNoteException.class,
                        (error, request) ->
                            ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .body(new ApiError(
                                        "NOTE_INVALID",
                                        "Invalid note input")))

                    .onError(NoteNotFoundException.class,
                        (error, request) ->
                            ServerResponse.status(HttpStatus.NOT_FOUND)
                                .contentType(MediaType.APPLICATION_JSON)
                                .body(new ApiError(
                                        "NOTE_NOT_FOUND",
                                        "Note does not exist"))))
                .build();
    }
}
```

**Java structure:** the file has one public top-level class (`WebFnApplication`), while the remaining records/classes are package-private. Java 17 supports `record` and `Stream#toList()`. Spring Boot component scanning from `demo.webfn` finds `FunctionalRoutesConfig`. The `applicationRoutes` bean is discovered by Spring MVC `RouterFunctionMapping`.

**Compiler note:** method references `handler::list`, `handler::stats`, `handler::get`, and `handler::create` all take `ServerRequest` and return `ServerResponse`. `create` declares `throws Exception`, matching `HandlerFunction#handle`. `UriComponentsBuilder.fromUri(request.uri())` accepts `URI` without needing a current request holder. `replaceQuery(null)` strips old request query params; `pathSegment("{id}")` + `encode()` + `buildAndExpand(id)` safely places the ID as a URI segment.

**Demo data note:** the in-memory map exists only within one JVM; restarting loses data and multiple nodes do not share state. Moving to production requires a service/database, transactions, auth/authorization, input validation, and product-level concurrency policies.

### 10.3. How to run

```bash
./gradlew bootRun
```

**Public health, no demo header required:**

```bash
curl -i 'http://localhost:8080/health'
```

Expected `200 OK` and body:

```text
OK
```

**Notes endpoint missing header:**

```bash
curl -i 'http://localhost:8080/api/v1/notes'
```

Expected `400 Bad Request` with JSON:

```json
{
  "code": "DEMO_HEADER_REQUIRED",
  "message": "X-Demo-Client must be learning"
}
```

**Notes list with header:**

```bash
curl -i 'http://localhost:8080/api/v1/notes' \
  -H 'X-Demo-Client: learning'
```

Initially (before any POST) expected body:

```json
[]
```

**Create note:**

```bash
curl -i -X POST \
  'http://localhost:8080/api/v1/notes?source=docs' \
  -H 'X-Demo-Client: learning' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Functional MVC"}'
```

For the first creation request, expected result:

```http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/v1/notes/1001
Content-Type: application/json

{"id":1001,"title":"Functional MVC"}
```

`source=docs` does **not** appear in Location thanks to `replaceQuery(null)`. ID 1001 is simply the result of the initial counter before any other create requests.

**Read note:**

```bash
curl -i \
  'http://localhost:8080/api/v1/notes/1001' \
  -H 'X-Demo-Client: learning'
```

Expected 200 and corresponding note body.

**Access static `stats` route:**

```bash
curl -i \
  'http://localhost:8080/api/v1/notes/stats' \
  -H 'X-Demo-Client: learning'
```

After exactly one POST, body:

```json
{"count":1}
```

If `/{id}` were placed before `/stats`, the string `"stats"` could be parsed as a numeric ID and return an error. The working example places the static route first.

**Enter non-numeric ID:**

```bash
curl -i \
  'http://localhost:8080/api/v1/notes/abc' \
  -H 'X-Demo-Client: learning'
```

Handler throws `InvalidNoteException` and `onError` returns 400:

```json
{"code":"NOTE_INVALID","message":"Invalid note input"}
```

**Valid ID that does not exist:**

```bash
curl -i \
  'http://localhost:8080/api/v1/notes/999999' \
  -H 'X-Demo-Client: learning'
```

Expected 404 and:

```json
{"code":"NOTE_NOT_FOUND","message":"Note does not exist"}
```

In other environments (especially behind a proxy/context path), Location host/prefix or headers depend on the actual request and deployment. These HTTP examples illustrate the output contract, **not logs from executing Gradle**.

## 11. Testing MVC Functional Routes with MockMvc

`MockMvc` boots the MVC test/request infrastructure without opening a network port. This test uses `@SpringBootTest` to ensure Spring Boot finds the `RouterFunction` bean and `@AutoConfigureMockMvc` to execute requests.

Create **`src/test/java/demo/webfn/WebFnApplicationTests.java`**:

```java
package demo.webfn;

import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebFnApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void healthIsNotAffectedByNestedFilter() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("OK"));
    }

    @Test
    void notesFilterShortCircuitsWithoutClientHeader()
            throws Exception {
        mvc.perform(get("/api/v1/notes"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DEMO_HEADER_REQUIRED"));
    }

    @Test
    void staticStatsRouteWinsBeforeVariableRoute()
            throws Exception {
        mvc.perform(get("/api/v1/notes/stats")
                .header("X-Demo-Client", "learning"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").isNumber());
    }

    @Test
    void invalidIdUsesFunctionalOnError400()
            throws Exception {
        mvc.perform(get("/api/v1/notes/not-a-number")
                .header("X-Demo-Client", "learning"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("NOTE_INVALID"));
    }

    @Test
    void missingNoteUsesFunctionalOnError404()
            throws Exception {
        mvc.perform(get("/api/v1/notes/999999999")
                .header("X-Demo-Client", "learning"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                    .value("NOTE_NOT_FOUND"));
    }

    @Test
    void postCreatesResourceAndLocationHasNoOldQuery()
            throws Exception {

        MvcResult response = mvc.perform(
                post("/api/v1/notes?source=docs")
                    .header("X-Demo-Client", "learning")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"title":"Created with WebMvc.fn"}
                        """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title")
                    .value("Created with WebMvc.fn"))
            .andReturn();

        String location = response.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);

        URI uri = URI.create(location);
        assertTrue(uri.getPath().matches(
                "/api/v1/notes/[0-9]+"));
        assertTrue(uri.getRawQuery() == null);

        mvc.perform(get(uri.getRawPath())
                .header("X-Demo-Client", "learning"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                    .value("Created with WebMvc.fn"));
    }

    @Test
    void blankTitleUsesFunctionalOnError400()
            throws Exception {
        mvc.perform(post("/api/v1/notes")
                .header("X-Demo-Client", "learning")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"   "}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("NOTE_INVALID"));
    }
}
```

Run:

```bash
./gradlew test
```

**Seven tests are designed to pass against the code and Spring Boot 3.5 baseline above**. These are expected results from code and Spring API analysis, **not evidence that Gradle was executed**. The tests do not assert fixed IDs or exact counts (other than numeric type) to avoid depending on test order or shared Spring context.

Meaningful checks:

- `/health` without header → nested filter does not leak to top-level route.
- `/notes` without header → `filter` short-circuits before the handler.
- `/notes/stats` returns stats JSON rather than misrouting to `/{id}`.
- Non-numeric ID → 400 from `onError(InvalidNoteException.class,...)`.
- Non-existent numeric ID → 404 from `onError(NoteNotFoundException.class,...)`.
- POST creates a note → 201 and Location contains no old query params.
- POST blank title → 400 per business validation mapping.

### 11.1. Testing filter scope and error mapping with negative cases

Valuable additional tests:

- Call `/health` with an arbitrary header and assert its behavior does not change.
- Call `/api/v1/notes/foo` without the demo header: the short-circuiting filter returns the header error **before entering the ID parser**, per the example's contract.
- Call an unmatched endpoint like `/does-not-exist`: the notes router's `onError` does **not** turn that 404 into NOTE_NOT_FOUND.
- Send syntactically invalid JSON with `Content-Type: application/json`: verify the actual error response produced by the message converter/MVC infrastructure rather than assuming it automatically maps to NOTE_INVALID.
- Put the same path in another router or add a catch-all before it: test route shadowing.
- When Security starter is enabled, test unauthorized access at the Servlet security filter layer, not just the demo header.
- Send requests with context paths and proxy headers in an integration test if Location must be an external URL.

### 11.2. When do you need to test against a real server?

`MockMvc` verifies MVC routing, handlers, filters, and `onError` without running a full embedded socket/gateway. When you need to check:

- Servlet filter registrations, CORS preflight, and security chains.
- Proxy/Host/Forwarded URL generation.
- Real content negotiation/compression/HTTP headers.
- Large multipart uploads, streaming, disconnects/timeouts.
- Multiple nodes/load balancing or transaction consistency.

Use `@SpringBootTest(webEnvironment=RANDOM_PORT)` + a real HTTP client, and run staging tests through your gateway when policies depend on a proxy/CDN.

## 12. `HandlerFilterFunction` and Filter Execution Order

Imagine nested filters:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> a =
        (request, next) -> {
            events.add("A-in");
            try {
                return next.handle(request);
            } finally {
                events.add("A-out");
            }
        };

HandlerFilterFunction<ServerResponse, ServerResponse> b =
        (request, next) -> {
            events.add("B-in");
            try {
                return next.handle(request);
            } finally {
                events.add("B-out");
            }
        };
```

This is a fragment where `events` is a list supplied by the test; if used concurrently, thread-safe instrumentation or a request-scoped event list is needed.

A specific chain `a.andThen(b).apply(handler)` has the conceptual flow:

```text
A-in
  B-in
    handler
  B-out
A-out
```

In practice, builders/nested routers also have other filter layers, `before`/`after`/`onError`, and wrapping order. When order affects access control or logging, assert event order in tests. **Do not rely on filter name labels or unspecified `@Bean` registration order**.

### 12.1. Filter chains do not guarantee safe multi-read body access

If a handler filter reads `request.body(NewNote.class)` to validate and the handler reads the body a second time, the Servlet request body may already be consumed. Do not write a JSON logging filter that reads the whole body and assume downstream still deserializes normally.

Solutions:

- Perform domain validation in the handler/service after parsing once.
- If a filter must inspect the raw payload, use a properly configured/bounded buffering wrapper or change the architecture.
- Never log raw credentials/PII/Authorization.
- Be cautious with large multipart bodies, streams, and memory limits.
- For audit events, record verified metadata instead of the entire request content.

### 12.2. Using try/finally for MDC

If using `MDC` for correlation IDs in a filter, always clean up:

```java
return (request, next) -> {
    String requestId = UUID.randomUUID().toString();
    MDC.put("requestId", requestId);
    try {
        return next.handle(request);
    } finally {
        MDC.remove("requestId");
    }
};
```

This is a fragment requiring imports `java.util.UUID` and `org.slf4j.MDC`. A filter only wraps **handler invocation**; if a streaming response body writes later on another thread, MDC may no longer be present and separate context propagation is required. If you need a correlation ID earlier for Servlet filters/error responses, consider a Servlet-level filter or tracing/observability framework.

## 13. Error Handling: Classifying "Unmatched", "Client Error", and "Server Error"

### 13.1. Unmatched route ≠ exception in handler

For example, `GET /api/v1/unknown` may not match any functional router. `onError(NoteNotFoundException.class,...)` is **not** invoked merely because the request ends in 404.

When a route matches yet the note ID is absent from the repository, the handler throws `NoteNotFoundException`: that is a business error mapped by `onError` to 404. Both cases yield the same status, though their source and error body can differ.

### 13.2. Bad request vs. not found

| Case | Recommended Status | Source of Handling |
| --- | --- | --- |
| Missing demo header per lesson contract | 400 | Short-circuit in `HandlerFilterFunction` |
| Unparseable ID for `/{id}` | 400 | `InvalidNoteException` → `onError` |
| Valid ID but record does not exist | 404 | `NoteNotFoundException` → `onError` |
| Route does not exist | 404 (typical) | MVC handler mapping / default error handling |
| Malformed JSON body syntax | 400 (typical) | Message converter + MVC exception infrastructure |
| Unsupported request media type | Possibly 415 depending on routes/config | Predicate/HTTP handling and explicit error contract |
| Inappropriate HTTP method | Possibly 405 or fallback handling depending on mappings | Request mapping/resolvers |
| Unauthenticated | 401 | Spring Security authentication |
| Authenticated without sufficient permissions | 403 | Spring Security authorization |
| Unexpected server code/persistence failure | 500 | Error infrastructure/monitoring |

Never turn every exception into 200 with `{"ok":false}`. HTTP status codes are an essential part of a public API.

### 13.3. Committed responses have limits

If a handler/filter produces a streaming response and an error occurs **after the first bytes are sent**, `onError` may be unable to alter headers or status. This is an HTTP/Servlet lifecycle constraint, not unique to functional APIs.

To signal errors inside an already-open stream, use an in-stream framing/error protocol (e.g., an `"error"` event type in SSE), or let clients handle disconnects/retries. Never dump stack traces into an open body.

## 14. Can Functional Routes Coexist with Annotated Controllers?

Yes. In Spring MVC, `RouterFunctionMapping` and annotated `RequestMappingHandlerMapping` are both handler mappings under `DispatcherServlet`. One app can have both:

```java
@RestController
class LegacyController {
    @GetMapping("/legacy/ping")
    String ping() {
        return "pong";
    }
}
```

and:

```java
@Bean
RouterFunction<ServerResponse> functionalRouter() {
    return RouterFunctions.route()
            .GET("/new/ping",
                request -> ServerResponse.ok().body("pong"))
            .build();
}
```

These two illustrative fragments run side by side in a Boot MVC application. However:

- A `HandlerFilterFunction` on `/new/ping` does not automatically run for `/legacy/ping`.
- `@ControllerAdvice`, interceptors, HandlerAdapters, and message converters have their own scopes/semantics.
- If an annotated controller and a functional router register **the exact same method/path**, handler mapping order decides who gets the request, leading to surprises.
- Organize routes to avoid overlap between functional and annotated styles, especially during module-by-module migrations.
- Path/method security policies must cover both, not only one controller style.

A good migration strategy is converting one bounded module at a time (e.g., `/api/v2/catalog/**`), testing the API contract, keeping remaining annotated controllers, and evaluating complexity before converting more.

## 15. CORS, Security, and Observability

### 15.1. Spring Security and CORS

The WebMvc.fn documentation explicitly notes that CORS support for functional endpoints is provided via a **dedicated `CorsFilter`**. Do not assume the functional builder automatically carries all CORS annotation support like annotated controllers.

For APIs with cross-origin clients:

- Configure `CorsFilter` or Spring Security CORS integration matching the Servlet filter chain.
- Verify `OPTIONS` preflight requests are handled properly **before the relevant authentication layer**.
- Never use `Access-Control-Allow-Origin: *` when returning credentials/cookies cross-origin.
- CORS does not replace authentication/authorization/CSRF; non-browser clients are not restricted by CORS.
- When using cookies with state-changing requests, design CSRF and SameSite according to your threat model.

The simulated `X-Demo-Client` header in the sample code **is not a security control**. Clients can send any value. For real protection, build a `SecurityFilterChain`, validate bearer tokens/sessions, and authorize per resource.

### 15.2. Safe metric/logging fields

Recommended to collect:

- Route template/operation name, HTTP method, and status class.
- Latency buckets, count/error rate.
- Correlation ID generated by the server or trusted infrastructure.
- Categorized exception type/error code, not raw exception messages.
- Pseudonymous tenant/user ID per privacy policy if needed.

Never log raw request bodies, Authorization headers, cookies, passwords, OTPs, access tokens, or sensitive query parameters. If logged request paths contain resource IDs/PII, replace them with templates or properly designed hashes/pseudonyms.

`HandlerFilterFunction` can measure synchronous duration around `next.handle`, **not necessarily the full duration of streaming body writes**, timeouts, or network latency. For full HTTP lifecycle metrics, use Servlet filters/observability frameworks at the proper layer.

## 16. When to Use `HandlerFilterFunction` vs. Other Mechanisms?

| Goal | Appropriate Mechanism | Why |
| --- | --- | --- |
| Run checks before a group of functional routes | `RouterFunctions.Builder.filter` | Applies only to matching route group, can short-circuit |
| Simple functional request transformation | `before` | Clear code, no need to invoke next manually |
| Record status after handler function | `after` | Receives the constructed `ServerResponse` |
| Convert domain exceptions to HTTP bodies for a route group | `onError` | Local, explicit error mapping |
| Reuse a filter on an already-built router function | `RouterFunction.filter(...)` | Composition after router creation |
| CORS preflight and servlet-level concerns | `CorsFilter`/Servlet Filter | Runs before functional routing |
| Authentication/authorization across all entry points | `SecurityFilterChain` | Unified HTTP-layer protection |
| Intercept annotated controller handlers | `HandlerInterceptor` | Aware of MVC handler execution context |
| Global exception/ProblemDetail policies | MVC exception infrastructure/`@ControllerAdvice` with compatibility tests | Not limited to a single router |
| Streaming HTTP responses | `ServerResponse` streaming API or MVC streaming APIs | Mind async/response commit behavior |
| Full-request event/log tracing including unmatched requests | Servlet filter/observation pipeline | Handler filters run only after route matching |

When an application is tiny, three routes and one filter can sit in one class. As a domain grows many routes, separate routers, handlers, services, and filters by module to avoid an unreadable "God Config."

## 17. Common Pitfalls and How to Diagnose Them

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| Filter does not run on annotated controller | Filter attached only to a functional router | Distinguish `HandlerFilterFunction` and Servlet Filter |
| Notes filter accidentally runs on /health | `.filter(...)` placed on outer builder | Move filter into nested builder, add test |
| GET /notes/stats enters get ID | `/{id}` route precedes static route | Swap order, test stats output |
| Route does not match yet onError does not run | No selected handler/exception | Distinguish 404 mapping vs. exception |
| Malformed JSON returns unexpected error body | Handled by message converter/MVC resolver | Test invalid JSON, configure global error handling |
| Returns 200 yet body reports an error | Exception caught and accidentally returned as success body | Use proper HTTP statuses |
| Exception leaks raw message in JSON | Error handler returns `error.toString()` | Stable safe error codes/messages |
| Header gate treated as authentication | Client-supplied header | Use Spring Security |
| Filter added yet barely logs anything | No route match or wrong filter scope | Log selected route, check mapping |
| Behavior changes across multiple @Bean routers | Bean order/route overlaps | Reduce overlap, enforce explicit order and tests |
| v1/v2 route groups pick wrong version | Path/predicate overlap and first match | Isolate by group, test each version |
| `ServerRequest.body(...)` cannot be read again after reading | Body stream already consumed | Deserialize once, no double-reading |
| `before` adds header yet downstream sees odd value | Duplicate/forged header from client | Do not use request headers as trusted identity |
| `after` does not run on exception | No successful response before throw | Proper `try/finally` or `onError` |
| Filter `try/finally` metric shorter than full download | `ServerResponse` body may write afterward | Measure Servlet lifecycle end-to-end |
| Boot does not discover routes | Missing `@Bean`/component scan or wrong WebFlux imports | Check router bean, WebMvc.fn packages |
| Annotated controller mapping collides with router | HandlerMapping ordering | Avoid overlapping, add tests |
| CORS preflight gets 401/403 | Missing proper CorsFilter/Security integration | Check Servlet filter ordering |
| MockMvc tests differ from real server | Filter/proxy/container behaviors not simulated | `RANDOM_PORT` + gateway tests |

### Debugging workflow

1. Confirm the app uses Spring MVC (`spring-webmvc`), not WebFlux by mistake.
2. Confirm `RouterFunction<ServerResponse>` exists as a Spring bean.
3. Check HTTP method, path, query, Accept, and Content-Type.
4. Check declared route order and route shadowing.
5. Check nested/outer scopes of `before`/`after`/`filter`/`onError`.
6. If the route matches, check whether filters invoke `next.handle(request)`.
7. If the handler throws an exception, verify `onError` predicate/class matching.
8. If still failing, inspect HandlerExceptionResolver/Boot error handling.
9. Verify response status, Location, and JSON body against the API contract.
10. If errors occur only in production, check Servlet Filters/Security/proxies/tracing before MVC.

## 18. Comparing Spring Versions

| Environment | Key Points to Watch |
| --- | --- |
| Spring Framework 5.2+ / Boot 2.x | WebMvc.fn introduced in Spring 5.2; many Servlet APIs use `javax.servlet.*` |
| Spring Framework 6.2 / Boot 3.5 | Java 17+, Jakarta Servlet `jakarta.servlet.*`, WebMvc.fn builder and error handlers as shown |
| Spring Framework 7.x / Boot 4.x | Functional route/filter concepts continue evolving; starter and test infrastructure may change; check version-matched Javadoc |

Do not copy `Mono<ServerResponse>` signatures or import reactive packages from WebFlux.fn into WebMvc.fn code. Certain newer methods like API-version-aware route predicates may appear only in newer Framework versions; do not slip Spring 7 methods into examples targeting Spring 6.2.

Detailed WebMvc.fn references appear in both Spring Framework docs and Javadocs for `org.springframework.web.servlet.function`. When upgrading Boot major versions, check:

- `RouterFunctions.Builder` method overloads.
- `ServerRequest`/`ServerResponse` serialization and message converters.
- `spring-boot-starter-web`/MVC starter dependencies for that version.
- Spring Security CORS integration.
- MockMvc test imports/autoconfig.
- `RouterFunctionMapping` bean ordering and path matching.
- Error formatting/ProblemDetail policies.

## 19. Practical Deployment Checklist

- [ ] RouterFunction bean contains only routes for the right module/version.
- [ ] Static paths precede variable/wildcard paths when overlapping.
- [ ] Method/media-type predicates have clear contracts.
- [ ] Nested path filters do not accidentally leak to top-level routes.
- [ ] Shared filters always call `next` for valid requests.
- [ ] Short-circuit statuses/bodies are accurate and user-controlled demo headers are never used for auth.
- [ ] `before`/`after` match the lifecycle; `try/finally` handles cleanup.
- [ ] `onError` intentionally matches domain exceptions rather than catching every throwable as 400.
- [ ] Public error messages never expose exception internals/secrets.
- [ ] Missing routes and missing resources have distinct error contracts/tests.
- [ ] `ServerRequest` bodies are parsed only as needed; inputs are bounded and validated.
- [ ] Security/CORS/CSRF are applied at the proper Servlet/Security layer.
- [ ] Multiple router beans are composed/ordered intentionally with no unintended overlap.
- [ ] Tests cover route order, nested filters, `onError` 400/404, and POST Location.
- [ ] HTTP integration tests cover proxy/security environments when critical.
- [ ] Functional routes and annotated controllers do not register overlapping mappings.
- [ ] Metrics/logging use route templates and never log secrets.
- [ ] API docs accurately describe success/error schemas and statuses.

## 20. Practice Exercises

1. In the demo, move `GET("/notes/{id}")` before `GET("/notes/stats")`. What happens on `GET /api/v1/notes/stats` and why?
2. Move `.filter(notesDemoFilter())` from the nested builder to the outer builder. Does `GET /health` still return 200 without the header?
3. Write a `HandlerFilterFunction` measuring latency with `try/finally`. Why might this number differ from end-to-end HTTP response time with a streaming body?
4. Move the demo header rule from `filter` to `before`. Why is `before` unsuitable when you want to short-circuit explicitly as shown above?
5. Use `ServerRequest.from(request)` to create a request wrapper adding a demo header. Why must this value never be used as an authenticated principal?
6. Create an `ApiError` record matching a contract with `code` and `message`; add an `onError` handler for a new business exception.
7. A request matching no route receives 404. Why is `onError(NoteNotFoundException.class,...)` not necessarily invoked?
8. A POST with malformed JSON triggers a 400 from the framework. Identify which exception resolver handles it; should you use a catch-all `onError`?
9. Add `GET /api/v2/notes` with a different schema, separating filters and error contracts by version, and write tests.
10. Register the same URL in an annotated controller and a RouterFunction bean. Observe handler mapping order; why should this be avoided in production?
11. Split the single-file demo into `NotesRoutes`, `NotesHandler`, `NotesService`, and `ApiError` while keeping all tests passing.
12. Write a filter returning 429 when a rate limit threshold is reached **using server-side counters**, not a client-sent header. Why should you prefer gateway/Security rate limiters across multiple entry points?
13. With Spring Security enabled, explain why `HandlerFilterFunction` does not replace `SecurityFilterChain`.
14. Why should a `@ControllerAdvice` for annotated controllers not be assumed to cover all WebMvc.fn errors without testing?
15. Attach `.after(...)` to log status and have the handler throw an exception. Can `after` be skipped? When should metrics live in the Servlet observation layer?
16. Use `RouterFunctions.route().add(ordersRouter).add(notesRouter)` and analyze the effect if the two routers overlap.
17. Add an `accept(MediaType.APPLICATION_JSON)` request predicate. Distinguish it from `contentType(APPLICATION_JSON)`.
18. Design a MockMvc test verifying the filter short-circuits before the handler inserts a record into the database.
19. Build consistent error responses for unknown routes and unknown resources using `ProblemDetail`/MVC error infrastructure without mis-catching 401/403.
20. If the app must run on Spring Boot 4, which starter/test APIs and framework versions must be checked before copying examples?

## 21. Official Documentation

- [Spring Framework 6.2 — WebMvc.fn Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): RouterFunction, HandlerFunction, nested routes, filters, route matching order, server execution.
- [Spring Framework 6.2 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.Builder.html): GET/POST/path/nest/add/filter/before/after/onError overloads.
- [Spring Framework 6.2 — HandlerFilterFunction Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/function/HandlerFilterFunction.html): filter(request,next), composition, ofErrorHandler, request/response adapters.
- [Spring Framework 6.2 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/function/ServerRequest.html): body, pathVariable, params, URI, and headers.
- [Spring Framework 6.2 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/function/ServerResponse.html): ok/created/status/build/body.
- [Spring Framework 6.2 — RouterFunction Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/function/RouterFunction.html): route, and, andRoute, filter.
- [Spring Framework 6.2 — MVC Exception Handling](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/exceptionhandlers.html): HandlerExceptionResolver pipeline.
- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): RFC 9457 ProblemDetail and MVC error architecture.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): MVC auto-configuration, RouterFunction integration.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): Servlet MVC handler testing.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): SecurityFilterChain; not replaced by WebMvc.fn filters.
