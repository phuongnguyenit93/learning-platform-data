# Integrating Functional Endpoints with Existing Spring MVC Infrastructure

## 1. Context and Objectives

A running Spring MVC application typically already has many components: `@RestController`, `@ControllerAdvice`, `HttpMessageConverter`, `WebMvcConfigurer`, Servlet filters, HandlerInterceptors, Spring Security, Jackson, Bean Validation, CORS, static resources, templates, tracing, and MockMvc tests. When adding a module written in the functional style, the question is not only "how do I declare a RouterFunction?" but also:

- Do functional endpoints share the same `DispatcherServlet` with annotated controllers?
- Can existing services, repositories, transactions, and dependency injection be reused?
- At which layer do JSON converters, locales, validation, CORS, interceptors, security, and logging operate?
- Are `@ControllerAdvice`, `@Valid`, `@InitBinder`, and `@ResponseBody` applied identically to functional handlers?
- Can both endpoint groups be declared side by side without route/HTTP status conflicts?
- How do you migrate step by step and test without breaking old API contracts?

**WebMvc.fn** is the functional HTTP endpoints model of the **Spring MVC Servlet stack**, package `org.springframework.web.servlet.function`. It provides `RouterFunction`, `HandlerFunction`, `ServerRequest`, and `ServerResponse`, while using the same `DispatcherServlet` infrastructure. It is **not WebFlux.fn** (package `org.springframework.web.reactive.function.server`) and does not automatically make HTTP/database I/O non-blocking.

This lesson uses **Java 17, Spring Boot 3.3.5, Spring Framework 6.1.x**, featuring a runnable Maven example with functional + annotated endpoints in the same application, sharing services and MVC configuration. It then analyzes the boundaries of converters, validation, errors, filters, CORS, Spring Security, versioning, and migration.

### What You Will Be Able to Do

1. Introduce `RouterFunction<ServerResponse>` into an existing MVC application without creating a second `DispatcherServlet`.
2. Run functional routes in parallel with `@RestController` on separate URLs.
3. Share Spring-managed `@Service`, DTOs, validators, Jackson converters, and transaction boundaries.
4. Apply shared MVC-level `HandlerInterceptor`/CORS and distinguish them from functional `filter`s.
5. Understand handler selection, route ordering, and overlapping mapping risks.
6. Design consistent error responses when argument resolution and validation differ between the two styles.
7. Protect Spring Security, CSRF, authorization, logging, and metrics independently of route style.
8. Write MockMvc tests for both endpoint types and verify real behavior.
9. Plan an incremental migration rather than rewriting everything merely to change syntax.

## 2. One DispatcherServlet, Multiple Handler Styles

Spring MVC is organized around `DispatcherServlet`. It receives HTTP requests from the Servlet container and queries registered `HandlerMapping` instances in turn to select a matching handler; a capable `HandlerAdapter` then invokes that handler.

Simplified diagram:

```text
HTTP client
     |
     v
Servlet container (Tomcat/Jetty/Undertow)
     |
     v
Servlet Filter chain (security, tracing, request policy)
     |
     v
DispatcherServlet
     |
     +---- RequestMappingHandlerMapping
     |        |
     |        v
     |    @RestController / @GetMapping / @PostMapping
     |        |
     |        v
     |    RequestMappingHandlerAdapter
     |    @RequestBody, @Valid, ResponseEntity...
     |
     +---- RouterFunctionMapping
     |        |
     |        v
     |    RouterFunction + RequestPredicate
     |        |
     |        v
     |    HandlerFunctionAdapter
     |    ServerRequest -> ServerResponse
     |
     +---- Static resource / other HandlerMappings
              |
              v
     HTTP status, headers, body -> Servlet response
```

With WebMvc.fn, Spring MVC uses components such as `RouterFunctionMapping` and `HandlerFunctionAdapter`. RouterFunctionMapping finds `RouterFunction<?>` beans in the application context, orders them, and combines them for routing. WebMvc.fn and annotated controllers can coexist in a single Boot Web application.

**Sharing infrastructure does not mean all method argument handling mechanisms are identical.** Both share the MVC foundation and message converters, yet a functional handler receives a single `ServerRequest` and reads the body/params itself, whereas an annotated controller has its Java parameters resolved by `RequestMappingHandlerAdapter` based on `@RequestParam`, `@PathVariable`, `@RequestBody`, `@Valid`, etc.

### No webflux-starter needed

An application having only:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

already includes Spring Web MVC and the required Servlet functional APIs. **Do not import by mistake** classes of the same name under `web.reactive.function.server`. Adding `spring-boot-starter-webflux` just to write WebMvc.fn is both unnecessary and a source of confusion for runtime/tests and reactive clients.

### Do not enable @EnableWebMvc arbitrarily in Spring Boot

Boot auto-configures MVC along with Jackson, static resources, and converter defaults. Manually adding `@EnableWebMvc` or extending `WebMvcConfigurationSupport` can disable or replace part of auto-configuration. To add interceptors, CORS, formatters, or resource handlers, usually start with `@Configuration implements WebMvcConfigurer` rather than building a second MVC stack.

## 3. Reusable Components and Applicability Boundaries

| Existing Component | Reusable by Functional Endpoints? | What Must Be Verified |
| --- | --- | --- |
| `DispatcherServlet` and Servlet runtime | **Yes** | Only one MVC application/context as usual |
| Spring `@Service` / `@Repository` / DI | **Yes** | Handler is a Spring bean, constructor-injected |
| `@Transactional` on services | **Yes** | Invoked via Spring proxy; transactions sit at service boundaries |
| Jackson / `HttpMessageConverter` | **Yes** | `request.body(Dto.class)` and `ServerResponse.body(dto)` use MVC converters |
| Servlet `Filter` / Spring Security chain | **Yes** | Matching URL/dispatcher types and filter chain ordering |
| MVC `HandlerInterceptor` | Can apply via MVC HandlerMapping config | Test filter/interceptor mappings and request lifecycle |
| `WebMvcConfigurer.addCorsMappings` | Configures CORS per HandlerMapping | Test preflight and Origin with functional URLs |
| `@Valid @RequestBody` method argument magic | **Does not auto-apply to HandlerFunction like a controller method** | Functional needs explicit validator/binding |
| `@InitBinder` / `@ModelAttribute` method arguments | **Do not auto-apply the same way** | Use `ServerRequest` APIs or custom binding |
| `@ControllerAdvice` / `@ExceptionHandler` | Not guaranteed to handle all functional errors identically | Test each error, use appropriate error boundaries |
| `ResponseBodyAdvice` for controller methods | Do not assume it transforms every functional ServerResponse | Test the actual converter/adapter path |
| Router-level `filter` | Only for that router/functional group | Does not automatically wrap annotated controllers |
| `@CrossOrigin` on annotated methods | Metadata for annotated handlers only | Use global/filter CORS suitable for functional routes |
| `@PreAuthorize` on service methods | Yes when Spring method security is enabled and invoked via proxy | Do not rely on controller method annotations over full filter-chain auth |
| OpenAPI generators/Actuator/tracing | Depends on integration/version | Verify docs, operation IDs, metric tags, links |

