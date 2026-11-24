# ServerRequest, ServerResponse, and HandlerFunction in Spring Web MVC Functional Endpoints

## 1. What Problem Does Functional MVC Solve?

In familiar Spring MVC, we typically declare `@RestController`, `@GetMapping`, and `@PostMapping`. Spring scans the annotations to select a handler for each HTTP request. Alongside that model, **Spring Web MVC also provides WebMvc.fn**, a **functional endpoints** API: you describe routes with functions and process requests using Java lambdas or method references.

The core contract is:

- `ServerRequest`: the **input** abstraction, providing HTTP method, URI, query/path parameters, headers, cookies, and body reading/binding.
- `HandlerFunction<ServerResponse>`: the **handling function**, receiving a `ServerRequest` and returning a `ServerResponse`.
- `ServerResponse`: the **output** abstraction, representing status, headers, cookies, and body; constructed via a builder (immutable contract).
- `RouterFunction<ServerResponse>`: the **selection rule**; receives a request and returns `Optional<HandlerFunction<ServerResponse>>` when matched.

A simple composition:

```java
HandlerFunction<ServerResponse> sayHello =
        request -> ServerResponse.ok().body("Hello");

RouterFunction<ServerResponse> router =
        RouterFunctions.route(
                RequestPredicates.GET("/hello"), sayHello);
```

This is an illustrative snippet for understanding the signatures. A complete runnable Spring Boot example is in section 10.

**A very important point:** WebMvc.fn runs on the **Servlet stack** with `DispatcherServlet`. It is **not** WebFlux.fn; you do not need Reactor `Mono`/`Flux` to use these three components. The Servlet API uses the package:

```java
org.springframework.web.servlet.function.ServerRequest
org.springframework.web.servlet.function.ServerResponse
org.springframework.web.servlet.function.HandlerFunction
org.springframework.web.servlet.function.RouterFunction
org.springframework.web.servlet.function.RouterFunctions
org.springframework.web.servlet.function.RequestPredicates
```

WebFlux.fn uses `org.springframework.web.reactive.function.server.*` and asynchronous signatures such as `Mono<ServerResponse>`. Importing from the wrong ecosystem will cause compilation errors or incorrect expectations about how the body is read.

### 1.1. Learning Objectives

After this lesson, you can:

1. Accurately explain the relationship `RouterFunction → HandlerFunction → ServerResponse`.
2. Read route parameters, query parameters, headers, and JSON bodies from `ServerRequest`.
3. Return 200, 201 with Location, 204, 400, 404, and JSON using the `ServerResponse` builder.
4. Compose `RouterFunctions.route()`, understanding route evaluation order, `RequestPredicates`, path nesting, and composition.
5. Use `HandlerFilterFunction`/`before`/`after` without confusing them with Servlet Filters or Spring Security.
6. Separate routing from business logic, validation, transactions, errors, and security; understand the limits of the functional style.
7. Build a Spring Boot 3 + Java 17 application with list/search/get/create/delete routes and 9 MockMvc tests.

This lesson applies to Spring Framework 6.x / Spring Boot 3.x with Java 17+. Java records are used to write concise DTOs.

## 2. Execution Flow Under DispatcherServlet

WebMvc.fn does not create a second web server. It uses the same Servlet MVC infrastructure as annotated controllers:

```text
Browser/API client
     │ HTTP GET /api/notes/1
     ▼
Servlet filters (security, logging, ...)
     │
     ▼
DispatcherServlet
     │
     ▼
HandlerMapping chain
     ├── RouterFunctionMapping
     │      └── RouterFunction<ServerResponse>
     │             ├── evaluate route's RequestPredicate
     │             └── return HandlerFunction if matched
     │
     ├── RequestMappingHandlerMapping
     │      └── annotated @GetMapping/@PostMapping...
     │
     └── other HandlerMappings
     │
     ▼
HandlerFunctionAdapter
     │
     ▼
HandlerFunction.handle(ServerRequest)
     ├── read request
     ├── call service/repository
     └── create ServerResponse
     │
     ▼
ServerResponse.writeTo(...) / HTTP converters
     ▼
HTTP status + headers + body
```

The diagram is a conceptual outline and **does not assert that RouterFunctionMapping always has higher precedence than RequestMappingHandlerMapping** in every Spring/Boot configuration. HandlerMappings have their own `order` and setup; when a URL has both handler types competing, check the actual HandlerMapping order and avoid declaring the same path in both functional and annotated controllers.

In a typical Spring Boot MVC setup, you only need:

```java
@Bean
RouterFunction<ServerResponse> routes(NoteHandlers handlers) {
    return RouterFunctions.route()
            .GET("/api/notes", handlers::list)
            .GET("/api/notes/{id}", handlers::get)
            .build();
}
```

Spring automatically discovers `RouterFunction<?>` beans, combines/registers them via `RouterFunctionMapping`, and uses `HandlerFunctionAdapter` to invoke the handler. You do not need to configure a separate Servlet. `spring-boot-starter-web` is usually sufficient to enable the WebMvc.fn infrastructure.

### 2.1. Comparison with @RestController

Annotated style:

```java
@RestController
class NoteController {
    @GetMapping("/api/notes/{id}")
    Note get(@PathVariable long id) {
        return service.find(id);
    }
}
```

Functional style:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/notes/{id}", handlers::get)
                .build();
```

The end behavior can be the same, but responsibilities differ:

| Annotated MVC | WebMvc.fn |
| --- | --- |
| Annotations on class/method determine mapping | `RouterFunction` and `RequestPredicate` determine mapping |
| Parameters are bound into method arguments | `ServerRequest` provides accessor methods |
| Returns DTO/ResponseEntity | Returns `ServerResponse` |
| Logic usually placed in controller method | Logic in lambda/handler class |
| Advice/validation/integration follow annotated MVC conventions | Requires explicit understanding of WebMvc.fn binding/exception/filter pipeline |
| Can coexist on DispatcherServlet | Can coexist with annotated controllers |

WebMvc.fn does not automatically speed up every endpoint or make blocking JDBC non-blocking. Its main value lies in **composable route definitions**, behavior expressed as functions, and clear separation between route mapping and handler logic.

## 3. HandlerFunction: One Function Handling One Request

In essence, the API signature can be understood as:

```java
@FunctionalInterface
public interface HandlerFunction<T extends ServerResponse> {
    T handle(ServerRequest request) throws Exception;
}
```

This is a **summary signature** for learning, not the full Spring source code. Lambda:

```java
HandlerFunction<ServerResponse> hello = request ->
        ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("Hello from WebMvc.fn");
