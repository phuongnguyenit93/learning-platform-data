# Reading Input, Building Responses, and Using Message Converters in Functional Spring MVC

> **Context:** Spring Framework 6.2.x, Spring Boot 3.5.x, Java 17+, on the **Servlet stack**. This topic belongs to **Functional MVC (WebMvc.fn)**: handling requests with `HandlerFunction<ServerResponse>` instead of declaring controller methods with `@RequestMapping`, reading data from `ServerRequest`, returning `ServerResponse`, and using Spring MVC's **`HttpMessageConverter`** implementations to turn HTTP bytes into Java objects and vice versa. Distinguish this from **WebFlux.fn**: WebMvc.fn uses the `org.springframework.web.servlet.function` package, and its primary body-reading operations are `request.body(Class<T>)` / `request.body(ParameterizedTypeReference<T>)`, not WebFlux's `bodyToMono()` or `HttpMessageReader`.

## 1. What Does Functional MVC Solve?

Spring MVC has two familiar ways to declare HTTP endpoints:

**Annotation-based MVC:**

```java
@RestController
@RequestMapping("/api/books")
class BookController {

    @PostMapping
    public Book create(@RequestBody CreateBook input) {
        return service.create(input);
    }
}
```

**Functional MVC (WebMvc.fn):**

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .POST("/api/books", handler::create)
                .build();

// Inside handler class:
ServerResponse create(ServerRequest request) throws Exception {
    CreateBook input = request.body(CreateBook.class);
    Book saved = service.create(input);
    return ServerResponse.ok().body(saved);
}
```

The two snippets above **are illustrative snippets**, requiring `Book`, `CreateBook`, `service`, and `handler` to be defined. Functional MVC still runs inside **`DispatcherServlet`**, still uses Servlet requests/responses and message converters; it does **not** automatically turn a web application into a reactive WebFlux stack.

For the goal of "reading input – building responses – using converters", the WebMvc.fn model is:

```text
HTTP request bytes
      |
Servlet container / DispatcherServlet
      |
RouterFunction<ServerResponse> selects route
      |
HandlerFunction<ServerResponse>.handle(ServerRequest)
      |
ServerRequest.body(Class/ParameterizedTypeReference)
      |
HttpMessageConverter.read(...)  <-- JSON/text/form/binary
      |
Java DTO + validation/authorization/business logic
      |
ServerResponse.status(...).contentType(...).body(Java object)
      |
HttpMessageConverter.write(...) <-- serialize body by type/media
      |
HTTP status + headers + response bytes
```

**Remember:** The router decides **which handler** runs; the handler decides **what to read and what to return**; the converter decides **how to interpret and serialize the HTTP body**. Validation, authentication/authorization, and payload size limits are separate responsibilities; having Jackson does not mean input is automatically safe.

## 2. Four Components of Functional MVC

| Component | Package | Role |
| --- | --- | --- |
| `RouterFunction<ServerResponse>` | `org.springframework.web.servlet.function` | Determines the corresponding handler from `ServerRequest` |
| `HandlerFunction<ServerResponse>` | `org.springframework.web.servlet.function` | Receives `ServerRequest`, returns `ServerResponse`; may `throws Exception` |
| `ServerRequest` | `org.springframework.web.servlet.function` | Accesses method/URI/headers/query/path variables/body/cookies/Servlet request |
| `ServerResponse` | `org.springframework.web.servlet.function` | Builds status/headers/cookies/body or empty response, then writes via converters |
| `HttpMessageConverter<T>` | `org.springframework.http.converter` | Converts between Java values and HTTP request/response bytes |
| `RouterFunctionMapping` | `org.springframework.web.servlet.function.support` | Discovers RouterFunction beans and finds matching routes |
| `HandlerFunctionAdapter` | `org.springframework.web.servlet.function.support` | Executes HandlerFunction inside the MVC lifecycle |

In a Spring Boot Web app, the Spring MVC infrastructure usually auto-detects `RouterFunction<?>` beans. **You do not need `@EnableWebMvc`** just to use functional routes; enabling it arbitrarily can disable some Boot MVC auto-configuration defaults.

### 2.1. Functional does not mean purely side-effect free

The request/response APIs describe an **immutable-style contract** for building routes/responses; however, a handler can still interact with databases, transactions, Servlet sessions, and stateful Spring beans. `ServerRequest` can expose request attributes, the body, and the underlying servlet request; thus thread-safety, validation, and authorization design are still required.

### 2.2. Do not confuse with WebFlux.fn

| Aspect | WebMvc.fn | WebFlux.fn |
| --- | --- | --- |
| Server request import | `org.springframework.web.servlet.function.ServerRequest` | `org.springframework.web.reactive.function.server.ServerRequest` |
| Handler returns | `ServerResponse` | `Mono<ServerResponse>` or Kotlin coroutine adapters |
| Reading JSON DTO | `request.body(Dto.class)` | `request.bodyToMono(Dto.class)` |
| Reading `List<T>` | `request.body(new ParameterizedTypeReference<List<T>>() {})` | `bodyToFlux(T.class)` or `bodyToMono(...)` |
| HTTP formatting | MVC `HttpMessageConverter` | WebFlux reactive `HttpMessageReader/Writer` codecs |
| HTTP I/O | Servlet blocking foundation | Reactive stack, non-blocking I/O when runtime supports it |
| Server entrypoint | `DispatcherServlet` | `DispatcherHandler` |

If your IDE reports that `bodyToMono()` cannot be found on `ServerRequest` while your project uses `web.servlet.function`, **it is not a missing import**: you are reading a WebFlux.fn example. Switch to the right API instead of adding the reactive starter just to make the compiler recognize a method absent from the MVC type.

## 3. RouterFunction and HandlerFunction: Routing Requests to the Right Place

Example:

```java
import static org.springframework.web.servlet.function.RouterFunctions.route;