**Architectural rule:** reuse components **below routing** (services, repositories, transactions) and components **before DispatcherServlet** (Servlet Filters/security). For features tied directly to `HandlerMethod` or annotation metadata, test them or switch to explicit mechanisms for functional handlers.

## 4. Sharing Services and DTOs, Swapping Only the HTTP Adapter

A stable design:

```text
                      Shared Spring Context
  +------------------------------------------------+
  | DTOs + Bean Validation                         |
  | NoteService (@Service, @Transactional if needed) |
  | NoteRepository                                 |
  +------------------------------------------------+
             ^                            ^
             |                            |
  +---------------------+    +------------------------+
  | Annotated adapter   |    | Functional adapter     |
  | @RestController     |    | RouterFunction @Bean   |
  | @RequestBody @Valid |    | HandlerFunction        |
  | ResponseEntity      |    | ServerRequest/Response |
  +---------------------+    +------------------------+
             |                            |
             +---------- HTTP ------------+
```

For example, both REST styles need "create note":

- The annotated controller has `@PostMapping` and parameter `@Valid @RequestBody NewNote input`.
- The functional handler calls `NewNote input = request.body(NewNote.class)`, then explicitly calls `validator.validate(input)`.
- Both call `NoteStore.create(input.title())` (or a `NoteService` in a real system).
- Both return HTTP `201 Created`, the `Location` header, and the `Note` JSON DTO.

**Do not duplicate business rules across both handlers**. When a `@Service` already holds authorization, transactions, idempotency, and invariants, keep it as the single source of logic. Functional/annotated layers should only handle differences at the HTTP boundary.

## 5. Route Discovery, Ordering, and Avoiding Conflicts

### 5.1. WebMvc.fn uses matching order

Example:

```java
RouterFunction<ServerResponse> router = route()
        .GET("/api/fn/notes/latest", handler::latest)
        .GET("/api/fn/notes/search", handler::search)
        .GET("/api/fn/notes/{id}", handler::find)
        .build();
```

This is a **snippet** (requiring handler bean/imports). Literal routes `latest` and `search` are placed **before** `/{id}`. If `/{id}` matched first, it could receive `id="latest"` and fail numeric parsing in the handler. With annotated controllers, Spring ranks `@RequestMapping` by specificity; functional route traversal depends on **order**.

### 5.2. Both styles should have clear namespaces

During experimentation, you can set:

- `/api/annotated/notes/**` for the existing annotated API.
- `/api/fn/notes/**` for the functional version developed in parallel.

In a real migration, you do not have to keep both public prefixes; you can migrate **route by route** at controlled boundaries. Avoid declaring **the exact same HTTP method + path** simultaneously on both a RouterFunction and a `@RestController` hoping the framework "picks the right one" by Java source order. HandlerMapping precedence depends on configuration/framework, not a contract to rely on for rollout.

To compare two implementations before swapping an endpoint, you can:

1. Use separate/staging URLs to run contract tests.
2. Put traffic splitting at the gateway under controlled, observable rules.
3. Switch one route at a time once the functional handler passes contract and security checks.
4. Remove the old mapping once migration completes.

### 5.3. Multiple RouterFunction beans

`RouterFunctionMapping` can discover multiple RouterFunction beans and combine them in order. By module:

```java
@Bean
RouterFunction<ServerResponse> catalogRoutes(CatalogHandler handler) {
    return route()
            .GET("/api/catalog", handler::list)
            .build();
}

@Bean
RouterFunction<ServerResponse> billingRoutes(BillingHandler handler) {
    return route()
            .GET("/api/billing", handler::summary)
            .build();
}
```

These are **snippets** assuming the respective handlers exist. When prefixes are completely disjoint, order is less risky. When route patterns overlap (catch-alls, path variables), enforce deliberate bean/order configuration and tests; never rely on alphabetical/class names.

## 6. @Bean RouterFunction Inside @Configuration

Minimal style:

```java
@Configuration
class FunctionalNotesConfiguration {

    @Bean
    RouterFunction<ServerResponse> notesRoutes(NoteHandler handler) {
        return route()
                .GET("/api/fn/notes", handler::list)
                .build();
    }
}
```

This is a snippet; `NoteHandler`/static `route()` are defined in the full example in section 11. Spring Boot scans `@Configuration` and creates the `RouterFunction` bean at startup; MVC detects it and serves HTTP requests. Neither `@RestController` on `NoteHandler` nor a separate DispatcherServlet/Servlet registration is needed.

**Important:** RouterFunctions builders are normally built at startup; do not keep a mutable builder and append routes per request. Handlers injected from Spring beans are usually singletons and reused, so do not store `ServerRequest` or user data in mutable instance fields on handlers.

## 7. Shared MVC HttpMessageConverters, Different Invocation Style

A standard Spring Boot setup has a Jackson converter reading/writing JSON.

Annotated:

```java
@PostMapping(
        path = "/api/annotated/notes",
        consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<Note> create(
        @Valid @RequestBody NewNote body) {
    // ...
}
```

Functional:

```java
public ServerResponse create(ServerRequest request) throws Exception {
    NewNote body = request.body(NewNote.class);
    // validate body then call service
    return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(result);
}
```

Both can use the same Jackson configuration, yet:

- Annotated `@RequestBody` is invoked by an MVC argument resolver before the controller.
- Functional handlers **explicitly** call `request.body(NewNote.class)`. For malformed JSON, the error can arise **inside the handler** and take a different error-handling path.
- Annotated `@ResponseBody`/`ResponseEntity` is processed by the handler adapter; functional `ServerResponse` writes the HTTP body via `ServerResponse.writeTo` and converters.
- Sharing the converter does not mean every `RequestBodyAdvice`/`ResponseBodyAdvice` tied to the annotated method pipeline automatically runs for functional ServerResponse.
- Both require accurate content-type/Accept negotiation; functional routes can use the `contentType(MediaType.APPLICATION_JSON)` predicate.

**Be careful with custom converters:** if a team misuses `WebMvcConfigurer.configureMessageConverters(...)`, it can replace all default converters instead of extending them, breaking JSON routes. Usually use `extendMessageConverters` or Boot Jackson customizers for small adjustments. After changing converters, test **both** request/response styles.

### Generic types

For functional handlers needing to deserialize a JSON array of DTOs:

```java
List<NewNote> notes = request.body(
    new ParameterizedTypeReference<List<NewNote>>() {});
```

This is a snippet requiring `org.springframework.core.ParameterizedTypeReference` and `java.util.List` imports. The generic type token tells the converter the element type instead of `List.class` (which can produce Maps instead of DTOs). Ensure converters support the media type and body content.

## 8. Validation: Reusing Validator, Not Expecting @Valid to Auto-Run

DTO record:

```java
public record NewNote(
        @NotBlank
        @Size(max = 80)
        String title) {}
```

Annotated method:

```java
public ResponseEntity<Note> create(
        @Valid @RequestBody NewNote input) {
    // Spring MVC triggers Bean Validation via annotated pipeline
}
```