```

A handler class is often easier to maintain than many large lambdas:

```java
class NoteHandlers {
    ServerResponse list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(List.of("Spring", "MVC"));
    }

    ServerResponse health(ServerRequest request) {
        return ServerResponse.ok().body("OK");
    }
}
```

The code above illustrates methods referenced via `handlers::list`, `handlers::health`. In a full project, the handler is made a Spring component, injected with services, and passed into a RouterFunction bean.

### 3.1. HandlerFunction does not have to be a Spring bean

A lambda can be created inside the route bean; a handler class can be a Spring `@Component`, a manually constructed object, or supplied via DI. What matters is that `RouterFunction` holds a reference to a valid handler.

However, **do not `new Service()` everywhere** if the service requires Spring-managed transactions/security/configuration. Separating dependencies and injecting via constructor improves testability.

### 3.2. Checked exceptions

`HandlerFunction#handle` allows throwing `Exception`. A handler method that reads a JSON body can declare `throws Exception`:

```java
ServerResponse create(ServerRequest request) throws Exception {
    CreateNote command = request.body(CreateNote.class);
    return ServerResponse.ok().body(command);
}
```

This is only a syntax example; in production, you must validate the command and handle decode/validation errors according to your error contract. Never return stack traces or raw persistence exceptions to clients.

## 4. ServerRequest: Reading the HTTP Request Through One Interface

`ServerRequest` is the handler-side facade for a Servlet HTTP request. Common API groups:

| Need | Typical API | Output |
| --- | --- | --- |
| Method | `request.method()` | `HttpMethod` |
| Full URI | `request.uri()` | `URI` |
| Path | `request.path()` | Request path string |
| Single query value | `request.queryParam("q")` | `Optional<String>` |
| All query params | `request.params()` | `MultiValueMap<String,String>` |
| Path variable | `request.pathVariable("id")` | `String` |
| Headers | `request.headers()` | `ServerRequest.Headers` |
| Single header | `request.headers().firstHeader("X-Request-Id")` | String or null |
| Typed body | `request.body(CreateNote.class)` | DTO from `HttpMessageConverter` |
| Generic body | `request.body(new ParameterizedTypeReference<List<Note>>() {})` | `List<Note>` |
| Underlying Servlet request | `request.servletRequest()` | `HttpServletRequest` |
| Bind params | `request.bind(Foo.class, binder -> ...)` | Object via binder |

Some methods can throw an exception when a path variable is missing or input fails to parse. `ServerRequest` makes functional code more convenient, **without bypassing** HTTP semantics, converters, or validation.

### 4.1. Path parameters

Route:

```java
RouterFunctions.route()
    .GET("/api/notes/{id}", handlers::get)
    .build();
```

Handler:

```java
ServerResponse get(ServerRequest request) {
    String raw = request.pathVariable("id");
    long id;
    try {
        id = Long.parseLong(raw);
    } catch (NumberFormatException ex) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("error", "invalid_id"));
    }

    return service.find(id)
            .map(note -> ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(note))
            .orElseGet(() -> ServerResponse.notFound().build());
}
```

This is an illustrative snippet, not a standalone method because `service` is undeclared. The complete example uses ConcurrentHashMap so it does not depend on a DB.

**Note:** `ServerRequest.pathVariable("id")` returns a string and does not automatically perform type conversion identically to `@PathVariable long id` on an annotated controller. The handler must parse it and decide the error response per the contract.

### 4.2. Query params

```java
String q = request.queryParam("q").orElse("");
String trimmed = q.trim();
```

If a query parameter has multiple values, `request.params()` lets you read the list. Distinguish:

- `pathVariable("id")` from `/{id}` in the route.
- `queryParam("q")` from `?q=spring`.
- `headers().firstHeader("...")` from HTTP headers.
- `body(...)` from the request entity.

Do not read `request.body(...)` twice arbitrarily: a normal Servlet request body stream is not automatically rewound. Consume the DTO once and pass the DTO to the service.

### 4.3. Headers and content negotiation

```java
MediaType requested =
        request.headers().accept().stream()
                .findFirst()
                .orElse(MediaType.ALL);

String correlation =
        request.headers().firstHeader("X-Request-Id");
```

This snippet illustrates access; the server does not necessarily pick the first media type to determine the response in every situation. Use `RequestPredicates.accept(MediaType.APPLICATION_JSON)` or Spring HTTP converters when explicit negotiation is desired.

Do not treat a client-supplied header like `X-User-Role` as proof of authorization. Headers can be forged by non-browser clients; authentication/authorization must rely on trust boundaries and Spring Security.

### 4.4. Reading a JSON body

With `spring-boot-starter-web`, Jackson and MVC converters normally support JSON:

```java
record CreateNote(String title) {}

ServerResponse create(ServerRequest request) throws Exception {
    CreateNote data = request.body(CreateNote.class);

    if (data == null || data.title() == null ||
            data.title().isBlank()) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("error", "title_required"));
    }

    return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(data);
}
```

This snippet can be placed in a handler class alongside the record; Java 17 supports records. When JSON syntax is invalid or the content type is unsupported by converters, Spring can throw a parse/media-type error to be handled by the exception-handling layer.

**Do not assume** that placing `@Valid` on a record type or a `HandlerFunction` parameter automatically produces a `BindingResult` like an annotated controller. A functional endpoint needs to run validation **explicitly**, or use an appropriate binder/validator integration.

### 4.5. Binding form/query params

The Spring MVC Functional API provides:

```java
FormInput input = request.bind(
        FormInput.class,
        binder -> binder.setAllowedFields("title", "category"));
```