@Bean
RouterFunction<ServerResponse> booksRouter(BookHandler handler) {
    return route()
            .GET("/api/books", handler::list)
            .GET("/api/books/{id}", handler::get)
            .POST("/api/books", handler::create)
            .build();
}
```

This is an illustrative bean method in a `@Configuration` class, requiring `BookHandler`, `@Bean`, and `RouterFunction`/`ServerResponse` imports.

- `RouterFunctions.route()` creates the DSL builder.
- `.GET(path, handler)` and `.POST(path, handler)` bind method/path to callbacks.
- `handler::get` is a method reference; the target method takes `ServerRequest` and returns `ServerResponse`.
- `.build()` returns a `RouterFunction<ServerResponse>` for Spring MVC to register.
- In annotated MVC, routing metadata comes from `@GetMapping`/`@PostMapping`; in WebMvc.fn, metadata comes from **functions/builders**.

### 3.1. Predicates filtering Content-Type and Accept

If you want the POST route to handle JSON only, you can use:

```java
import static org.springframework.web.servlet.function.RequestPredicates.contentType;

RouterFunction<ServerResponse> router = route()
        .POST("/api/books", contentType(MediaType.APPLICATION_JSON),
                handler::create)
        .build();
```

If you want to enforce `Accept: application/json`:

```java
import static org.springframework.web.servlet.function.RequestPredicates.accept;

RouterFunction<ServerResponse> router = route()
        .GET("/api/books", accept(MediaType.APPLICATION_JSON),
                handler::list)
        .build();
```

**Important note:** when a predicate does not match, the router may simply skip selecting the handler and lead to a 404/or handling by other mappings, **not necessarily** matching the 415/406 statuses of an annotated controller. If the API needs an exact error contract for wrong Content-Type/Accept, run integration tests and define an explicit error policy. The runnable example in section 9 intentionally omits the `contentType(...)` predicate so body/converter errors are easy to observe.

### 3.2. Nested routes and filter functions

```java
RouterFunction<ServerResponse> router = route()
        .path("/api", b -> b
                .GET("/health", handler::health)
                .POST("/books", handler::create))
        .build();
```

This is a snippet with another defined `handler`. Nested routing helps group prefixes/conditions. WebMvc.fn also offers `before`, `after`, `filter`, and `onError` on the router builder. When registering a filter **inside a nested route**, the filter's scope does not automatically extend to outer routes. Use them for appropriate cross-cutting concerns, not as a replacement for Spring Security FilterChain.

## 4. Reading Request Metadata Before Reading the Body

`ServerRequest` provides convenient APIs:

```java
String id = request.pathVariable("id");
Optional<String> q = request.param("q");
HttpMethod method = request.method();
URI uri = request.uri();
String accept = request.headers().firstHeader("Accept");
Map<String, Object> attrs = request.attributes();
```

This snippet requires `java.net.URI`, `java.util.*`, and `org.springframework.http.HttpMethod` imports. APIs can vary across Spring major versions; Spring MVC 6.2 has `pathVariable`, `param`, `headers`, and `attributes`.

- `request.pathVariable("id")` fetches the path segment matched by RouterFunction; it can throw an error if the route lacks that variable.
- `request.param("q")` returns `Optional<String>`; handle the missing case rather than calling `.get()`.
- `request.params()` reads query parameters into a `MultiValueMap<String,String>` (which may hold multiple values).
- `request.headers()` provides typed header convenience methods like `accept()` and `contentType()` depending on the API.
- `request.servletRequest()` grants access to `HttpServletRequest` when Servlet-specific capabilities are needed; do not use it as a backdoor to read the entire body and then read it again.

### 4.1. PathVariable needs parsing and validation

```java
long id;
try {
    id = Long.parseLong(request.pathVariable("id"));
} catch (NumberFormatException ex) {
    return ServerResponse.badRequest()
            .body("Invalid id");
}
```

This is an illustrative snippet, though a JSON API should use an error DTO and `contentType(APPLICATION_JSON)` instead of a plain-text body. Do not turn `NumberFormatException` into HTTP 500, and do not expose raw exception messages in the body.

### 4.2. Query parameters with defaults and ranges

```java
String rawLimit = request.param("limit").orElse("20");
int limit = Integer.parseInt(rawLimit);
if (limit < 1 || limit > 100) {
    throw new IllegalArgumentException("limit outside range");
}
```

Validate parse errors, size bounds, semantic constraints, and any filtering/search permissions. For pagination, apply LIMIT at the repository/DB rather than loading millions of records and calling `stream().limit(20)` in the app.

## 5. Reading the HTTP Body: ServerRequest.body(Class<T>)

The shortest way for a JSON object:

```java
CreateBook command = request.body(CreateBook.class);
```

When a request arrives with:

```http
POST /api/books HTTP/1.1
Content-Type: application/json