Functional handler:

```java
NewNote input = request.body(NewNote.class);
Set<ConstraintViolation<NewNote>> violations =
        validator.validate(input);

if (!violations.isEmpty()) {
    return ServerResponse.badRequest()
            .body(new ApiError("invalid_note"));
}
```

**The difference lies in triggering validation**. The same Jakarta Validator bean can be injected via constructor, yet `HandlerFunction.handle(ServerRequest)` has no `@Valid @RequestBody` method argument for Spring to process automatically like an annotated handler. When using functional style, write a consistent helper to:

1. Read the JSON body and recognize malformed bodies.
2. Check Bean Validation constraints.
3. Map violations to stable error codes/schemas.
4. Never leak exception stack traces or sensitive values.
5. Distinguish 400 (bad request) from 403 (not authorized), 404 (not found), 409 (conflict), and 500 (server fault).

For complex form binding, multipart uploads, request params, or constructor binding, annotated controllers generally offer richer automatic binding features; functional handlers must be designed explicitly when those APIs are needed.

## 9. Error Handling: Consistent Contract Without Identical Pipelines

An annotated endpoint can throw `MethodArgumentNotValidException` when `@Valid` fails. A functional endpoint can explicitly return `ServerResponse.badRequest().body(new ApiError(...))` or catch conversion exceptions of the right type. Both can return HTTP 400, yet **with different body formats**.

Points to verify:

| Error | Typical Annotated MVC | Functional MVC Must Actively Test |
| --- | --- | --- |
| Invalid JSON | Resolver/converter may throw `HttpMessageNotReadableException` | `request.body(...)` may throw inside HandlerFunction |
| DTO violates @NotBlank | `@Valid` method argument pipeline | Explicit Validator or custom binding |
| `id=abc` when long is expected | MVC type conversion exception | `Long.parseLong`/conversion called by handler |
| Missing required query param | `@RequestParam(required=true)` | `request.param(...)` Optional then validate |
| Unsupported media type | `consumes` mapping/converter | `contentType` predicate and converter; status may differ |
| Business conflict | Service exception/response | Same service; adapter mapping must stay compatible |
| Security rejection | Spring Security filter chain | Still Spring Security filter chain, not bypassed |
| Serialization error | MVC return-value handling | `ServerResponse` body writing; test behavior |

### Does @ControllerAdvice automatically handle all functional errors?

**Do not assume so.** Certain exception resolvers can handle exceptions in both flows, yet `@ExceptionHandler` is often tied to the `HandlerMethod` concept of annotated controllers. Functional handlers may not follow the exact annotation-based error resolution path. Do the following:

- Use **router-level `onError`/filters** matching your version's API when defining an error policy for functional routes.
- Use explicit error-to-`ServerResponse` helpers for handler-managed conversion/validation.
- Verify global `HandlerExceptionResolver` and `ProblemDetail` responses with MockMvc.
- Never catch `Exception` and always return 400, as it hides real 500s.
- If the backend standardizes on RFC 9457 Problem Details, test `type`, `title`, `status`, and `detail` fields for both styles instead of checking HTTP status alone.

### Functional error boundaries are a different layer from controller advice

A middleware/router filter can short-circuit or intercept exceptions:

```java
.filter((request, next) -> {
    try {
        return next.handle(request);
    } catch (IllegalArgumentException ex) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ApiError("bad_parameter"));
    }
})
```

This snippet is illustrative only; catch `IllegalArgumentException` **only if** domain policy treats that exception as bad input. Avoid overly broad exception types for unrelated failure modes. Note that body serialization errors can happen **after** the handler creates `ServerResponse`, so a filter wrapping `next.handle()` will not necessarily catch errors occurring while the body is written.

## 10. MVC Interceptor, Servlet Filter, Functional Filter, Security

There are at least three kinds of interception whose names easily cause confusion.

| Layer | Example API | Scope |
| --- | --- | --- |
| Servlet filter | `jakarta.servlet.Filter`, Spring `OncePerRequestFilter` | Before DispatcherServlet, depends on URL/dispatcher mappings |
| MVC interceptor | `HandlerInterceptor` + `WebMvcConfigurer.addInterceptors` | MVC HandlerMappings configured to use interceptors |
| Functional filter | `RouterFunctions.Builder.filter` | Only routes built by that RouterFunction builder/group |
| Spring Security | `SecurityFilterChain` in Servlet filters | Protects HTTP requests per security matcher rules |

### 10.1. Sharing an MVC interceptor

An app that already has MVC correlation header, locale, or metrics interceptors can continue registering them:

```java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(new HandlerInterceptor() {
        @Override
        public boolean preHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler) {
            response.setHeader("X-MVC-Pipeline", "active");
            return true;
        }
    }).addPathPatterns("/api/**");
}
```

This is an illustrative snippet; the runnable class is in section 11. Actual effect must be tested against the HandlerMappings used in your Spring/Boot version, especially if the application registers custom HandlerMappings. Spring MVC Java configuration normally supplies interceptors to mappings it manages.

**Important note:** Interceptors are not the optimal place for authorization due to potential mapping differences/mismatches; Spring docs recommend Spring Security or Servlet filter chains for security. Correlation/observability fits better, though ASYNC redispatch must still be handled when async endpoints exist.

### 10.2. Functional filters wrap only functional routes

Example:

```java
RouterFunction<ServerResponse> router = route()
        .GET("/api/fn/notes", handler::list)
        .filter((request, next) -> {
            if ("true".equals(
                    request.headers().firstHeader("X-Demo-Block"))) {
                return ServerResponse.status(HttpStatus.FORBIDDEN)
                        .body(new ApiError("demo_blocked"));
            }
            return next.handle(request);
        })
        .build();
```

Educational snippet; **do not use the `X-Demo-Block` header as an authorization system**. When a request goes to an annotated URL, this functional filter does not run automatically because the request is not handled by that RouterFunction. Conversely, the Servlet Security filter chain applies according to app-wide SecurityFilterChain matchers.

### 10.3. Security FilterChain for both styles

If the application uses Spring Security:

- `/api/fn/**` and `/api/annotated/**` requests need identical or equivalent security matcher policies.
- The filter chain handles authentication, authorization, CSRF, CORS integration, and exception entry points **before DispatcherServlet**.
- `@PreAuthorize` on shared service methods can protect the business layer when method security is enabled and calls go through a proxy; do not rely solely on route matchers.
- When using session/cookie auth, functional POSTs remain subject to CSRF protection when enabled. Never disable CSRF just because a functional route does not use `@PostMapping`.
- When authorizing by tenant/resource, enforce permissions in the service after resolving the resource ID, not solely by checking URL prefixes.
- Functional filters for auditing/transformation do not replace the standard security filter chain.

**Security model:** The chosen handler can vary by routing style, yet user identity and access permissions must be enforced consistently at request and service boundaries.

## 11. Runnable Maven Project: Functional + Annotated + Shared MVC Infrastructure

The following demo runs **a single Spring Boot MVC application** with:

1. `POST /api/fn/notes`, `GET /api/fn/notes`, `GET /api/fn/notes/{id}`, `GET /api/fn/notes/latest`, and `GET /api/fn/notes/search?q=...`.
2. Annotated equivalents at `/api/annotated/notes`.
3. A shared singleton in-memory `NoteStore`, rather than two separate databases.
4. Shared DTOs and Jakarta Bean Validation.
5. An MVC `HandlerInterceptor` setting the `X-MVC-Pipeline: active` header for API routes.
6. A `WebMvcConfigurer.addCorsMappings` illustrating global CORS.
7. A simulated functional filter checking `X-Demo-Block: true` to observe route-specific filter scope.
8. MockMvc tests verifying HTTP status, Location, JSON, validations, shared store, routing, and the MVC interceptor.

**Demo limitations:** There is no Spring Security dependency, DB, or production authorization; `X-Demo-Block` is illustrative only. The CORS origin `https://portal.example.test` is a sample domain, not a live service.

### 11.1. File structure

```text
mvc-mixed-endpoints/
├── pom.xml
└── src/
    ├── main/java/demo/mixed/
    │   ├── MixedApplication.java
    │   ├── Note.java
    │   ├── NewNote.java
    │   ├── ApiError.java
    │   ├── NoteStore.java
    │   ├── NoteHandler.java
    │   ├── FunctionalRoutes.java
    │   ├── AnnotatedNotesController.java
    │   └── MvcInfrastructureConfig.java
    └── test/java/demo/mixed/
        └── MixedMvcTest.java
```

**`pom.xml`**

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
    <artifactId>mvc-mixed-endpoints</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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

### 11.2. Boot application

**`src/main/java/demo/mixed/MixedApplication.java`**

```java
package demo.mixed;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MixedApplication {
    public static void main(String[] args) {
        SpringApplication.run(MixedApplication.class, args);
    }
}
```

### 11.3. Shared DTOs and simple entities

**`src/main/java/demo/mixed/Note.java`**

```java
package demo.mixed;

public record Note(long id, String title) {}
```

**`src/main/java/demo/mixed/NewNote.java`**

```java
package demo.mixed;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NewNote(
        @NotBlank @Size(max = 80) String title) {}
```

**`src/main/java/demo/mixed/ApiError.java`**

```java
package demo.mixed;

public record ApiError(String code) {}
```

All use Java 17 records. Jackson can serialize/deserialize these records in Spring Boot 3.3.5. `@NotBlank` and `@Size` only declare constraint metadata; they must be validated via `@Valid` (annotated method) or `Validator.validate` (functional handler).

### 11.4. Shared business component

**`src/main/java/demo/mixed/NoteStore.java`**

```java
package demo.mixed;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class NoteStore {

    private final AtomicLong ids = new AtomicLong();
    private final ConcurrentHashMap<Long, Note> notes =
            new ConcurrentHashMap<>();

    public Note create(String title) {
        Note note = new Note(ids.incrementAndGet(), title.strip());
        notes.put(note.id(), note);
        return note;
    }

    public Optional<Note> find(long id) {
        return Optional.ofNullable(notes.get(id));
    }

    public List<Note> list() {
        List<Note> data = new ArrayList<>(notes.values());
        data.sort(Comparator.comparingLong(Note::id));
        return data;
    }

    public Optional<Note> latest() {
        return list().stream()
                .max(Comparator.comparingLong(Note::id));
    }

    public List<Note> search(String q) {
        String term = q.toLowerCase(Locale.ROOT).strip();
        return list().stream()
                .filter(n -> n.title()
                        .toLowerCase(Locale.ROOT).contains(term))
                .toList();
    }
}
```

The store is purely an example: data disappears after restart; there is no persistence or authorization. Having `ConcurrentHashMap` does not solve transactions, tenant isolation, or unique constraints. With a real DB, replace it with a service/repository/JPA and place `@Transactional` on service methods needing transactions. Both functional and annotated handlers invoke the same Spring proxy when properly injected, avoiding two separate business implementations.

### 11.5. Functional handler: ServerRequest/ServerResponse

**`src/main/java/demo/mixed/NoteHandler.java`**

```java
package demo.mixed;

import java.net.URI;

import jakarta.validation.Validator;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class NoteHandler {

    private final NoteStore store;
    private final Validator validator;

    public NoteHandler(NoteStore store, Validator validator) {
        this.store = store;
        this.validator = validator;
    }

    public ServerResponse list(ServerRequest request) throws Exception {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.list());
    }

    public ServerResponse latest(ServerRequest request) throws Exception {
        Note note = store.latest().orElse(null);
        if (note == null) {
            return ServerResponse.notFound().build();
        }
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }

    public ServerResponse search(ServerRequest request) throws Exception {
        String q = request.param("q").orElse("");
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.search(q));
    }

    public ServerResponse find(ServerRequest request) throws Exception {
        long id;
        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException ex) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError("bad_id"));
        }

        Note note = store.find(id).orElse(null);
        if (note == null) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }

    public ServerResponse create(ServerRequest request) throws Exception {
        NewNote input = request.body(NewNote.class);

        if (input == null || !validator.validate(input).isEmpty()) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError("invalid_note"));
        }

        Note note = store.create(input.title());
        URI location = URI.create("/api/fn/notes/" + note.id());

        return ServerResponse.created(location)
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }
}
```

**Points to note:**

- `@Component` enables injecting the handler and reusing `NoteStore`/`Validator`.
- No `@RequestMapping`/`@PostMapping` on the class: functional `RouterFunction` handles mapping.
- `request.body(NewNote.class)` reads JSON via the MVC converter, then the handler explicitly invokes the validator.
- `request.pathVariable("id")` is converted from String to long manually; if invalid, it returns the JSON error `bad_id`.
- `ServerResponse.created(location)` returns **HTTP 201 Created** and `Location`; the relative URI is built from a server-controlled prefix. Never take user-supplied Host/Forwarded headers to construct redirects.
- The handler holds no request-specific state in object fields; `NoteStore` is used concurrently by both handler styles.
- In production, `request.body(...)` can throw when JSON is malformed; the demo does not define a custom malformed-JSON error schema. Test in practice before promising a specific error format.

### 11.6. RouterFunction bean

**`src/main/java/demo/mixed/FunctionalRoutes.java`**

```java
package demo.mixed;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.web.servlet.function.RequestPredicates.contentType;
import static org.springframework.web.servlet.function.RouterFunctions.route;

@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> noteRoutes(NoteHandler handler) {
        return route()
                // Literal routes before variable route.
                .GET("/api/fn/notes/latest", handler::latest)
                .GET("/api/fn/notes/search", handler::search)
                .GET("/api/fn/notes/{id}", handler::find)
                .GET("/api/fn/notes", handler::list)
                .POST("/api/fn/notes",
                        contentType(MediaType.APPLICATION_JSON),
                        handler::create)
                .filter((request, next) -> {
                    // Scope demonstration only, NOT authorization.
                    String blocked = request.headers()
                            .firstHeader("X-Demo-Block");
                    if ("true".equalsIgnoreCase(blocked)) {
                        return ServerResponse
                                .status(HttpStatus.FORBIDDEN)
                                .contentType(MediaType.APPLICATION_JSON)
                                .body(new ApiError("demo_blocked"));
                    }
                    return next.handle(request);
                })
                .build();
    }
}
```