The snippet above illustrates the binder, requiring `FormInput` to be a bindable class with corresponding properties. `setAllowedFields(...)` helps reduce **mass assignment** when binding from request parameters; understand how binding/validation errors are reported back to the handler or MVC exception resolution.

For JSON bodies, use dedicated request DTOs; do not deserialize directly into persistence entities containing fields such as role, ownerId, or paymentStatus and save them unchecked.

## 5. ServerResponse: Building Status, Headers, and Body

`ServerResponse` has an immutable-style contract. You do not mutate an already "built" response arbitrarily; instead, you call static builders to create responses:

```java
ServerResponse response = ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .header("X-Demo", "webmvc-fn")
        .body(Map.of("status", "ready"));
```

Common static entrypoints:

| Goal | Example |
| --- | --- |
| 200 OK with body | `ServerResponse.ok().body(data)` |
| 200 JSON | `ServerResponse.ok().contentType(APPLICATION_JSON).body(data)` |
| 201 Created | `ServerResponse.created(location).body(resource)` |
| 204 No Content | `ServerResponse.noContent().build()` |
| 400 Bad Request | `ServerResponse.badRequest().body(error)` |
| 404 Not Found | `ServerResponse.notFound().build()` |
| 401/403/409/422... | `ServerResponse.status(HttpStatus.CONFLICT).body(error)` |
| Redirect | `ServerResponse.temporaryRedirect(uri).build()` |
| Custom header | Builder `.header("X-Key", "value")` |
| Content type | Builder `.contentType(MediaType.APPLICATION_JSON)` |

### 5.1. 200 with body

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(Map.of("id", 12, "name", "Example"));
```

Expected JSON output:

```json
{"id":12,"name":"Example"}
```

JSON object key order is not a default contract; assert individual fields rather than doing byte-for-byte string comparisons.

### 5.2. 201 + Location

```java
URI location = URI.create("/api/notes/12");
return ServerResponse.created(location)
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Note(12, "Created"));
```

A good "create" response normally has status `201 Created` and a `Location` header pointing to the URL of the new resource. In production, depending on requirements, the URI can be absolute (correct host/context path through a reverse proxy) or relative like the demo; do not assemble hosts from untrusted headers.

### 5.3. 204 and empty body

```java
return ServerResponse.noContent().build();
```

HTTP 204 has no representation body. Do not attach JSON content to the response and expect browsers to receive a body on 204.

### 5.4. Response body is not automatically a WebFlux Publisher

In WebMvc.fn:

```java
ServerResponse.ok().body(note);
```

This is the Servlet MVC API. WebFlux.fn typically writes a `Mono<ServerResponse>` or response builder with `bodyValue(...)` depending on the API. Certain async adapters support async bodies in WebMvc.fn, **but do not infer that the Servlet API is identical to the reactive stack**. If the app requires end-to-end non-blocking execution, evaluate the stack, dependencies, and contracts separately.

## 6. RouterFunction: Which HandlerFunction Receives the Request?

A router is a function that selects a handler. With the builder:

```java
@Bean
RouterFunction<ServerResponse> routes(NoteHandlers handler) {
    return RouterFunctions.route()
            .GET("/api/notes/search", handler::search)
            .GET("/api/notes/{id}", handler::get)
            .GET("/api/notes", handler::list)
            .POST("/api/notes", handler::create)
            .DELETE("/api/notes/{id}", handler::delete)
            .build();
}
```

**Order inside RouterFunction matters.** Spring evaluates routes in order; the first matching route is selected. Therefore, place `GET /api/notes/search` **before** `GET /api/notes/{id}`; otherwise, the string `search` could be treated as `id`, resulting in 400/404 in the wrong handler.

### 6.1. Typical RequestPredicates

You can match not only the URL, but also method, Accept, and Content-Type:

```java
import static org.springframework.web.servlet.function.RequestPredicates.*;

RouterFunction<ServerResponse> router = RouterFunctions.route()
    .GET("/api/notes", accept(MediaType.APPLICATION_JSON),
         handler::list)
    .POST("/api/notes", contentType(MediaType.APPLICATION_JSON),
          handler::create)
    .build();
```

This is an example configuration **different** from the runnable project's routes in section 10. Predicates can be combined:

```java
RequestPredicate predicate =
        RequestPredicates.GET("/api/notes")
                .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));
```

When a predicate fails to match, RouterFunction may try the next route; if no route matches, Servlet MVC looks for other handlers and may return 404/405/406/415 depending on mappings/converters and infrastructure. **Do not claim that every HTTP content-type error is automatically returned as 415 by WebMvc.fn**, especially when a POST route has an unmatched `contentType` predicate.

### 6.2. Nested routes

When multiple endpoints share a prefix, you can group them:

```java
return RouterFunctions.route()
    .path("/api/notes", builder -> builder
        .GET("/search", handler::search)
        .GET("/{id}", handler::get)
        .GET(handler::list)
        .POST(handler::create))
    .build();
```

This is an alternative configuration to routes using absolute paths; do not define both simultaneously to avoid duplicate mappings. When nesting, understand empty paths and slashes in the builder; to avoid confusion between `/api/notes` and `/api/notes/`, configure and test the exact actual URLs.

### 6.3. Composing RouterFunctions

You can combine multiple route groups:

```java
RouterFunction<ServerResponse> apiRoutes = ...;
RouterFunction<ServerResponse> adminRoutes = ...;

RouterFunction<ServerResponse> all =
        apiRoutes.and(adminRoutes);
```

Or builder `.add(otherRouter)`, `.andRoute(predicate, handler)`. Composition order matters because router functions are evaluated sequentially; avoid catch-all patterns too early.

### 6.4. Coexisting multiple RouterFunction beans

`RouterFunctionMapping` can auto-discover, sort, and combine RouterFunction beans. With multiple beans having overlapping paths, establish an explicit order and test the outcome; do not assume bean names or Java file order decide precedence. For a moderate API group, one router bean per domain/module is usually clear enough.

### 6.5. RouterFunctionMapping order differs from route order in the builder

There are two layers:

1. **Between HandlerMappings:** MVC/annotation/static-resource mappings each have their own order.
2. **Inside a RouterFunction:** routes within a function are tried in declaration/composition order.

A URL with a specific functional route can still never reach that router if another HandlerMapping is chosen first. Do not confuse "putting a specific route first" with changing `HandlerMapping#order` across all of MVC.