{"title":"Spring MVC"}
```

Spring MVC searches for an `HttpMessageConverter` that can read:
- Target Java type `CreateBook.class`;
- Request `Content-Type` `application/json`;
- Dependencies/converters registered in MVC.

A matching JSON converter (e.g., Jackson from the Spring Web starter) reads bytes from the Servlet request input stream and deserializes them into `CreateBook`. `request.body(...)` can throw if JSON is invalid or no converter matches; the handler method can declare `throws Exception`.

### 5.1. The body can be consumed

A standard Servlet request input stream **is not a stream you can rewind arbitrarily**. Do not do this:

```java
String raw = request.body(String.class);
CreateBook second = request.body(CreateBook.class);
```

This is an anti-pattern: the second read must not be treated as a fresh parse from the beginning. Similarly, if a custom Servlet Filter calls `getInputStream().readAllBytes()` to log before MVC reads the body, the request can appear empty in the handler. To observe the body, use a bounded caching wrapper and let downstream read within the proper lifecycle; do not assume cache-on-read is a built-in replay mechanism.

### 5.2. Body conversion is NOT automatic validation

Suppose the DTO is:

```java
record CreateBook(String title) {
}
```

Jackson can instantiate it when the `title` field is absent/null, so the application must still check required fields, lengths, valid values, and business constraints. In a functional handler, bare `request.body(CreateBook.class)` is not equivalent to running Bean Validation via `@Valid @RequestBody` in an annotated method.

Minimal approach:

```java
CreateBook input = request.body(CreateBook.class);
if (input == null || input.title() == null
        || input.title().isBlank()
        || input.title().length() > 120) {
    return ServerResponse.badRequest()
            .contentType(MediaType.APPLICATION_JSON)
            .body(new ApiError("invalid_title"));
}
```

In a larger app, use Spring `Validator`/Jakarta Bean Validation through an explicit validation service layer to reuse DTO rules. Never read input and map it directly onto a JPA entity containing sensitive fields like `isAdmin`/`ownerId`/`tenantId`.

### 5.3. Exceptions related to reading the body

Common error classes:
- Syntactically invalid JSON or undeserializable data can raise `HttpMessageNotReadableException`.
- Missing a matching converter for the content type or data format can raise `HttpMediaTypeNotSupportedException` / corresponding infrastructure exceptions.
- Invalid formats/business rules rejected by handler code can become `IllegalArgumentException` or an error DTO.
- `IOException`/`ServletException` can arise from the HTTP body reading layer.
- Oversized bodies require **independent** ingress/container/filter policies; registering a converter does not impose a hard cap.

Do not lump everything into HTTP 400 if it is a system failure. An I/O error from a client disconnect or a database outage does not share the same semantics as malformed JSON.

## 6. Reading Generic Types: ParameterizedTypeReference<T>

Java generics undergo type erasure. To deserialize `List<CreateBook>` (a JSON array of objects) with the proper generic element type, use:

```java
import org.springframework.core.ParameterizedTypeReference;

List<CreateBook> commands =
        request.body(new ParameterizedTypeReference<List<CreateBook>>() {});
```

Corresponding request:

```json
[
  {"title":"Book A"},
  {"title":"Book B"}
]
```

If you use `request.body(List.class)`, the converter lacks the generic element type and can produce `List<LinkedHashMap>` instead of `List<CreateBook>`. Directly casting elements to `CreateBook` can throw `ClassCastException`.

### 6.1. When to use Class vs. ParameterizedTypeReference?

| Input | Recommended API |
| --- | --- |
| JSON object of a single DTO | `request.body(CreateBook.class)` |
| JSON string/plain text | `request.body(String.class)` with appropriate Content-Type |
| JSON array with generic element | `request.body(new ParameterizedTypeReference<List<CreateBook>>() {})` |
| Nested JSON map/list | `request.body(new ParameterizedTypeReference<Map<String, List<ValueDto>>>() {})` |
| Raw bytes | `request.body(byte[].class)` with appropriate converter; watch memory |
| Form URL-encoded | `request.params()` / form handling or `MultiValueMap` per converter and request handling |
| Multipart upload | Use supported Servlet multipart parsing and binding; do not assume a JSON converter reads binary files |

### 6.2. ParameterizedTypeReference does not guarantee every format

It provides **type metadata**, not a converter installation. For custom media types or objects unsupported by Jackson/MessageConverter, you still need the matching converter and security/resource limits. Do not assume that "using ParameterizedTypeReference makes JSON/XML/CSV all parseable."

### 6.3. Protecting memory when receiving large Lists

A request containing millions of JSON elements can deserialize into a massive `List<CreateBook>`. Because MVC converters typically read/deserialize the body into an object graph:
- enforce body size limits at the reverse proxy/container or via a counting input stream;
- limit element counts and JSON depth via parser configuration/policy where appropriate;
- consider smaller batches/pagination or dedicated streaming ingestion for big data;
- avoid `readAllBytes()` which duplicates memory.

The demo example caps batches at 5 items, yet **validation after deserialization is not a hard memory limit**. Oversized payloads must be blocked at an earlier layer if your threat model requires it.

## 7. Building ServerResponse: Status, Headers, and Body

WebMvc.fn provides static factories:

```java
ServerResponse.ok()
ServerResponse.created(URI.create("/api/books/42"))
ServerResponse.accepted()
ServerResponse.noContent()
ServerResponse.badRequest()
ServerResponse.notFound()
ServerResponse.status(HttpStatus.CONFLICT)
```

These expressions return builders or response-building APIs; to produce a complete response you call `.body(value)` or `.build()` as appropriate.

### 7.1. HTTP 200 with a JSON body

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Book(42L, "Spring MVC"));
```

The Java object is not sent raw over the network. When Spring writes `ServerResponse`, a matching converter serializes `Book` into JSON bytes. With default Jackson, the body looks like:

```json
{"id":42,"title":"Spring MVC"}
```

Field order/whitespace can vary by Jackson/version, so test JSON by path rather than comparing full strings.

### 7.2. HTTP 201 Created and Location

```java
return ServerResponse.created(URI.create("/api/books/42"))
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Book(42L, "Spring MVC"));
```

This yields status **201 Created**, header `Location: /api/books/42` (a relative URI is valid for Location), and a JSON body. Do not build an absolute host directly from a raw `X-Forwarded-Host` header for sensitive Location values; proxy trust boundaries and canonical public base URLs must be controlled.

### 7.3. No body: build()

```java
return ServerResponse.noContent().build();
```

Returns **204 No Content**; do not call `.body(...)` on 204 and expect browsers to receive JSON. For a successful DELETE or an update needing no representation, 204 is a common choice.

### 7.4. 400/404/409 and error DTOs

```java
return ServerResponse.status(HttpStatus.CONFLICT)
        .contentType(MediaType.APPLICATION_JSON)
        .body(new ApiError("conflict"));
```

For validation errors:

```java
return ServerResponse.badRequest()
        .contentType(MediaType.APPLICATION_JSON)
        .body(new ApiError("invalid_request"));
```

For a missing resource:

```java
return ServerResponse.notFound().build();
```