Both `latest` and `search` precede `/{id}`, avoiding being parsed as an ID. `contentType(JSON)` applies to the POST body; it is not `accept(JSON)` (which checks what response type the client wants to receive). The functional filter takes effect only inside this router bean and does not apply to annotated endpoints under `/api/annotated/**`.

When an API has dozens of routes, use `path(...)`/`nest(...)` or multiple router beans to group domains. Never use a wildcard functional route `/**` that captures everything and accidentally shadows static files, controllers, or error handlers.

### 11.7. Annotated controller sharing the store

**`src/main/java/demo/mixed/AnnotatedNotesController.java`**

```java
package demo.mixed;

import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/annotated/notes")
public class AnnotatedNotesController {

    private final NoteStore store;

    public AnnotatedNotesController(NoteStore store) {
        this.store = store;
    }

    @GetMapping
    public List<Note> list() {
        return store.list();
    }

    @GetMapping("/latest")
    public ResponseEntity<Note> latest() {
        return store.latest()
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/search")
    public List<Note> search(@RequestParam(defaultValue = "") String q) {
        return store.search(q);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Note> find(@PathVariable long id) {
        return store.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Note> create(
            @Valid @RequestBody NewNote input) {
        Note note = store.create(input.title());
        URI location = URI.create(
                "/api/annotated/notes/" + note.id());
        return ResponseEntity.created(location).body(note);
    }
}
```

Annotated code requires less HTTP plumbing when binding/validation is straightforward:
- `@PathVariable long id`: Spring MVC converts automatically.
- `@RequestParam(defaultValue = "")`: Spring MVC reads query/default automatically.
- `@Valid @RequestBody`: uses body converter + automatic Bean Validation.
- `ResponseEntity.created(location)`: returns 201 + Location.

Sharing `NoteStore` means a note created via `/api/fn/notes` can be read via `/api/annotated/notes/{id}` and vice versa. This proves **coexistence in a shared business layer**, not merely two static responses.

### 11.8. WebMvcConfigurer: shared interceptor and CORS

**`src/main/java/demo/mixed/MvcInfrastructureConfig.java`**

```java
package demo.mixed;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcInfrastructureConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override
            public boolean preHandle(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler) {
                response.setHeader("X-MVC-Pipeline", "active");
                return true;
            }
        }).addPathPatterns("/api/**");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://portal.example.test")
                .allowedMethods("GET", "POST", "OPTIONS")
                .allowedHeaders("Content-Type", "Authorization");
    }
}
```

This is **additive** configuration and does not create a second DispatcherServlet. The interceptor sends `X-MVC-Pipeline: active` for MVC handlers to which MVC configuration attaches the interceptor by path; the test below checks both functional and annotated endpoints.

CORS allows browser scripts at `https://portal.example.test` to call `/api/**` APIs using the listed methods/headers, provided handler mapping/CORS integration supports it. This does not allow untrusted websites to read user data; when adding cookie auth, handle allowed credentials, CSRF, and Spring Security CORS integration carefully.

**Do not arbitrarily combine `allowedOrigins("*")` with credentials**. And do not use CORS instead of authentication: curl or non-browser clients can still call the API when security controls are absent.

## 12. Running the Application, Observing the Shared DispatcherServlet

In the `mvc-mixed-endpoints` directory containing `pom.xml`, with Java 17+ and Maven installed:

```bash
mvn test
mvn spring-boot:run
```

The two commands run sequentially. To start only the server without running tests first, run `mvn spring-boot:run` alone. By Boot default, the server listens on `http://localhost:8080`.

### 12.1. Creating a note via the functional route

```bash
curl -i -X POST 'http://localhost:8080/api/fn/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Spring MVC Functional"}'
```

On a fresh JVM with no prior data:

```http
HTTP/1.1 201
Location: /api/fn/notes/1
Content-Type: application/json
X-MVC-Pipeline: active

{"id":1,"title":"Spring MVC Functional"}
```

Status 201 and Location follow real HTTP semantics; do not put a URL in a JSON field while returning HTTP 200. A relative URL avoids trusting unverified Host headers. The `X-MVC-Pipeline` header comes from the MVC interceptor, not the functional router filter.

### 12.2. Reading back from the annotated controller

```bash
curl -i 'http://localhost:8080/api/annotated/notes/1'
```

Expected 200 and JSON:

```json
{"id":1,"title":"Spring MVC Functional"}
```

Seeing the exact same note proves both endpoint styles share `NoteStore`.

### 12.3. Creating a note via annotation, reading via functional

```bash
curl -i -X POST 'http://localhost:8080/api/annotated/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Spring MVC Annotation"}'

curl -i 'http://localhost:8080/api/fn/notes/2'
```

Note ID 2 is expected in the functional response if both requests run sequentially after the first creation with no intervening requests. IDs can differ across other tests/in-memory state; do not hardcode IDs in automated tests.

### 12.4. Search, latest, and precedence

```bash
curl -G -i 'http://localhost:8080/api/fn/notes/search' \
  --data-urlencode 'q=Functional'

curl -i 'http://localhost:8080/api/fn/notes/latest'
```

Search returns a JSON array of notes whose title contains "Functional". Latest returns the note with the highest ID. If `/{id}` were placed before `/search` or `/latest`, clients could receive 400 `bad_id` — a functional builder route precedence bug.

### 12.5. Functional-only filter

```bash
curl -i 'http://localhost:8080/api/fn/notes' \
  -H 'X-Demo-Block: true'

curl -i 'http://localhost:8080/api/annotated/notes' \
  -H 'X-Demo-Block: true'
```

The first request is expected to return `403` with body:

```json
{"code":"demo_blocked"}
```

The second request is still answered with 200 by the annotated handler; it is outside the functional router filter. **This is not an access control policy**: clients can modify headers freely, and all real security must be enforced in Spring Security/services.

### 12.6. Validation 400 on both, yet bodies may differ

```bash
curl -i -X POST 'http://localhost:8080/api/fn/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}'

curl -i -X POST 'http://localhost:8080/api/annotated/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}'
```

The functional handler explicitly returns:

```http
HTTP/1.1 400
Content-Type: application/json

{"code":"invalid_note"}
```

The annotated handler can return 400 via `@Valid`, **yet Boot/MVC's default error body shape** does not automatically match `ApiError("invalid_note")`. If API clients need a shared error body, design an explicit adapter/error contract and test both.

## 13. MockMvc: Contract Tests for Both Handler Styles and Shared Infrastructure

**`src/test/java/demo/mixed/MixedMvcTest.java`**