## 7. HandlerFilterFunction: Behavior Before/After HandlerFunction

WebMvc.fn provides functional-style middleware via `HandlerFilterFunction`. A filter receives:

- `ServerRequest request`.
- `HandlerFunction<ServerResponse> next`.

It can pre-process the request, call `next.handle(request)`, inspect the response, or **omit calling next** to return a response early.

Illustrative filter example:

```java
.filter((request, next) -> {
    if ("reject".equals(
            request.headers().firstHeader("X-Demo-Flow"))) {
        return ServerResponse.status(
                HttpStatus.TOO_MANY_REQUESTS)
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("error", "demo_filtered"));
    }
    return next.handle(request);
})
```

In the full project, this is a **demo scenario to verify middleware can short-circuit**, **not production authorization/security filtering**. A client can choose the X-Demo-Flow header freely, so do not use it for user identity decisions or real rate limiting.

### 7.1. before and after

The builder also provides `before` and `after`:

```java
.before(request ->
        ServerRequest.from(request)
                .header("X-Internal-Hint", "demo")
                .build())
.after((request, response) -> {
    // logging/observability (avoid logging sensitive data)
})
```

This example describes the API and is not a complete standalone RouterFunction. `before` can supply a customized ServerRequest wrapper downstream; `after` fits lightweight post-handler observation. Do not use hooks for heavy CPU work or write to HttpServletResponse once the response has committed.

**Inside nested routes**, a filter placed inside a nested builder applies only to that child group, unlike a filter placed on the root builder which applies to all routes in the root. Test filter scope with URLs both outside and inside the group.

### 7.2. Comparison with Servlet Filter and HandlerInterceptor

| Tool | Layer | Scope |
| --- | --- | --- |
| Servlet `Filter` | Container, before DispatcherServlet | By URL/dispatcher mapping, can apply broadly |
| MVC `HandlerInterceptor` | Spring MVC handler chain | Before/after matching MVC handlers |
| WebMvc.fn `HandlerFilterFunction` | Inside RouterFunction | Only the wrapped routes |
| Spring Security `SecurityFilterChain` | Security Servlet filters | Authentication, authorization, CSRF, headers... |
| `@ControllerAdvice` | MVC error/binding/response handling | Different scope and support depending on handler adapter |

In production, authentication/authorization should be handled by Spring Security, not replaced with a request header and HandlerFilterFunction. Functional middleware is useful for domain-specific logic, lightweight enrichment, or custom error mapping for a route group.

## 8. Validation, Exceptions, and Persistence

### 8.1. Validation with DTOs

A functional handler reads the body:

```java
CreateNote input = request.body(CreateNote.class);
```

Decoding into a Java record **does not guarantee that all Bean Validation constraints run automatically like an annotated method with `@Valid @RequestBody`**. Options:

- For simple rules, validate transparently in the handler/service (like the demo's non-blank `title` and max length).
- For complex rules, inject `jakarta.validation.Validator` or Spring `org.springframework.validation.Validator` and map violations to a stable error response.
- For form/query binding, check `ServerRequest.bind(...)` and `DataBinder` to restrict fields.

A snippet using Jakarta Bean Validation (requires starter-validation and a validator bean):

```java
Set<ConstraintViolation<CreateNote>> violations =
        validator.validate(input);

if (!violations.isEmpty()) {
    return ServerResponse.badRequest()
            .contentType(MediaType.APPLICATION_JSON)
            .body(Map.of("error", "validation_failed"));
}
```

This is an illustrative snippet, lacking sufficient classes/imports to run standalone. In a real application, aggregate violations into localizable field/constraint messages without returning raw sensitive values.

### 8.2. Body parse errors and business errors differ

| Scenario | Reasonable Handling |
| --- | --- |
| Malformed JSON syntax | 400 if MVC converter/handler mapping handles it per error policy |
| Valid JSON syntax but blank title field | 400 with error code `title_required` |
| Path ID fails long parsing | 400 with error code `invalid_id` |
| Valid ID but not found | 404 |
| Conflict because resource already exists | 409 if contract specifies |
| Unsupported Content-Type | 415 if Framework/converter contract applies |
| User logged in but lacks permission | 403 via Spring Security |
| DB/remote service error | 5xx with structured error, no stack trace leak |

In annotated MVC, `@ExceptionHandler`/`@ControllerAdvice` integrates familiarly with controller methods. With functional endpoints, **test in practice** how exceptions pass through `HandlerFunctionAdapter` and MVC exception resolvers; if you want to handle all domain errors across a route group, `HandlerFilterFunction` can catch domain exceptions and build the corresponding `ServerResponse`. Do not assume annotation-based binding errors and all handler advice apply 100% automatically in the same way.

### 8.3. Transaction boundaries

Routers/handlers do not replace the service layer. Example saving a note to the DB:

```java
@Service
class NoteService {
    @Transactional
    public Note create(CreateNote command) {
        // validate ownership, convert DTO, persist through repository
        // and return saved object
    }
}
```

The illustrative snippet omits model/repository and is not standalone. In a real project, transactional service methods must be invoked through the proper Spring proxy, and resource validations/authorization must still execute on writes.

### 8.4. OpenAPI, observability, and filters

Some tools detect annotated controllers more deeply than functional endpoints. When using OpenAPI generators/documentation plugins, verify whether your version supports `RouterFunction`/functional routes, or add explicit docs declarations. Instrumentation/logging usually still works through the Servlet Filter/Spring MVC chain, though custom metrics need to identify the matched route/handler properly.

## 9. Security, Caching, and HTTP Semantics

WebMvc.fn **does not automatically provide authentication, authorization, CSRF, or session management**. It shares the Servlet security/filter chain with Spring MVC.

- **Authentication:** who is the user? Based on valid Spring Security/OIDC/Session/Bearer tokens.
- **Authorization:** does the user have permission to read/modify the note with that specific ID and tenant?
- **CSRF:** state-changing methods when browsers use cookies/ambient credentials require a proper policy.
- **CORS:** which origins' JavaScript can read responses? The WebMvc.fn reference recommends a dedicated `CorsFilter` for functional endpoints when needed.
- **Validation:** do not copy arbitrary DTOs into entities; prevent mass assignment.
- **Caching:** GET can use ETag/Cache-Control when representations fit; 304 does not automatically skip DB queries if validation happens late.
- **Idempotency:** GET is safe; DELETE/PUT carry appropriate idempotent semantics; POST creates can produce duplicates on retry, requiring a business idempotency key if needed.
- **Content negotiation:** `Accept` and `Content-Type` are distinct headers; test preflight/CORS and converters if the API is called from browsers.

### 9.1. Do not expose unauthenticated mutation endpoints in production

The demo intentionally allows POST/DELETE to focus on ServerRequest/ServerResponse; in a real application, add Spring Security, per-resource/tenant authorization checks, and CSRF where appropriate. Do not deploy the demo directly to the internet as a production API without these controls.

### 9.2. CORS errors are not routing errors

If a browser reports a CORS error, do not rush to change `RouterFunction.GET(...)`. Check `OPTIONS` preflight, allowed origins/methods/headers, and Spring Security filter order. Non-browser HTTP clients can still call the route even when browser JavaScript cannot read the response; CORS does not replace authentication.

### 9.3. Do not blindly let the client decide ID/owner

When a POST body sends:

```json
{"title":"My note","ownerId":"other-user","role":"ADMIN"}
```

If the handler only uses `CreateNote(String title)`, fields outside the contract must not be used to set ownership/privileges. In production, define a policy for unknown JSON properties, and obtain the owner's identity from a trusted principal, not from the body.

## 10. Complete Demo: Spring Boot 3, Java 17, Functional CRUD

The small application has:

- `GET /api/notes`: list Notes sorted by ID.
- `GET /api/notes/search?q=Spring`: search by title; `search` route placed before `{id}`.
- `GET /api/notes/{id}`: return a note or 400/404.
- `POST /api/notes`: accept JSON `{"title":"..."}`, validate, return 201 + Location.
- `DELETE /api/notes/{id}`: delete, return 204 or 404.
- `HandlerFilterFunction` checking a **demo header** and possibly returning 429 (not a security control).
- `GET /annotated/ping` using `@RestController` to prove both styles run together in one application.

Uses Spring Boot **3.3.13**, Java **17+**, and Maven. The data store uses `ConcurrentHashMap` and `AtomicLong` to avoid needing a DB install; data is lost when the application restarts.

### 10.1. Project Structure

```text
webmvc-fn-demo/
├── pom.xml
└── src/
    ├── main/java/example/FnMvcApplication.java
    └── test/java/example/FnMvcApplicationTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>webmvc-fn-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 10.3. FnMvcApplication.java

All the code below resides in one file. Only the main class is a public top-level class; the DTO records are public nested types, making it easy for Jackson to read/write them. `NoteHandlers` and `RouteConfig` are package-private classes discovered by Spring component scanning.

```java
package example;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@SpringBootApplication
public class FnMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(FnMvcApplication.class, args);
    }

    public record Note(long id, String title) {}
    public record CreateNote(String title) {}
}

@Configuration
class RouteConfig {

    @Bean
    RouterFunction<ServerResponse> noteRoutes(NoteHandlers handler) {
        return RouterFunctions.route()
            // Specific first; /search is not captured by the /{id} route.
            .GET("/api/notes/search", handler::search)
            .GET("/api/notes/{id}", handler::get)
            .GET("/api/notes", handler::list)
            .POST("/api/notes", handler::create)
            .DELETE("/api/notes/{id}", handler::delete)
            .filter((request, next) -> {
                // Only to learn the short-circuit mechanism,
                // DO NOT use this header for security.
                String mode = request.headers()
                        .firstHeader("X-Demo-Flow");
                if ("reject".equals(mode)) {
                    return ServerResponse.status(
                            HttpStatus.TOO_MANY_REQUESTS)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("error", "demo_filtered"));
                }
                return next.handle(request);
            })
            .build();
    }
}

@Component
class NoteHandlers {

    private final Map<Long, FnMvcApplication.Note> notes =
            new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(2);

    NoteHandlers() {
        notes.put(1L, new FnMvcApplication.Note(1L, "Spring MVC"));
    }

    ServerResponse list(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(sortedNotes(""));
    }

    ServerResponse search(ServerRequest request) {
        String q = request.queryParam("q")
                .orElse("")
                .trim()
                .toLowerCase(Locale.ROOT);

        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(sortedNotes(q));
    }

    private List<FnMvcApplication.Note> sortedNotes(String query) {
        return notes.values().stream()
                .filter(note -> note.title()
                        .toLowerCase(Locale.ROOT).contains(query))
                .sorted(Comparator.comparingLong(
                        FnMvcApplication.Note::id))
                .toList();
    }

    ServerResponse get(ServerRequest request) {
        Long id = parseId(request);
        if (id == null) {
            return badId();
        }

        FnMvcApplication.Note note = notes.get(id);
        if (note == null) {
            return ServerResponse.notFound().build();
        }
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }

    ServerResponse create(ServerRequest request) throws Exception {
        FnMvcApplication.CreateNote command =
                request.body(FnMvcApplication.CreateNote.class);

        if (command == null || command.title() == null ||
                command.title().isBlank()) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("error", "title_required"));
        }

        String title = command.title().trim();
        if (title.length() > 120) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("error", "title_too_long"));
        }

        long id = nextId.getAndIncrement();
        FnMvcApplication.Note note =
                new FnMvcApplication.Note(id, title);
        notes.put(id, note);

        return ServerResponse.created(
                    URI.create("/api/notes/" + id))
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }

    ServerResponse delete(ServerRequest request) {
        Long id = parseId(request);
        if (id == null) {
            return badId();
        }

        FnMvcApplication.Note removed = notes.remove(id);
        return removed != null
                ? ServerResponse.noContent().build()
                : ServerResponse.notFound().build();
    }

    private Long parseId(ServerRequest request) {
        try {
            return Long.valueOf(request.pathVariable("id"));
        } catch (NumberFormatException ex) {
            return null;
        }
    }

    private ServerResponse badId() {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("error", "invalid_id"));
    }
}