Use HTTP statuses that reflect semantics instead of returning 200 with `{"error":...}`. Never expose raw exception stack traces, tokens, or internal filesystem paths in responses.

### 7.5. Headers, caching, content negotiation

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .header("X-Request-Tag", "demo")
        .header("Cache-Control", "no-store")
        .body(book);
```

The response builder APIs also support cookies, ETag/Last-Modified, and headers when needed. Be careful:
- `Content-Type` describes the output bytes' format, not the Java class.
- The client's `Accept` header indicates which representations the client accepts.
- If you force `contentType(APPLICATION_JSON)` even when the client accepts only XML, do not assume the handler negotiates identically to annotated `produces`; you need router predicates, infrastructure, and proper 406/serialization tests.
- `Content-Length` must count **encoded bytes**, not `String.length()`; normally leave it to the container/converter.
- Once the response has started writing/committed, you cannot reliably alter its status or headers.

## 8. What Does HttpMessageConverter Actually Do?

Spring MVC `HttpMessageConverter<T>` is the bridge:

```text
Read:
application/json bytes -> Jackson JSON converter -> Java DTO

Write:
Java DTO -> Jackson JSON converter -> application/json bytes

Read:
text/plain bytes -> StringHttpMessageConverter -> String

Write:
byte[] -> ByteArrayHttpMessageConverter -> application/octet-stream bytes

Read form:
application/x-www-form-urlencoded -> FormHttpMessageConverter
                                         -> MultiValueMap<String, String>
```

A converter decides whether it can read/write based on the Java type, `Content-Type` / `MediaType`, libraries on the classpath, and the registered converter order.

### 8.1. Common converters

| Converter | Common Java Type | Media Type |
| --- | --- | --- |
| `StringHttpMessageConverter` | `String` | `text/plain` / text media |
| `MappingJackson2HttpMessageConverter` | POJO/record/List/Map | `application/json` and compatible JSON forms |
| `ByteArrayHttpMessageConverter` | `byte[]` | Typically `application/octet-stream` |
| `ResourceHttpMessageConverter` | `Resource` | Binary/stream resources |
| `FormHttpMessageConverter` | `MultiValueMap<String,String>` | `application/x-www-form-urlencoded` (read/write), multipart (write within supported scope) |
| XML converters | JAXB/Jackson XML types | `application/xml` or `text/xml` if dependency/config is present |

**Do not confuse `HttpMessageConverter` with `Converter<S,T>` in `ConversionService`.** ConversionService typically converts String path/query/form fields into primitives/enums/types; HttpMessageConverter reads/writes the **HTTP body**.

### 8.2. Converters do not replace validation

Deserializing into `CreateBook` does not verify whether the user is authorized to create a book, does not enforce business title limits, does not sanitize HTML scripts, and does not prevent owner spoofing. Dedicated DTOs, bean/manual validation, and domain service authorization are required.

### 8.3. Converters do not guarantee safety against untrusted payloads

A JSON parser can suffer CPU/memory pressure from oversized/deeply nested payloads. Multipart/XML/file uploads carry additional risks. Configure:
- request body and header size limits at the proxy/container;
- parser constraints for elements/depth and multipart limits;
- DTO/schema validation, field allowlists;
- authentication/authorization and rate limits;
- redacted logging, avoiding raw body dumps by default.

### 8.4. Request and response converters in WebMvc.fn

`ServerRequest.messageConverters()` exposes the converters used to read request bodies. When writing `ServerResponse`, the infrastructure uses the converter list in the response context to choose how to serialize the body. Spring Boot MVC auto-configuration supplies default converters based on the classpath.

If you add a custom converter to only part of the infrastructure and an endpoint does not pick it up, check the MVC configuration and converter order; do not assume every custom Jackson `ObjectMapper`/codec applies automatically to all routes.

## 9. Runnable Example: Java 17 + Spring Boot 3.5, WebMvc.fn

The illustrative app **does not use `@RestController`**; it has only:
- One `RouterFunction<ServerResponse>` bean;
- One handler class (Spring component) working with `ServerRequest`/`ServerResponse`;
- One in-memory store decoupled from HTTP routing.

Endpoints:
- `GET /api/books?limit=10` — reads query param, returns JSON array;
- `GET /api/books/{id}` — reads path variable, returns JSON or 404;
- `POST /api/books` — uses `body(CreateBook.class)`, validates, returns 201 + Location + JSON;
- `POST /api/books/batch` — uses `body(ParameterizedTypeReference<List<CreateBook>>)`, validates, and returns a JSON array.
- `IllegalArgumentException` errors from input checks are mapped by the router's `onError` to 400 JSON.

**This is a learning example:** it uses an in-memory concurrent map; there is no database, user auth, CSRF, CORS, or persistent storage. Those protections must be added in production. `CREATE` in the demo can be called unauthenticated; never deploy it publicly as a production service.

### 9.1. POM/Dependencies

Create a Maven project at [Spring Initializr](https://start.spring.io/) with:
- Spring Boot 3.5.x, Java 17+;
- **Spring Web** (`spring-boot-starter-web`) dependency.

Version-managed `pom.xml` fragment from Initializr:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Spring Web starter includes Spring MVC, the Jackson JSON converter, and embedded Tomcat by default. No `spring-boot-starter-webflux` is needed; functional MVC uses `web.servlet.function`.

### 9.2. One Complete Java File

Create file:

```text
src/main/java/com/example/demo/DemoApplication.java
```

Full contents:

```java
package com.example.demo;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
        return RouterFunctions.route()
                .GET("/api/books", handler::list)
                .GET("/api/books/{id}", handler::get)
                .POST("/api/books", handler::create)
                .POST("/api/books/batch", handler::createBatch)
                .onError(IllegalArgumentException.class,
                        (ex, request) -> ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .body(new ApiError("invalid_request")))
                .build();
    }
}

record Book(long id, String title) {
}

record CreateBook(String title) {
}

record ApiError(String error) {
}

@Component
class BookHandler {