```java
package demo.mixed;

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
import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MixedMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void functionalCreateCanBeReadByAnnotatedController()
            throws Exception {
        MvcResult created = mvc.perform(post("/api/fn/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Cross Style One\"}"))
                .andExpect(status().isCreated())
                .andReturn();

        String location = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);
        assertTrue(location.matches("/api/fn/notes/[1-9][0-9]*"));

        String id = location.substring(location.lastIndexOf('/') + 1);
        mvc.perform(get("/api/annotated/notes/" + id))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.title").value("Cross Style One"));
    }

    @Test
    void annotatedCreateCanBeReadByFunctionalHandler()
            throws Exception {
        MvcResult created = mvc.perform(
                    post("/api/annotated/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Cross Style Two\"}"))
                .andExpect(status().isCreated())
                .andReturn();

        String location = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);
        String id = location.substring(location.lastIndexOf('/') + 1);

        mvc.perform(get("/api/fn/notes/" + id))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.title").value("Cross Style Two"));
    }

    @Test
    void mvcInterceptorAppliesToBothHandlerStyles()
            throws Exception {
        mvc.perform(get("/api/fn/notes"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    "X-MVC-Pipeline", "active"));

        mvc.perform(get("/api/annotated/notes"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    "X-MVC-Pipeline", "active"));
    }

    @Test
    void functionalFilterDoesNotInterceptAnnotations()
            throws Exception {
        mvc.perform(get("/api/fn/notes")
                    .header("X-Demo-Block", "true"))
           .andExpect(status().isForbidden())
           .andExpect(jsonPath("$.code").value("demo_blocked"));

        mvc.perform(get("/api/annotated/notes")
                    .header("X-Demo-Block", "true"))
           .andExpect(status().isOk());
    }

    @Test
    void functionalValidationUsesInjectedValidator()
            throws Exception {
        mvc.perform(post("/api/fn/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"   \"}"))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("invalid_note"));
    }

    @Test
    void annotationValidationUsesMethodArgumentPipeline()
            throws Exception {
        mvc.perform(post("/api/annotated/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"   \"}"))
           .andExpect(status().isBadRequest());
    }

    @Test
    void literalRoutesOutrankVariableRouteByDeclaredOrder()
            throws Exception {
        mvc.perform(post("/api/fn/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Latest Marker\"}"))
           .andExpect(status().isCreated());

        mvc.perform(get("/api/fn/notes/latest"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.id").isNumber());
    }

    @Test
    void searchReadsQueryParameter() throws Exception {
        mvc.perform(post("/api/fn/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Unique Search Phrase\"}"))
           .andExpect(status().isCreated());

        mvc.perform(get("/api/fn/notes/search")
                    .param("q", "Unique Search Phrase"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$[0].title")
                    .value("Unique Search Phrase"));
    }

    @Test
    void missingResourceGets404InBothStyles()
            throws Exception {
        mvc.perform(get("/api/fn/notes/999999999"))
           .andExpect(status().isNotFound());

        mvc.perform(get("/api/annotated/notes/999999999"))
           .andExpect(status().isNotFound());
    }

    @Test
    void badFunctionalIdHasExplicitErrorContract()
            throws Exception {
        mvc.perform(get("/api/fn/notes/not-a-number"))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("bad_id"));
    }
}
```

The test suite above has **10 test methods**. Run:

```bash
mvn test
```

When source files are created accurately and all tests pass, Maven exits with code 0 and a summary similar to `Tests run: 10, Failures: 0, Errors: 0, Skipped: 0`. This example was written and statically reviewed against Java 17/Spring MVC 6.1; **Maven was not actually executed in the Google Sheets authoring environment**.

### Why do the tests avoid hardcoding ID 1/2?

The tests share `NoteStore` within the same application context; JUnit test execution order is not a contract. After POST, they read the actual `Location` header, extract the ID from the URI, and perform the GET. This makes tests far less dependent on ordering/parallel test state. With a production DB, you must also handle per-test isolation/test transactions/cleanup.

### What does MockMvc verify, and what is still missing?

MockMvc verifies:
- DispatcherServlet routing to the right functional or annotated handler.
- Headers from the MVC interceptor.
- That the functional router filter does not affect annotated endpoints.
- JSON converters, validation/status, and `Location`.
- Shared store/read-your-write behavior.
- That literal routes are not captured by `/{id}`.

MockMvc is **not enough** to prove:
- Reverse proxies rewrite Host/Forwarded/CORS properly in real deployments.
- The Servlet security chain behaves as configured for production if tests omit Spring Security.
- HTTP client aborts/async timeouts/socket backpressure.
- DB transaction rollbacks, deadlocks, and connection pooling under concurrency.
- OpenAPI generators discover functional routes.
- Cache/CDN policies do not leak user data.

Add integration tests through an embedded server/gateway and Spring Security test support when the real app includes those features.

## 14. CORS and Preflight: Configuration Must Pass Through the Right Mapping

A browser sending a request from `https://portal.example.test` to `http://localhost:8080/api/fn/notes` is governed by the same-origin policy. CORS is a mechanism for **browsers** to decide whether to read cross-origin responses; it does not prove the user is authenticated or authorized.

With `WebMvcConfigurer.addCorsMappings("/api/**")`, MVC HandlerMappings can apply the registered policy. However, `OPTIONS` preflight requests are handled at the mapping/CORS processing layer; a `RouterFunction` with GET/POST predicates can produce different error branches if configuration/routing/custom filters differ. When adding functional endpoints to an older app, **test real preflight** requests:

```bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/fn/notes' \
  -H 'Origin: https://portal.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

Inspect `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and status. Never assume a `@CrossOrigin` annotation on an annotated controller applies automatically to another functional endpoint.

When Spring Security is present, integrate CORS into the security filter chain properly, because preflight requests usually lack session cookies; if security blocks before the CORS processor, browser requests can fail. Enable `allowCredentials(true)` only for trusted origins and never combine it with invalid wildcard origins.

## 15. Multipart, File Upload, Static Resources, and Templates

When gradually migrating to functional endpoints, not every use case has a simple 1:1 conversion.

### Multipart / forms