@RestController
class PingController {
    @GetMapping("/annotated/ping")
    Map<String, String> ping() {
        return Map.of("style", "annotated");
    }
}
```

#### Explanation of Each Role

**FnMvcApplication:** boots Spring Boot and defines the two Java records. `Note` is the response DTO; `CreateNote` is the request DTO accepting only title at the handler layer.

**RouteConfig:** the `noteRoutes` bean is the entrypoint registering functional endpoints. Spring auto-detects the bean without manually instantiating `RouterFunctionMapping`. The static `/search` route comes before the variable `/{id}` route. `HandlerFilterFunction` at the end of the builder applies to routes belonging to this builder; the demo header only proves the filter can skip calling next.

**NoteHandlers:** holds the simple business logic of each route. It reads `ServerRequest`, parses query/path/body, and returns `ServerResponse` with clear status and content type. `ConcurrentHashMap` ensures basic map operations are safe under concurrent requests, but **does not** replace database transactions, multi-tenant policies, or POST idempotency.

**PingController:** demonstrates that annotated style and functional style share DispatcherServlet. Neither registers handlers on the same URL to avoid an off-topic precedence issue.

### 10.4. Running the Application

In the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Requires Maven/JDK 17+ and network access to download dependencies if they are not already in the local repository.

GET requests:

```bash
curl -i http://localhost:8080/api/notes
curl -i http://localhost:8080/api/notes/1
curl -i "http://localhost:8080/api/notes/search?q=Spring"
curl -i http://localhost:8080/annotated/ping
```

Expected JSON bodies in the freshly started state:

```json
[{"id":1,"title":"Spring MVC"}]
```

GET ID 1:

```json
{"id":1,"title":"Spring MVC"}
```

Search:

```json
[{"id":1,"title":"Spring MVC"}]
```

Annotated ping:

```json
{"style":"annotated"}
```

Create:

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title":"WebMvc.fn"}'
```

Expected result on a freshly started app with no prior POSTs: status 201, header `Location: /api/notes/2`, and body:

```json
{"id":2,"title":"WebMvc.fn"}
```

If there are multiple POSTs, the ID number increments; **do not** hardcode ID 2 in a production client. Use the actual Location returned by the server.

Bad request:

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title":"   "}'
```

Expected HTTP 400 with JSON:

```json
{"error":"title_required"}
```

Delete:

```bash
curl -i -X DELETE http://localhost:8080/api/notes/2
```

Expected 204 if ID 2 exists on the running server. Afterwards `GET /api/notes/2` returns 404. Because the demo has no database, restarting the app brings back seeded ID 1.

Filter demo:

```bash
curl -i http://localhost:8080/api/notes \
  -H "X-Demo-Flow: reject"