    private final AtomicLong nextId = new AtomicLong();
    private final Map<Long, Book> books = new ConcurrentHashMap<>();

    public ServerResponse list(ServerRequest request) {
        int limit = Integer.parseInt(
                request.param("limit").orElse("10"));

        if (limit < 1 || limit > 50) {
            throw new IllegalArgumentException("limit out of range");
        }

        List<Book> result = books.values().stream()
                .sorted(Comparator.comparingLong(Book::id))
                .limit(limit)
                .toList();

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header("Cache-Control", "no-store")
                .body(result);
    }

    public ServerResponse get(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));
        Book found = books.get(id);

        if (found == null) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(found);
    }

    public ServerResponse create(ServerRequest request)
            throws Exception {

        // HttpMessageConverter reads JSON -> CreateBook.
        CreateBook command = request.body(CreateBook.class);
        validate(command);

        long id = nextId.incrementAndGet();
        Book created = new Book(id, command.title().trim());
        books.put(id, created);

        // Location uses a relative URI, not trusting raw Host headers.
        return ServerResponse.created(
                        URI.create("/api/books/" + id))
                .contentType(MediaType.APPLICATION_JSON)
                .body(created);
    }

    public ServerResponse createBatch(ServerRequest request)
            throws Exception {

        // Preserve generic type List<CreateBook> for the JSON converter.
        List<CreateBook> commands = request.body(
                new ParameterizedTypeReference<List<CreateBook>>() {});

        if (commands == null
                || commands.isEmpty()
                || commands.size() > 5) {
            throw new IllegalArgumentException("invalid batch size");
        }

        // Validate all before writing to the map.
        commands.forEach(this::validate);

        List<Book> created = commands.stream()
                .map(command -> {
                    long id = nextId.incrementAndGet();
                    Book book = new Book(id, command.title().trim());
                    books.put(id, book);
                    return book;
                })
                .toList();

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(created);
    }

    private void validate(CreateBook command) {
        if (command == null
                || command.title() == null
                || command.title().isBlank()
                || command.title().length() > 120) {
            throw new IllegalArgumentException("invalid title");
        }
    }
}
```

### 9.3. Checking Self-Containment of the Example

The code resides **in a single Java file** with one public class `DemoApplication` and package-private classes/records. JDK 17 supports `record`, method references, and `Stream.toList()`. `RouterFunctions.route()` calls the exact Servlet MVC package. Body input is parsed via `ServerRequest.body(...)`, and output is written via `ServerResponse.body(...)`. The Jackson converter from the Spring Web starter can serialize records.

The store logic uses `AtomicLong` and `ConcurrentHashMap` to avoid duplicate IDs under concurrent requests; **there is no** atomic transaction across the whole batch and no persistence across restarts. In production, use transactional services/repositories and check permissions/constraints before writing.

The handler does not catch JSON parsing exceptions to turn them into success. The router's `onError(IllegalArgumentException.class,...)` handles only that exception type. Malformed JSON/unreadable converter errors can be handled by Spring exception resolvers with the appropriate status depending on MVC config, though if a uniform error JSON is needed you must add purposeful error handling.

**Routing note:** `POST /api/books/batch` and `GET /api/books/{id}` do not conflict because their HTTP methods differ. If `GET /api/books/batch` is added later, evaluate static vs. variable paths and order/specificity to avoid mapping ambiguity.

### 9.4. Running the Application

At the project root:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell / CMD
mvnw.cmd spring-boot:run
```

The default server URL is `http://localhost:8080` unless `server.port` or the Servlet context path was changed.

### 9.5. Test 1: GET empty list

```bash
curl -i 'http://localhost:8080/api/books'
```

Expected:
- Status `200 OK`.
- `Content-Type: application/json`.
- Body:

```json
[]
```

The store initially has no books; there is no reason to return 404 for a valid empty list. `Cache-Control: no-store` is set by the handler on the list response.

### 9.6. Test 2: POST JSON object to Book

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"Spring MVC.fn"}'
```

Expected:

```http
HTTP/1.1 201
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"Spring MVC.fn"}
```

Note that `1` is the first ID when the app has just started and no other POSTs have occurred; running other tests beforehand produces a different ID. Spring/Jackson may add headers or serialize JSON whitespace differently, so inspect status, Location, and JSON fields instead of comparing raw strings.

### 9.7. Test 3: GET by ID

```bash
curl -i 'http://localhost:8080/api/books/1'
```

When record ID 1 exists, status 200, JSON:

```json
{"id":1,"title":"Spring MVC.fn"}
```

Querying a non-existent ID:

```bash
curl -i 'http://localhost:8080/api/books/99999'
```

Expected status **404 Not Found**. The response body with `ServerResponse.notFound().build()` may be empty depending on error dispatch/container; do not assert a fixed error JSON.

### 9.8. Test 4: POST generic JSON array

```bash
curl -i -X POST 'http://localhost:8080/api/books/batch' \
  -H 'Content-Type: application/json' \
  --data-binary '[{"title":"Java"},{"title":"Spring"}]'
```

Expected status **200 OK**, JSON array with two objects having the next IDs:

```json
[
  {"id":2,"title":"Java"},
  {"id":3,"title":"Spring"}
]
```

These ID numbers assume only the POST from step 2 occurred earlier. This is a classic example proving the converter needs the generic element type to build `List<CreateBook>`.

### 9.9. Test 5: Invalid query limit

```bash
curl -i 'http://localhost:8080/api/books?limit=0'
```

`list()` throws `IllegalArgumentException` and router `onError(...)` returns **400 Bad Request**, body:

```json
{"error":"invalid_request"}
```

Similarly, `limit=abc` raises `NumberFormatException`, which is a subclass of `IllegalArgumentException`, so it is handled by the router error handler. Do not return raw exception details to clients.

### 9.10. Test 6: DTO validation

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"  "}'
```

Expected **400** with the error DTO, because `title.isBlank()` is true. In the example, validation logic uses manual Java checks; a real app should use shared Bean Validation/Validator when complex rules are needed.