Annotated MVC allows:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> upload(
        @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    // ...
}
```

The snippet above uses undefined types. This is a use case where Spring binding automatically supports rich options. In WebMvc.fn, you can access `ServerRequest.servletRequest()` / multipart servlet facilities and use appropriate converters/helpers, **but do not assume** the exact same `@RequestPart` method-argument auto-resolution inside a HandlerFunction. If an API has many uploads/validation constraints/bindings, keeping an annotated controller can be simpler and more maintainable.

### Static resources

Spring MVC typically serves JS/CSS/images from `classpath:/static` via resource handlers and cache policies. WebMvc.fn offers `RouterFunctions.resources(...)`/`resource(...)` for special cases; there is no need to replace the static resource handler just for functional style uniformity.

If writing an SPA fallback route such as `/**`, ensure it does not shadow:
- `/api/**` handlers and 404s.
- Actuator/health endpoints.
- Static resources/assets caching and range requests.
- Security-sensitive paths.

When a URL does not match a functional route, RouterFunction can return empty so DispatcherServlet checks other HandlerMappings. However, a catch-all functional route can match too early and break the intended fallback.

### Rendering templates

Annotated `@Controller` provides `Model`, `@ModelAttribute`, and view names. WebMvc.fn also has mechanisms to render views via `ServerResponse`/MVC view resolvers, yet lacks automatic method-argument binding from controller annotations. If a large project uses Thymeleaf forms, custom binders, and validation message codes, weigh the conversion cost; keeping annotated MVC for web pages and WebMvc.fn for API modules can be a sensible hybrid.

## 16. Observable Application: Logs, Metrics, Tracing, and Interceptors

Before adding a routing model, the team should know which layer tracing/metrics depend on.

1. **Servlet Filter / Spring Security filter**: can observe both functional and annotated requests by URL pattern.
2. **MVC interceptor**: usually covers MVC HandlerMappings managed by configuration, though it can depend on dispatch type and exception/async lifecycles.
3. **HandlerMethod-specific instrumentations**: may require extra support for `HandlerFunction`; do not assume controller/method names populate metric tags for functional endpoints.
4. **Micrometer/Observations**: frameworks share HTTP server integration, yet route pattern naming/tagging must be verified on the deployed version.
5. **Structured logging/MDC**: every route needs a trace ID without logging secret bodies/Authorization; async workers need context propagation if used.

A simple verification is sending the same GET to `/api/fn/notes` and `/api/annotated/notes`, then comparing:
- Are trace/span IDs fully populated?
- Are HTTP method/status/route pattern tags consistent?
- Are request latency/error counts recorded for both?
- Is security principal/tenant correlation accurate?
- Are exceptions classified as 4xx vs. 5xx?
- Are duplicate spans avoided on Servlet async redispatch?

This is critical during migration: an API might return accurate HTTP responses yet **go blind in observability** if instrumentation inspects only `HandlerMethod`.

## 17. Versioning and Contract Tests During Incremental Migration

A legacy project has `/api/v1/orders` served by an annotated controller. When moving route by route to functional, you can split by HTTP operation or resource subdomain:

```text
Before migration:
  GET  /api/v1/orders        @RestController
  POST /api/v1/orders        @RestController
  GET  /api/v1/orders/{id}   @RestController

Transition phase:
  GET  /api/v1/orders        @RestController
  POST /api/v1/orders        WebMvc.fn
  GET  /api/v1/orders/{id}   @RestController

After migration if needed:
  GET  /api/v1/orders        WebMvc.fn
  POST /api/v1/orders        WebMvc.fn
  GET  /api/v1/orders/{id}   WebMvc.fn
```

**Constraint:** each method + route has **only one** owner in any release; never declare duplicates hoping HandlerMapping order handles migration automatically. Update controllers/routers in tested commits/releases; never accidentally alter client URL contracts.

### Contract checklist

For each endpoint, compare before/after:
- Method/path/trailing slash and statuses 200/201/204/400/404/405/406/415.
- Headers: `Content-Type`, `Location`, `Cache-Control`, `ETag`, `Vary`, CORS, and security headers.
- JSON field names, null handling, ordering (if required by contract), locale/timezone.
- Validation constraints/error body/schema.
- Cookie/session/CSRF/authorization behavior.
- Pageable/sorting/query param semantics and duplicate query values.
- Multipart and file downloads: content type, bytes, range requests.
- Compression/proxy/forwarded host and context paths.
- OpenAPI docs + generated clients, operation IDs, and required fields.
- Tracing/metrics, load/timeouts, and rate limiting.

**Do not measure "success" solely by the absence of `@GetMapping` in a controller.** Migration succeeds when API consumers suffer no broken contracts and observability/security do not degrade.

## 18. Error Handling Strategies for a Mixed Application

The goal is a unified response schema, for example:

```json
{
  "code": "invalid_note",
  "message": "Title must not be blank"
}
```

Yet you do not need to force both handler styles through **the exact same exception class**. One way to organize it:

1. Define an `ApiError` or `ProblemDetail` contract in an HTTP-shared module.
2. Provide an adapter for annotated exceptions (`MethodArgumentNotValidException`, type mismatch, message-not-readable) and an adapter for functional exceptions/body validation.
3. Have every branch return the appropriate status; never accidentally turn a business 409 into 500 or 400.
4. Log with trace IDs, without leaking raw rejected PII/secrets.
5. Write tests sending the same invalid requests to both endpoints and comparing status + stable error fields.
6. Test errors during the converter/write phase too, since not every exception occurs inside the handler lambda.
7. Once part of a streaming response is sent, status/body can no longer be changed freely.
8. For handler exception resolution, distinguish global infrastructure from method-annotation-oriented `@ControllerAdvice`.

### Why not catch broad Exception in every functional filter?

```java
// ANTI-PATTERN: masking every bug as bad request.
try {
    return next.handle(request);
} catch (Exception e) {
    return ServerResponse.badRequest().body("invalid");
}
```

Database errors, NullPointerExceptions, permission failures, or network outages can be misclassified, hiding incidents and defeating monitoring/circuit breakers. Catch only exceptions the application can semantically explain, letting unexpected failures fall through to the global error boundary as 5xx.

## 19. Performance: Functional Style Is Not Non-Blocking I/O

A functional handler:

```java
return ServerResponse.ok().body(
        blockingRepository.findAll());
```

still blocks the Servlet request thread when `findAll()` executes synchronous JDBC. Within the same MVC Servlet stack, replacing `@GetMapping` with lambdas/RouterFunction does not turn databases/HTTP clients into reactive/non-blocking I/O.

If an application hits I/O bottlenecks:
- Measure DB pools, remote latency, and thread saturation first.
- Consider pooling, caching, queries/indexes, and timeouts.
- In MVC, `Callable`/`DeferredResult` can free the initial Servlet thread, though blocking work may move to a worker executor.
- For streaming/live events, evaluate backpressure and connection limits.
- Consider WebFlux only when the data path fits reactive/non-blocking I/O and the team has solid concurrency/resource reasons; do not adopt WebFlux merely for functional router syntax.

A WebMvc.fn migration helpful for **code structure** may yield identical throughput. Benchmark based on workload, not the word "functional."

## 20. Common Integration Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Functional endpoint returns 404 | RouterFunction bean not scanned, WebFlux package imported, unmatched predicate | Check application context, packages, and request method/path |
| Annotated API breaks after adding router | Catch-all functional route or custom MVC config | Avoid `/**`/overlap; do not enable `@EnableWebMvc` arbitrarily |
| `/latest` route parsed as ID | `/{id}` placed before literal route | Place literal routes first, test precedence |
| Two implementations on same URL | Two HandlerMappings both match | Assign one owner per method/path, migrate by release |
| JSON readable in annotated yet fails in functional | `request.body(...)`/contentType predicate differs from annotation pipeline | Use right converters/media types, test malformed JSON |
| `@NotBlank` does not return 400 in functional | Validator not invoked | Inject `Validator` and validate explicitly |
| Different error bodies despite both returning 400 | Annotated advice differs from functional explicit responses | Shared API error contract + tests |
| `@ControllerAdvice` misses functional exception | Handler is not a HandlerMethod | Functional error boundary or suitable global resolver |
| Functional filter skips annotated endpoints | Router-level scope | Use Servlet filters / Spring Security for app-wide concerns |
| MVC interceptor skips a custom mapping | Custom HandlerMapping not configured accordingly | Check registry/MappedInterceptor and mapping order |
| CORS preflight gets 403 | Security/CORS ordering or missing policy | Spring Security CORS integration and OPTIONS tests |
| Functional POST gets CSRF 403 | Cookie/session auth still enforces CSRF policy | Send valid CSRF token; do not disable arbitrarily |
| OpenAPI misses routes | Tool does not fully auto-discover RouterFunctions | Choose compatible integration or explicit docs |
| Traces/meters lack handler tags | Metrics integration looks only at annotation metadata | Verify instrumentation for functional handlers |
| ResponseBodyAdvice does not intervene | Functional response writing path differs from annotated | Write shared converter/HTTP adapter as needed, test |
| Wrong Location URL behind reverse proxy | Misconfigured Forwarded headers trust/path prefix | Trusted ingress, canonical base URL/relative URI |
| DTO overposting/IDOR | Validation checks syntax only, not authorization | Server-owned identity and per-resource authorization |
| Static JS/CSS returns 404 | Catch-all route blocks resource handler | Scope static routing/SPA fallback properly |
| GET returns different body across styles | Different Jackson/view config or adapter behavior | Contract tests for fields, headers, bytes, and nulls |
| Async request loses MDC/security context | Cross-thread context does not propagate automatically | Proper delegating executor/context propagation |
| File upload fails to bind MultipartFile | Functional lacks `@RequestPart` method args like annotated | Keep annotated for multipart or write explicit binding |

## 21. Production Deployment Checklist

1. Confirm functional endpoints genuinely add value in route composition, testability, or maintainability.
2. Do not add a second MVC Servlet application; register `RouterFunction` beans in the existing context.
3. Use the exact `org.springframework.web.servlet.function` namespace.
4. Keep annotated controllers where appropriate; do not rewrite the whole app pointlessly.
5. Separate REST adapters from the business layer, reusing Spring `@Service` and transaction boundaries.
6. Verify `RouterFunctionMapping` discovery/ordering, especially with multiple router beans.
7. Avoid overlapping method/path ownership; place literal routes before path variables.
8. Continue sharing converter/JSON configuration; do not accidentally override defaults.
9. Execute Bean Validation explicitly in functional handlers.
10. Design consistent error schemas/status policies across both pipelines.
11. Keep Spring Security/CSRF/auth in the filter chain/services, not solely in functional filters.
12. Test MVC interceptors and Servlet filters with both functional and annotated routes.
13. Test CORS preflight, OPTIONS/HEAD, and headers.
14. Check static resource handling/SPA fallbacks so they do not shadow other routes.
15. Protect Host/Forwarded headers and Location redirects when running behind a proxy.
16. Verify OpenAPI docs and generated client contracts after migration.
17. Verify logging/tracing/metrics capture all routes and statuses.
18. Never assume functional means non-blocking; measure real database/network performance.
19. Run MockMvc contract tests on every path; add integration tests for proxy/security/database behavior.
20. Roll out route by route with a rollback strategy, monitoring 4xx/5xx rates and latency.

## 22. Self-Check Exercises

1. Why can WebMvc.fn and `@RestController` coexist in a single Spring Boot Web application?
2. How do `RouterFunctionMapping` and `RequestMappingHandlerMapping` differ in role?
3. For `GET /api/fn/notes/latest`, why can `/{id}` cause an error if placed first?
4. Can a singleton `NoteStore` be shared by both annotated and functional handlers? Why?
5. Does `ServerRequest.body(NewNote.class)` automatically trigger `@NotBlank`?
6. If an app has `@RestControllerAdvice` for `MethodArgumentNotValidException`, is every functional validation error guaranteed to pass through that advice?
7. How do `WebMvcConfigurer.addInterceptors` and `RouterFunctions.Builder.filter` differ in scope?
8. Does a functional filter attached to `/api/fn/**` protect `/api/annotated/**`?
9. Why must the Spring Security filter chain still apply when migrating to functional endpoints?
10. Where can a browser `OPTIONS` preflight request be blocked before reaching a functional handler?
11. What does `@Transactional` in a shared service mean for the two handler styles?
12. Can duplicate routes be avoided by writing a HandlerMapping with a smaller order, or should there be a single clear owner?
13. Why can a static fallback `/**` cause wrong 404/200 responses for an API?
14. When a mixed app returns 400 from both styles, is the client guaranteed to receive the same JSON error schema?
15. Why does changing router syntax not automatically make JDBC non-blocking?
16. When migrating an endpoint, which HTTP headers besides the JSON body must be checked?
17. Can CORS replace authentication/authorization?
18. How do you prove a shared interceptor works: only reading config or running real HTTP tests?
19. Why might OpenAPI instrumentation see annotated endpoints more easily than functional routes?
20. When should you keep an annotated controller instead of converting to WebMvc.fn?

**Hints:** (1) Same DispatcherServlet, different HandlerMapping/Adapter. (2) Functional vs. annotation routing. (3) First-match order. (4) Yes, same Spring IoC context/business service. (5) No; requires explicit Validator. (6) Do not assume so. (7) MVC mapping config vs. router-local handler composition. (8) No. (9) Protects the entire HTTP request, not only lambdas. (10) Servlet/Security filters or CORS/HandlerMapping policy. (11) Transactions apply at the service proxy regardless of HTTP adapter. (12) One clear route owner is safer. (13) Too broad a match can shadow static/other mappings. (14) No. (15) Framework still runs on the Servlet stack/blocking dependencies. (16) Status, Content-Type, Location, CORS, cache, security, ETag... (17) No. (18) MockMvc/integration tests on both paths. (19) Tooling inspects HandlerMethod/annotations. (20) When existing binding/form/validation/error tooling fits better with no clear migration benefit.

## 23. Official Documentation and Further Reading

- [Spring Framework 6.1 — Functional Endpoints (Spring MVC)](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc-functional.html)
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
- [Spring Framework 6.1 — RouterFunctions Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.html)
- [Spring Framework 6.1 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/function/ServerRequest.html)
- [Spring Framework 6.1 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/function/ServerResponse.html)
- [Spring Framework 6.1 — RouterFunctionMapping Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/function/support/RouterFunctionMapping.html)
- [Spring Framework — MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config.html)
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [Spring Framework — MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html)
- [Spring Framework — Exception Handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring MVC Testing — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)

**Summary:** Functional endpoints are a way to declare HTTP routes inside existing Spring MVC, **not a different web server or framework**. `RouterFunction` + `HandlerFunction` can run alongside annotated controllers on `DispatcherServlet`; they share Spring IoC, services/repositories, HTTP converters, and much of MVC configuration. However, annotation-specific argument binding/validation/error handling **are not automatically copied over to functional handlers**. To integrate safely, keep business logic shared, clarify route ownership, design validation and error contracts explicitly, protect HTTP with Servlet/Spring Security, test interceptors/CORS/OpenAPI, and roll out incrementally with regression tests.