```

Expected status 429 and:

```json
{"error":"demo_filtered"}
```

This is a **middleware demonstration**; a client-supplied header has no security meaning. The cURL commands use POSIX shell line continuation; on Windows PowerShell, use `curl.exe` and corresponding line continuation.

## 11. MockMvc: Truly Testing Functional Routes

Use the Spring Boot test context because `@SpringBootTest` loads `RouterFunctionMapping`, `HandlerFunctionAdapter`, handlers, and converters. `@AutoConfigureMockMvc` lets you invoke MVC without opening a network port. Each test asserts only the necessary contract without relying on JSON key order.

File `src/test/java/example/FnMvcApplicationTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FnMvcApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void seededNoteCanBeRead() throws Exception {
        mvc.perform(get("/api/notes/1"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.title").value("Spring MVC"));
    }

    @Test
    void listContainsSeededNote() throws Exception {
        mvc.perform(get("/api/notes"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value(1));
    }

    @Test
    void specificSearchRoutePrecedesIdVariable() throws Exception {
        mvc.perform(get("/api/notes/search")
                    .param("q", "spring"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].title").value("Spring MVC"));
    }

    @Test
    void invalidPathIdGives400() throws Exception {
        mvc.perform(get("/api/notes/not-a-number"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_id"));
    }

    @Test
    void unknownIdGives404() throws Exception {
        mvc.perform(get("/api/notes/999999"))
            .andExpect(status().isNotFound());
    }

    @Test
    void createReturns201LocationAndReadableResource()
            throws Exception {
        MvcResult created = mvc.perform(post("/api/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"A new note\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    HttpHeaders.LOCATION,
                    startsWith("/api/notes/")))
            .andExpect(jsonPath("$.title").value("A new note"))
            .andReturn();

        String location = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);

        mvc.perform(get(location))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("A new note"));
    }

    @Test
    void blankTitleIsRejected() throws Exception {
        mvc.perform(post("/api/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"  \"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error")
                    .value("title_required"));
    }

    @Test
    void functionalFilterCanShortCircuit() throws Exception {
        mvc.perform(get("/api/notes")
                    .header("X-Demo-Flow", "reject"))
            .andExpect(status().isTooManyRequests())
            .andExpect(jsonPath("$.error").value("demo_filtered"));
    }

    @Test
    void annotatedAndFunctionalHandlersCoexist() throws Exception {
        mvc.perform(get("/annotated/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.style").value("annotated"));
    }
}
```

The tests do not assume the new ID is always 2; the create case reads `Location` from the response and then GETs the new resource. The list test only asserts that the seeded note is first because the list is sorted by ID. If integrating test parallelization or real stateful persistence, explicit data isolation/cleanup is required.

**Route order testing is critical:** `/api/notes/search` must match its explicit route before `/api/notes/{id}`; if the order is reversed, the get handler could try to parse `search` as a number and return 400, causing the search test to fail.

### 11.1. Adding a DELETE Test

To verify 204 and 404 after deletion without relying on the seeded resource:

```java
@Test
void deleteCreatedNote() throws Exception {
    MvcResult created = mvc.perform(post("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"title\":\"Delete me\"}"))
        .andExpect(status().isCreated())
        .andReturn();

    String url = created.getResponse()
            .getHeader(HttpHeaders.LOCATION);

    mvc.perform(delete(url))
        .andExpect(status().isNoContent());

    mvc.perform(get(url))
        .andExpect(status().isNotFound());
}
```

Place this method in the test class above so the declared imports are all present. The suite then has **10 tests**. The main application already supports the DELETE route.

### 11.2. What can MockMvc test, and what can it not?

MockMvc verifies route registration/selection, HTTP converters, response status/body, and composition under Spring MVC. It does not fully simulate TLS, reverse proxies, actual Servlet container network buffering, connection timeouts, or browser CORS enforcement.

For production applications, add integration tests running an embedded server on a random port to test forwarded headers, network statuses, caching, cookies, filter mappings, and real Spring Security.

## 12. Debugging WebMvc.fn Layer by Layer

### 12.1. Route does not match

Scenario:

```text
GET /api/notes/search → 400 invalid_id
```

Common cause: `GET /api/notes/{id}` comes before the `search` route. Fix by placing specific routes first. Do not guess that Spring will automatically choose the most specific route like in annotated RequestMapping.

### 12.2. Wrong WebFlux import chosen

If the IDE auto-imports:

```java
org.springframework.web.reactive.function.server.ServerRequest
```

then your code is using the reactive type, which is incompatible with `org.springframework.web.servlet.function.RouterFunction`. Fix the packages consistently for WebMvc.fn; do not inject `Mono<ServerResponse>` into a synchronous handler method and expect it to compile.

### 12.3. JSON body cannot be read

Checklist:

1. Does `spring-boot-starter-web` have the appropriate Jackson JSON converter?
2. Did the client send `Content-Type: application/json`?
3. Does the JSON body match valid syntax and the DTO schema?
4. Does the record/class have constructors/accessors for the converter to instantiate the object?
5. Did the handler read the body once, or was the stream already consumed earlier?
6. When binding fails, does the server convert the exception into an error response with a clear code?

### 12.4. Functional filter causes unexpected 429

If the filter is on the root builder, every route built from that builder can be affected by that filter. Check the predicate/header and scope. To apply it to a subgroup, place a nested builder/filter in the right location instead of filtering too broadly at the root.

### 12.5. CORS or 401/403 appears

These can come from Servlet/Spring Security layers before the handler runs. Do not modify routes to "bypass" security. Inspect CORS preflight, authentication, roles/ownership, and CSRF along the configured filter chain.

### 12.6. URL returns 404 from static ResourceHandler

In Spring Boot, the static resource handler can match the `/**` wildcard after no controller/functional route matches. Thus 404 can mean "resource not found" rather than "no handler matched," depending on configuration. Debug by the selected HandlerMapping, not just the HTTP status.

### 12.7. Response lacks Content-Type JSON

Returning a Map/object without setting a content type can leave the message converter to pick a default via Accept negotiation; to keep the demo API predictable, we use `.contentType(MediaType.APPLICATION_JSON)` on JSON responses. For a real application, design Accept/produces behavior explicitly.

### 12.8. Performance does not improve after switching from @RestController

WebMvc.fn is a way of **expressing routing/handling**; it does not guarantee faster queries, non-blocking DB calls, or significantly fewer object allocations. Profile DB latency, serialization, request concurrency, CPU, and garbage collection before deciding to refactor.

## 13. Common Mistakes and How to Avoid Them

| Misconception | Consequence | Right Approach |
| --- | --- | --- |
| "WebMvc.fn is WebFlux.fn" | Wrong imports, expecting Mono/Flux | Use Servlet packages for WebMvc.fn |
| "HandlerFunction selects the URL itself" | Missing routing bean, 404 endpoints | Register a RouterFunction bean |
| "RouterFunction is a controller method" | Confusing routing with handling | Router picks handler; handler builds response |
| "ServerRequest is identical to HttpServletRequest" | Ignoring wrapper/convenience APIs | Use ServerRequest, drop to servletRequest only when needed |
| "ServerResponse is like mutable HttpServletResponse" | Mutating against the contract | Use the immutable-style builder |
| "GET /{id} after /search still prioritizes search automatically" | Search parsed as ID | Put specific routes first in RouterFunction |
| "Using a body DTO automatically runs @Valid" | Invalid data reaches the service | Run explicit validation |
| "Trust ownerId if the client provides it" | Mass assignment/IDOR | Derive ownership from authenticated context |
| "Middleware filter is Spring Security" | Missing auth/CSRF | Use SecurityFilterChain |
| "Adding a root route filter only affects the nearest route" | Filter unintentionally applies to whole group | Understand builder/nesting scope |
| "404 always means RouterFunctionMapping failed to match" | Debugging the wrong layer | Check HandlerMapping/static fallback |
| "201 does not need Location" | Client struggles to locate new resource | Return Location when appropriate |
| "Returning 204 can still include a JSON body" | Broken HTTP semantics | Truly no content |
| "POST can be retried freely" | Can create duplicates | Idempotency key/logic if needed |
| "Functional style solves error handling by itself" | Leaked stack traces/unstructured errors | Define error contract and test |
| "Functional API is end-to-end non-blocking" | Wrong capacity plan | Servlet stack still has blocking I/O |
| "@ControllerAdvice applies 100% like @RequestBody" | Validation/advice behaves unexpectedly | Test actual adapter/converter/error flow |
| "A route filter returning 429 on a demo header is real rate limiting" | Broken security policy | Use a real rate limiter with identity/trust boundaries |
| "Having ConcurrentHashMap means having transactions" | Business race/not persistent | DB transactions, optimistic locking |
| "Tests hardcode new ID = 2" | Flaky under test ordering or concurrency | Read Location/ID from response |
| "Testing JSON bodies via exact string equality" | Pointless failures from key order | Use jsonPath/structural JSON assertions |
| "CORS OK means user is allowed to POST" | Confusing browser policy with authorization | Separate CORS, auth, role, and CSRF |

## 14. Practical Adoption Checklist

When starting a WebMvc.fn module:

1. **Choose the stack:** confirm whether it is Servlet MVC or reactive WebFlux, keeping imports consistent.
2. **Router structure:** group routes by domain, with transparent path/method/media predicates.
3. **Precedence:** place specific routes before broad wildcard/path-variable routes.
4. **Handler functions:** keep them small; only read the request, validate, call the service, and build the response.
5. **DTO schema:** separate request/response DTOs from JPA entities; prevent mass assignment.
6. **HTTP status:** GET 200/404, POST 201+Location, DELETE 204, validation 400, and clear policy errors.
7. **Business service:** transactions, optimistic concurrency, ownership checks, multi-tenant isolation.
8. **Security:** CORS/Csrf/Spring Security filters, method/object authorization, and private cache policies.
9. **Error mapping:** standardize JSON error codes, avoid stack trace leaks; test body parse/converter errors.
10. **Cross-cutting:** distinguish HandlerFilterFunction from Servlet Filters/MVC interceptors.
11. **Composition:** avoid multiple RouterFunction beans with overlapping paths without clear ordering.
12. **Concurrency:** check thread-safety and resource exhaustion if handlers call blocking services.
13. **Testing:** test static-vs-variable routes, 201/Location, 400, 404, 204, and functional middleware.
14. **Observability:** log matched route, request ID, status, p95 latency, and security denials without exposing secrets.
15. **API docs:** check whether generator/OpenAPI tooling supports functional routes and add supplemental declarations if needed.

### 14.1. When should you choose WebMvc.fn?

Suitable when you want centralized route declarations, composable predicates, simple handler classes, middleware applied per group, or a codebase that favors functional style.

Not necessarily suitable if the whole team already uses annotated controllers, familiar validation/exception advice/tools, and switching styles only increases refactoring risk without clearly improving readability. **Spring supports both**, so a system can use each style in whichever module fits best.

## 15. Self-Check

**1.** What does `HandlerFunction<ServerResponse>` accept and return?  
**Answer:** accepts `ServerRequest` and returns `ServerResponse`.

**2.** What task does `RouterFunction` perform?  
**Answer:** selects the matching HandlerFunction by predicate/method/path, returning Optional when matched.

**3.** Does WebMvc.fn use Reactor Mono by default?  
**Answer:** no; Servlet `HandlerFunction` returns ServerResponse directly.

**4.** What is the ServerRequest package in WebMvc.fn?  
**Answer:** `org.springframework.web.servlet.function.ServerRequest`.

**5.** How do you retrieve an ID from a path variable?  
**Answer:** `request.pathVariable("id")`, then parse/validate as needed.

**6.** How do you retrieve query `?q=java`?  
**Answer:** `request.queryParam("q").orElse("")`.

**7.** How do you read JSON into a DTO?  
**Answer:** `request.body(CreateNote.class)` when supported by a converter.

**8.** How do you build a 201 response with Location?  
**Answer:** `ServerResponse.created(uri).body(object)`.

**9.** How do you return 204 with no body?  
**Answer:** `ServerResponse.noContent().build()`.

**10.** Why must the `/search` route come before `/{id}`?  
**Answer:** RouterFunction evaluates routes in order; first match wins.

**11.** What can RequestPredicates check besides the URL?  
**Answer:** HTTP method, Accept, Content-Type, and custom conditions.

**12.** How does `HandlerFilterFunction` differ from a Servlet Filter?  
**Answer:** it is RouterFunction middleware and does not have Servlet-container-wide scope.

**13.** Is using `HandlerFilterFunction` to trust `X-User-Role` from a client safe?  
**Answer:** no; authentication/authorization require trust boundaries and Spring Security.

**14.** Is a Java record with @NotBlank automatically validated when calling `request.body(...)`?  
**Answer:** not by default; you must trigger an appropriate Validator/binding.

**15.** Does a RouterFunction bean need @EnableWebMvc on Spring Boot?  
**Answer:** usually not; MVC auto-configuration supports it.

**16.** Can functional routes and @RestController coexist?  
**Answer:** yes on DispatcherServlet, though avoid uncontrolled overlapping URLs.

**17.** Why does `ConcurrentHashMap` not replace a DB transaction?  
**Answer:** the map only provides in-memory concurrent operations; it lacks durability and business transactions.

**18.** Which test verifies a functional route is not shadowed by `/{id}`?  
**Answer:** GET `/api/notes/search?q=Spring` must return the list successfully.

**19.** Does WebMvc.fn automatically make JDBC non-blocking?  
**Answer:** no; it is functional routing/handling on the Servlet stack.

**20.** Does a 404 response always mean no HandlerFunction matched?  
**Answer:** no; a handler itself may return 404, or the static fallback may report a missing resource.

## 16. Official References

- [Spring Framework 6.2 — Web MVC Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): WebMvc.fn model, RouterFunction, HandlerFunction, ServerRequest/Response, predicates, nesting/filtering.
- [Spring Framework 6.2 — Servlet Functional API package](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/function/package-summary.html): interfaces/builder classes.
- [Spring Framework 6.2 — RouterFunctionMapping Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/function/support/RouterFunctionMapping.html): detecting/combining RouterFunction beans.
- [Spring Framework 6.2 — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): comparing Servlet MVC with reactive API to avoid wrong imports.
- [Spring Framework 6.2 — Spring MVC Test Framework](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html): MockMvc testing.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC auto-configuration, Servlet stack.
- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110): status codes and request/response semantics.

**Key Takeaway:** `RouterFunction` decides **which route matches**; `HandlerFunction` performs **business/orchestration logic** on `ServerRequest`; `ServerResponse` represents **the HTTP result**. This trio is a **functional style on Spring MVC Servlet**, able to stand alongside annotated controllers and share Servlet/security infrastructure, while still requiring proper validation, authorization, error handling, tests, and data design.