### 9.11. Test 7: Malformed JSON error

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":'
```

The Jackson converter cannot parse it; the request must be rejected with no new book created. The actual status is typically **4xx** via MVC exception handling, though the exact error body format must be tested against your Boot/Spring version and global exception configuration. If the API contract requires a fixed error JSON, register an error handler for `HttpMessageNotReadableException` and return 400. Do not expect `{"error":"invalid_request"}` from the router's `onError(IllegalArgumentException)`, because a parse error is not necessarily that type.

### 9.12. Windows PowerShell

Use `curl.exe` (not the `curl` alias when using traditional curl syntax):

```powershell
curl.exe -i "http://localhost:8080/api/books"
curl.exe -i "http://localhost:8080/api/books?limit=5"
```

When sending complex JSON, a reliable approach is creating a UTF-8 `request.json` file:

```json
{"title":"Spring MVC.fn"}
```

Then:

```powershell
curl.exe -i -X POST "http://localhost:8080/api/books" -H "Content-Type: application/json" --data-binary "@request.json"
```

This avoids quote-escaping variations in native commands across PowerShell versions.

## 10. Functional Testing with MockMvc

With Spring Boot 3.5.x, add the test starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Test at `src/test/java/com/example/demo/FunctionalBookTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FunctionalBookTest {

    @Autowired
    MockMvc mvc;

    @Test
    void canCreateAndReadThroughFunctionalRoutes() throws Exception {
        MvcResult created = mvc.perform(
                        post("/api/books")
                                .contentType("application/json")
                                .content("{\"title\":\"Demo\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.title").value("Demo"))
                .andReturn();

        String location =
                created.getResponse().getHeader("Location");

        mvc.perform(get(location))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Demo"));
    }

    @Test
    void invalidInputIsHandledAs400() throws Exception {
        mvc.perform(post("/api/books")
                        .contentType("application/json")
                        .content("{\"title\":\"   \"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("invalid_request"));
    }

    @Test
    void genericBatchReadsTypedList() throws Exception {
        mvc.perform(post("/api/books/batch")
                        .contentType("application/json")
                        .content(
                                "[{\"title\":\"A\"},{\"title\":\"B\"}]"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].title").value("A"))
                .andExpect(jsonPath("$[1].title").value("B"));
    }
}
```

The tests do not assume absolute IDs because the store uses `AtomicLong` and the application context can be reused across tests. The tests only verify routes, converters, status/body, and Location; additional tests are needed for:
- Wrong/missing Content-Type;
- Incompatible Accept and 406/route predicates;
- Malformed JSON;
- Non-numeric path IDs;
- Empty batches and batches over 5 items;
- Authorization/CSRF/rate limits in production;
- Concurrency and persistence if using a database.

Run:

```bash
# Linux / macOS
./mvnw test

# Windows
mvnw.cmd test
```

## 11. Configuring Message Converters When Defaults Are Not Enough

Spring Boot auto-registers converters from the classpath. For ordinary JSON APIs, prefer keeping auto-config and configuring Jackson through Spring Boot-supported properties/beans. Only customize converters for clear needs such as proprietary media types, binary codecs, or specialized serialization.

### 11.1. extendMessageConverters instead of replacing the entire list

```java
@Configuration
class MvcConversionConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        // Check order/type, add or adjust converters
        // while keeping required defaults.
    }
}
```

This is a **configuration snippet**, requiring imports for `@Configuration`, `WebMvcConfigurer`, `HttpMessageConverter`, and `List`. When using `configureMessageConverters(...)` (Spring 6.x style configuration), you can **replace the default configuration** if you do not re-add converters. Note that Spring 7 may have a newer builder-style config API, so do not copy signatures blindly across major versions.

**Recommendation:** if you only want to change Jackson date formats or field naming, configure Jackson rather than replacing the converter list yourself. If CSV is needed, you can write a custom `HttpMessageConverter` with clear canRead/canWrite/MediaType, while accounting for security, streaming, and format parsing.

### 11.2. Converter selection and content negotiation

When reading a request body:

```text
Target: CreateBook.class
Content-Type: application/json
Converter candidate: Jackson JSON
-> canRead(CreateBook.class, application/json)
-> deserialize
```

When writing a response:

```text
Body: Book record
Response contentType: application/json
Converter candidate: Jackson JSON
-> canWrite(Book.class, application/json)
-> serialize
```

When no matching converter exists, MVC cannot succeed merely by calling `.body(value)`. The error can be 415 for an unsupported request media type, 406 for response negotiation, or a server-side converter failure/500 depending on where the failure occurs and the error handler. **Test the actual status and error contract**, rather than assuming every route predicate failure yields 415/406.

### 11.3. Form data is not like a JSON body

For `application/x-www-form-urlencoded`:

```http
POST /api/forms
Content-Type: application/x-www-form-urlencoded

name=Lan&city=Hanoi
```

Form fields are normally exposed via request parameters, unlike a JSON object body. With `ServerRequest.bind(...)` (Spring 6.1+), you can bind request parameters, URI variables, or headers via DataBinder. Example:

```java
CreateProfile form = request.bind(
        CreateProfile.class,
        binder -> binder.setAllowedFields("displayName", "city"));
```

This is a snippet: `CreateProfile` needs to be bindable with an appropriate customizer. `setAllowedFields(...)` restricts fields for DataBinder only; it does not create a JSON allowlist when a handler uses `request.body(CreateProfile.class)` with Jackson. **Never** bind directly onto a JPA entity containing admin/billingId fields.

### 11.4. Multipart file upload

File uploads should not be treated like a JSON DTO containing a massive byte array. For Servlet MVC multipart, check Spring's multipart resolver, `MultipartFile`/`Part`, request size limits, metadata validation, and private storage. With Functional MVC, you may need to access the Servlet multipart API or framework-supported request binding; do not assume `request.body(MyDto.class)` handles files/streams like JSON.

Spring Boot 3.x configuration example:

```properties
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
```

These properties apply to multipart, **not as a universal hard cap** for JSON/all request payloads. Guarding against large JSON requires additional edge/container config or a bounded-read policy.

## 12. Error Handling in Functional MVC

### 12.1. Router-level onError

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/api/items/{id}", handler::get)
        .onError(IllegalArgumentException.class,
                (ex, request) -> ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(new ApiError("invalid_request")))
        .build();
```

This is a snippet using an already defined `handler`. `onError(Class<? extends Throwable>, ...)` applies to matching exceptions arising within the router builder's scope. It is not a replacement for security error handling or all Servlet container exception handling. An exception raised **before** a route is matched or from an outer Servlet Filter does not by default pass through router onError.

### 12.2. Wrapping conversion exceptions selectively

If the contract requires JSON 400 for malformed JSON, you can add an error handler for `HttpMessageNotReadableException`:

```java
.onError(HttpMessageNotReadableException.class,
        (ex, request) -> ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ApiError("malformed_json")))
```

This is a **fragment** added to the router builder and requires importing `org.springframework.http.converter.HttpMessageNotReadableException`. Do not let a generic error handler catch every exception and return 400, because service/DB failures must be classified separately.

### 12.3. Returning errors from the handler instead of throwing

For simple input checks, returning an explicit ServerResponse can be simpler:

```java
if (input == null || input.title() == null) {
    return ServerResponse.badRequest()
            .contentType(MediaType.APPLICATION_JSON)
            .body(new ApiError("title_required"));
}
```

When there are many endpoints, use a shared validation/service layer to avoid repeating rules. Error responses should align with the API contract, such as RFC 9457 Problem Details where appropriate; WebMvc.fn does not automatically catch every domain exception and convert it into your exact desired DTO.

### 12.4. Are @ControllerAdvice and WebMvc.fn the same?

`@ControllerAdvice` is used most strongly with annotated controllers (global `@ExceptionHandler`, `@InitBinder`, `@ModelAttribute`). Functional routing has its own **`before/after/filter/onError`** mechanism. Do not assume every `@ControllerAdvice @ExceptionHandler` automatically covers functional handlers in the exact same order/semantics as `@RequestMapping` methods. Test framework exception resolvers, functional `onError`, and security filters specifically on the exact Spring version you are running.

### 12.5. Committed responses

Once `ServerResponse` begins writing the body and the response is committed, you cannot reliably change the status or write a new JSON error object. For streaming/file output, determine validation, headers, authorization, timeouts, and mid-stream error reporting up front. Even for small JSON DTOs, serialization errors can happen while the converter is writing; do not assume the entire process can always be recovered with status 400.

## 13. Common Implementation Pitfalls

| Symptom | Typical Cause | Fix |
| --- | --- | --- |
| Wrong import `web.reactive.function.server` | Copied a WebFlux.fn example | Use `web.servlet.function` |
| Cannot find `request.bodyToMono()` | WebMvc.fn has `body(Class)`, not bodyToMono | Use the right API; do not add WebFlux needlessly |
| Handler never invoked | `RouterFunction` not registered as a bean, wrong route/predicate | Create `@Bean RouterFunction<ServerResponse>` and test |
| POST JSON returns 404 | Path/method/predicate mismatch | Check routing and contentType/accept predicates |
| `request.body(List.class)` returns `List<Map>` | Generic type erasure | Use `ParameterizedTypeReference<List<Dto>>` |
| Invalid JSON causes 500/unexpected response | Converter exception not mapped properly | Configure appropriate route/onError/global error handling |
| `@Valid` placed somewhere does not run | Bare `request.body(...)` does not auto-validate like annotated MVC | Call Validator/manual validation |
| `String` serialized with wrong type | Mismatched converter/media type | Check Content-Type and converter ordering |
| 415 Unsupported Media Type | Request Content-Type unsupported by converters | Send right media type / add right converter |
| 406 Not Acceptable | Client Accept mismatches representation | Configure produces/negotiation clearly |
| PUT/POST reads an empty body | Servlet filter already consumed the stream | Do not read raw stream early; use bounded cache-on-read |
| 201 missing Location | Response only set status 201 | Use `ServerResponse.created(uri)` |
| 204 when client expects JSON | `noContent().build()` intentionally has no body | Pick 200/201 if a representation is needed |
| Huge JSON request causes heap pressure | Converter allocates huge object graph | Payload size limits/streaming strategy |
| Batch partially writes before full validation | Validation and mutation interleaved | Validate whole batch first, use transaction |
| Multipart upload path traversal | Trusted client's original filename | Server-generated key/private storage |
| Security bypass | Router route exists without auth | Spring Security FilterChain + object ACL |
| @ControllerAdvice fails to catch as expected | Functional router has separate error processing | Use router `onError` or test resolver |
| Code uses `@EnableWebMvc` and loses Boot defaults | Unnecessarily taking over MVC config | Keep Boot auto-config and WebMvcConfigurer |
| Large response buffered/logged as full `byte[]` | Using `readAllBytes`/unbounded response wrapper | Streaming + quotas + bounded observation |

## 14. Security and Resource Limits

WebMvc.fn carries the same attack surface as annotated MVC endpoints:

1. **Authorization:** both `GET /api/books/{id}` and `POST /api/books` must enforce permissions per resource/action; RouterFunction does not provide authentication itself.
2. **Mass assignment:** bind JSON bodies only to **minimal DTOs**, never directly to sensitive domain entities.
3. **DoS/payloads:** limit body size, batch element count, JSON depth, read duration, and concurrent requests at the proxy/container/parser.
4. **CSRF/CORS:** when using session cookies or cross-origin frontends, apply Spring Security CSRF and an accurate CORS allowlist; the HTTP router does not solve them automatically.
5. **Error exposure:** never return raw stack traces, SQL fragments, filesystem paths, or tokens in errors.
6. **Content type:** reject binary/HTML/XML outside the contract; handle MIME sniffing and file uploads separately.
7. **Logging:** log only filtered/redacted metadata; avoid raw Authorization/Cookie/PII-containing bodies.
8. **Transactions:** a handler can call a `@Transactional` service; `RouterFunction` itself does not create atomic transactions.
9. **Timeouts/streaming:** for large bodies or asynchronous publishers, define timeout/error/response-commit policies; WebMvc.fn on the Servlet stack does not turn socket writes into non-blocking WebFlux I/O.
10. **Caching:** if responses are user-specific, use `Cache-Control: private/no-store` and prevent shared caches from mixing data across cookies/headers.

**Do not equate the name Functional with having no side effects:** handlers can mutate DBs, write files, and send emails. Those side effects still require idempotency, validation, permissions, and error recovery just like any other HTTP endpoint.

## 15. QA and Code Review Checklist

- [ ] Correct Spring MVC stack; all primary imports are from `web.servlet.function`.
- [ ] RouterFunction is a Spring bean and route paths/methods/predicates are tested.
- [ ] Handlers use `ServerRequest.body(Class)` or `body(ParameterizedTypeReference)` to parse DTOs.
- [ ] JSON `Content-Type` is valid, JSON converter is present, and custom converters do not break defaults.
- [ ] Query/path params are parsed and value-bounded.
- [ ] Validation is separated from conversion; DTOs contain no client-controlled fields outside the contract.
- [ ] Response status, `Content-Type`, `Location`, `Cache-Control`, and body are valid.
- [ ] 400/404/409/415/406/error policies fit the use case instead of turning every error into 200.
- [ ] Batch inputs have size/quota limits and transactions when performing multiple writes.
- [ ] CORS/CSRF/auth/ACL live in the security architecture rather than relying on route names.
- [ ] MockMvc tests cover success, malformed bodies, generic lists, and negative cases.
- [ ] Never read the same Servlet body twice or log entire payloads unboundedly.
- [ ] Never confuse `ServerResponse.body(Object)` with WebFlux.fn's `bodyValue`/publisher-based API.
- [ ] For files/streams, handle response commit state, buffering, and timeouts.
- [ ] When upgrading to Spring Boot 4/Spring Framework 7, re-verify method signatures, starter/test packages, and converter configuration APIs.

## 16. Self-Check Knowledge Quiz

**Q1.** In WebMvc.fn, which API reads a JSON body into `CreateBook`?

**Answer:** `request.body(CreateBook.class)`. A matching converter (typically Jackson) deserializes the bytes; separate validation is still required.

**Q2.** How do you read a JSON array into `List<CreateBook>` while avoiding `List<Map>`?

**Answer:** `request.body(new ParameterizedTypeReference<List<CreateBook>>() {})` to preserve the generic element type.

**Q3.** Returning `201 Created` with Location and a JSON body?

**Answer:** `ServerResponse.created(URI.create("/api/books/42")).contentType(APPLICATION_JSON).body(book)`.

**Q4.** Returning `204 No Content`?

**Answer:** `ServerResponse.noContent().build()`. No JSON body per 204 semantics.

**Q5.** Does `ServerResponse.ok().body(myPojo)` turn a Java object into JSON without a converter?

**Answer:** No. A write converter compatible with the body type and media type is required.

**Q6.** Why is `request.body(List.class)` not ideal for `List<Book>`?

**Answer:** Type erasure drops the generic element metadata; the converter can create maps instead of Book instances.

**Q7.** Does WebMvc.fn use `bodyToMono()`?

**Answer:** It is not the primary API of Servlet WebMvc.fn; that is a WebFlux.fn API. MVC uses `body(Class)` and `body(ParameterizedTypeReference)`.

**Q8.** Once `request.body(Dto.class)` runs, do Bean Validation and ACLs run automatically?

**Answer:** No. The converter parses data, while validation and authorization must be applied explicitly.

**Q9.** If the `contentType(APPLICATION_JSON)` predicate does not match, is the server guaranteed to return 415?

**Answer:** No. The predicate can cause the router not to find a handler, so the HTTP status depends on mappings/error handling. Write integration tests if exact 415/406 behavior is required.

**Q10.** Why should you test a create endpoint and then GET via `Location` instead of hardcoding ID = 1?

**Answer:** An in-memory store/DB sequence may have incremented from other tests. The Location header reflects the actual ID of the newly created resource.

## 17. Official Documentation

- [Spring Framework 6.2 — Functional Endpoints (WebMvc.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): overview of RouterFunction/HandlerFunction/ServerRequest/ServerResponse, filters, nested routes, and running inside DispatcherServlet.
- [Spring Framework 6.2 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/function/ServerRequest.html): `body(Class)`, `body(ParameterizedTypeReference)`, params, headers, bind.
- [Spring Framework 6.2 — ServerResponse.BodyBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/function/ServerResponse.BodyBuilder.html): `body(Object)`, generic body, response-building.
- [Spring Framework 6.2 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.Builder.html): GET/POST, before/after/filter/onError.
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): converters, JSON/text/form/binary, configuration.
- [Spring Framework 6.2 — MVC Config Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html): `WebMvcConfigurer` and converter customization.
- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): HTTP errors and ProblemDetail.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Spring MVC auto-configuration, HTTP converters, and routing support.
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): to contrast `bodyToMono` and HTTP message codecs, **do not** copy WebFlux-specific imports into Servlet MVC.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain, authentication, authorization, and request processing.

**Conclusion:** in Spring WebMvc.fn, `RouterFunction` finds the route, `HandlerFunction` processes `ServerRequest` and returns `ServerResponse`, and `HttpMessageConverter` converts request/response bodies between bytes and Java values. Read DTOs with `body(Class)`, read generic lists with `body(ParameterizedTypeReference)`, construct status/headers/bodies with `ServerResponse`, and test realistically with MockMvc. Keep conversion separate from validation/security, enforce payload limits, and do not confuse Servlet Functional MVC with Reactive WebFlux.fn.
