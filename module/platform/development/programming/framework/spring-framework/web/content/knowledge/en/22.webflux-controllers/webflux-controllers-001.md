# Annotation-Based Controller Mapping in Spring WebFlux and Commonalities with Spring MVC

> **Scope:** Spring Framework 6.2.x, Spring Boot 3.5.x, Java 17+, annotation-based WebFlux on the reactive HTTP stack. This guide explains `@Controller`, `@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping`; matching URL/HTTP method/params/headers/consumes/produces; reading URI/query/header/body; returning `Mono`, `Flux`, `ResponseEntity`; validation, errors, content negotiation, and testing with `WebTestClient`. It also compares **the shared annotations** with MVC and **the real differences** in dispatching, request-body decoding, I/O, method signatures, and threading. Spring Framework 7/Spring Boot 4 may add APIs (for example version mapping) and rename starter/test packages; the complete example below targets **Boot 3.5 + WebFlux**.

## 1. Same Annotation Syntax, Different Processing Infrastructure

If you have already learned Spring MVC, you will recognize most of the annotations:

```java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{id}")
    Mono<BookView> find(@PathVariable long id) {
        return service.find(id);
    }

    @PostMapping
    Mono<BookView> create(@RequestBody Mono<CreateBook> input) {
        return input.flatMap(service::create);
    }
}
```

**This is a snippet** requiring `service`, DTOs, and imports to be declared; the runnable demo is in section 11. Those annotations from `org.springframework.web.bind.annotation` are also used in Spring MVC. However, WebFlux does **not** use `DispatcherServlet` to run handlers; it uses reactive components such as `DispatcherHandler` and `HandlerMapping` on `ServerWebExchange`.

```text
HTTP request
     |
Reactor Netty / Servlet nonblocking adapter / server runtime
     |
HttpHandler, WebFilter chain
     |
DispatcherHandler                  <-- WebFlux
     |
RequestMappingHandlerMapping      <-- selects @RequestMapping method
     |
RequestMappingHandlerAdapter      <-- resolves method arguments
     |
@Controller/@RestController method
     |
Mono<T> / Flux<T> / ResponseEntity<T>
     |
HandlerResultHandler + HttpMessageWriter
     |
HTTP response
```

**In MVC**, the corresponding path is `DispatcherServlet` → `HandlerMapping` → `HandlerAdapter` → `HttpMessageConverter` → Servlet response. **In WebFlux**, reading/writing the body uses `HttpMessageReader`/`HttpMessageWriter` from reactive codecs, and the request is processed through reactive HTTP abstractions.

### 1.1. Key Commonalities Worth Remembering

Both WebFlux and MVC support:
- `@Controller` and `@RestController` (`@Controller` + `@ResponseBody`);
- declaring routes with `@RequestMapping` and HTTP-method shortcut annotations;
- URI templates `/{id}`, regex path variables, `@PathVariable`;
- `@RequestParam`, `@RequestHeader`, `@CookieValue`;
- `@RequestBody` and `@ResponseBody`;
- `ResponseEntity`, `@ResponseStatus`;
- Bean Validation, `@ControllerAdvice`/`@ExceptionHandler`;
- `@CrossOrigin`/CORS, content negotiation, and conversion;
- `@ModelAttribute` for form/model binding (with runtime differences).

They share many annotations from the **spring-web module**, making request-handling code look very similar. **Do not infer the runtime solely from annotation names:** a controller returning `Mono<T>` can still be running on Servlet MVC if Boot selects the WebMvc stack.

### 1.2. Core Differences

| Topic | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Web model | Servlet API; supports blocking I/O | Reactive Streams, non-blocking HTTP I/O when supported by the runtime |
| Common servers | Tomcat/Jetty Servlet | Reactor Netty; other adapters also supported |
| Request abstraction | `HttpServletRequest` | `ServerWebExchange`/`ServerHttpRequest` |
| HTTP body reading | `HttpMessageConverter` | `HttpMessageReader` reactive codecs |
| HTTP body writing | `HttpMessageConverter`; Servlet output writes can block | Reactive `HttpMessageWriter` |
| `@RequestBody Mono<T>` | Not the equivalent reactive body-reading pattern | **Supported** |
| Returning `Mono/Flux` | Supported via adapters and Servlet async | Native reactive pipeline |
| Blocking JDBC/JPA | Relatively natural fit for the MVC thread model | Should not block the event-loop; consider R2DBC/boundedElastic |
| Functional API | `web.servlet.function` | `web.reactive.function.server` |

WebFlux does not mean an ordinary Java operation automatically becomes async. `Flux.just(...)` and `Mono.just(...)` may emit immediately on the subscription thread; WebClient/reactive drivers provide real async I/O. The infrastructure will not fix a `Thread.sleep(5000)` placed inside a controller.

## 2. @Controller and @RestController

### 2.1. @RestController for JSON/HTTP Body APIs

```java
@RestController
class HelloController {
    @GetMapping("/hello")
    Mono<String> hello() {
        return Mono.just("Hello WebFlux");
    }
}
```

With `@RestController`, the return value is written to the response body; a `String` is content, **not a view name**. The `Mono<String>` type is subscribed to by WebFlux and then encoded when the value is emitted.

### 2.2. @Controller for View Rendering or @ResponseBody

```java
@Controller
class PageController {
    @GetMapping("/welcome")
    String page(Model model) {
        model.addAttribute("title", "Welcome");
        return "welcome";
    }
}
```

This is a snippet requiring a view resolver and a `welcome` template. A `String` returned from a plain `@Controller` is interpreted as a **view name**, unless the method has `@ResponseBody`. To return JSON on a `@Controller` class:

```java
@ResponseBody
@GetMapping("/api/ping")
Mono<Map<String,String>> ping() {
    return Mono.just(Map.of("status", "ok"));
}
```

Do not confuse `@ResponseBody` with `@RequestBody`: the former applies to the **response**, while the latter reads the **request**.

## 3. @RequestMapping at Class and Method Levels

`@RequestMapping` can declare:
- `path`/`value`;
- `method` (HTTP method);
- `params` (query parameter conditions);
- `headers`;
- `consumes` (request Content-Type);
- `produces` (response media type).

```java
@RestController
@RequestMapping("/api/books")
class BooksController {

    @GetMapping("/{id}")
    Mono<BookView> get(@PathVariable long id) {
        // ...
    }

    @PostMapping(consumes="application/json",
                 produces="application/json")
    Mono<BookView> create(@RequestBody Mono<CreateBook> body) {
        // ...
    }
}
```

Method mappings inherit the `/api/books` prefix from the type level:
- GET `/api/books/10`;
- POST `/api/books` with JSON Content-Type, able to return JSON when the client's Accept header matches.

**Do not use `@RequestMapping` with an empty `method` when you only want GET**, because that annotation does not restrict the HTTP method by default. For REST, prefer `@GetMapping`/`@PostMapping`/... to reduce unintended surface area.

### 3.1. Shortcut Annotations

| Annotation | HTTP method | Application meaning |
| --- | --- | --- |
| `@GetMapping` | GET | Read data |
| `@PostMapping` | POST | Create/trigger action |
| `@PutMapping` | PUT | Replace representation |
| `@PatchMapping` | PATCH | Partial modification |
| `@DeleteMapping` | DELETE | Delete |
| `@RequestMapping(method=RequestMethod.HEAD)` | HEAD | If a custom HEAD route is needed |

They are **composed annotations** based on `@RequestMapping`. Avoid placing **two mapping annotations** on the same element (for example `@GetMapping` and `@PostMapping` on the same method) because Spring picks only one mapping and may warn. If you want one method to serve multiple verbs, declare a single `@RequestMapping(method={RequestMethod.GET, RequestMethod.POST})` with a clear reason or split into separate methods.

### 3.2. HTTP HEAD and OPTIONS

According to the Spring WebFlux reference:
- `@GetMapping` automatically supports the corresponding HEAD without usually needing a separate method; the response handles `Content-Length` and **sends no body**.
- OPTIONS by default may return `Allow` listing the HTTP methods mapped to the URL, unless the application provides custom handling.
- With a `@RequestMapping` that does not specify a method, Allow may include many unintended HTTP verbs; therefore, explicitly specify the real verb.

Do not assume from a normal GET response that HEAD will carry the same body; HEAD carries metadata only. CORS preflight OPTIONS also involves CORS configuration and other security filters.

## 4. URI Templates and Path Patterns

### 4.1. Reading Path Variables

```java
@GetMapping("/{bookId}")
public Mono<BookView> get(
        @PathVariable("bookId") long bookId) {
    return repository.findById(bookId)
            .map(BookView::from);
}
```

The snippet requires a reactive repository/DTO. For URL `/api/books/42`, `bookId=42`. The String is converted to `long` via type conversion; path `/api/books/abc` causes a conversion error rather than silently becoming `0`.

Specifying the explicit name `@PathVariable("bookId")` is helpful if the project is not compiled with `-parameters` or if the Java variable name differs from the URI template name.

### 4.2. PathPatternParser in WebFlux

Spring WebFlux uses `PathPattern`/`PathPatternParser`. Some examples:

| Pattern | Example match | Non-match / notes |
| --- | --- | --- |
| `/books/{id}` | `/books/42` | `/books/42/reviews` |
| `/files/*.png` | `/files/a.png` | `/files/a/b.png` |
| `/books/{name:[a-z-]+}` | `/books/spring-web` | `/books/Spring123` |
| `/assets/**` | `/assets/a/b.png` | Catch-all, so less specific |
| `/assets/{*path}` | `/assets/a/b.png`, captures the tail | Catch-all placed at the end of the pattern |

Do not use `/**/info` or a catch-all in the **middle** as a valid pattern under PathPattern rules. If multiple mappings can match, Spring compares specificity; static paths usually take precedence over corresponding variable/catch-all patterns. Avoid ambiguous mappings with equal precedence that prevent the application from selecting a handler.

### 4.3. No Default Suffix Matching

WebFlux does not apply legacy suffix path matching such as `/person` automatically matching `/person.json`. Use `Accept`, `produces`, or an explicitly documented query param if another representation is needed. Do not treat a `.json` suffix in the URL as safe content negotiation by default.

### 4.4. Prefix at a Reverse Proxy

If a proxy publishes `/portal/api/books` while the backend only matches `/api/books`, that is a proxy route rewrite/path prefix issue—not `@GetMapping` knowing the external prefix automatically. Configure the gateway and forwarded headers according to the trust boundary; do not blindly take raw client-sent `X-Forwarded-Prefix` and concatenate URIs. Test real public URLs as well as links/redirects when a prefix is present.

## 5. Conditions: params, headers, consumes, and produces

### 5.1. params: Condition for Method Selection, Not an Argument Value

```java
@GetMapping(path = "/search", params = "mode=featured")
Mono<List<BookView>> featured() {
    return service.featured().collectList();
}
```

The mapping above is only considered when the query contains `mode=featured`. Similarly:
- `params="q"`: query param q must be present;
- `params="!q"`: q must not be present;
- `params="mode=featured"`: exact specific value.

Meanwhile:

```java
@GetMapping("/search")
Mono<List<BookView>> search(
        @RequestParam(name = "q", required = false) String q) {
    return service.search(q).collectList();
}
```

`@RequestParam` on a parameter **reads the value**; if `required=true`, a missing parameter causes an argument resolution error. The two concepts—“params mapping condition” and “@RequestParam binding”—are related but not identical. If two mappings overlap, Spring selects the more specific mapping using its condition comparator rather than simply letting "the method declared first win."

### 5.2. headers

```java
@GetMapping(path="/internal-report",
            headers="X-Client-Type=partner")
Mono<ReportView> report() {
    return service.report();
}
```

This is a snippet; it requires the `X-Client-Type: partner` header for the route to match. **This is not security:** a client can set the header itself; do not use it in place of authentication, roles, or tenant authorization. Use Spring Security and object-level ACLs.

### 5.3. consumes: Request Content-Type

```java
@PostMapping(path="/api/books",
             consumes=MediaType.APPLICATION_JSON_VALUE)
Mono<Void> ingest(@RequestBody Mono<CreateBook> command) {
    return command.flatMap(service::save).then();
}
```

`consumes` narrows by Content-Type (for example application/json). Sending `text/plain` to a route that only accepts JSON usually results in **415 Unsupported Media Type**, depending on other mappings/error handling. Do not use `consumes` to check the response type.

### 5.4. produces: Response Accept

```java
@GetMapping(path="/api/books",
            produces=MediaType.APPLICATION_JSON_VALUE)
Flux<BookView> books() {
    return service.findAll();
}
```

`produces` states that the controller can produce JSON; a client with `Accept: application/json` or `*/*` usually matches. If the client only accepts `application/xml` while the API only supports JSON, the HTTP status may be **406 Not Acceptable**. `produces` affects mapping/negotiation, but it does not automatically install an XML codec or guarantee that a Java type serializes to JSON.

### 5.5. Relationship Between consumes and produces

| Client header | Controller mapping | Purpose |
| --- | --- | --- |
| `Content-Type: application/json` | `consumes="application/json"` | Read JSON request |
| `Accept: application/json` | `produces="application/json"` | Return JSON response |
| `Content-Type: text/plain` | JSON-only consumes | Usually 415 |
| `Accept: application/xml` | JSON-only produces | Usually 406 |
| `X-Mode: admin` | `headers="X-Mode=admin"` | Routing condition only, not authorization |

In `@RequestMapping`, method-level `consumes`/`produces` may **override**, rather than necessarily merging like other mapping conditions from the class level. For `headers` and `params`, understand how conditions combine according to framework rules and test with real HTTP requests to avoid misjudging precedence.

## 6. Reading Request Input via WebFlux Annotated Arguments

Annotations for reading URI, query, header, and cookie values have **syntax familiar from MVC**. In WebFlux, the `ServerWebExchange` argument and reactive body arguments show the clearest differences:

| Need | Appropriate WebFlux approach | Difference from MVC |
| --- | --- | --- |
| ID from URI | `@PathVariable("id") long id` | Reads route metadata; no need to wrap in `Mono<Long>` |
| Query, header, cookie | `@RequestParam`, `@RequestHeader`, `@CookieValue` | WebFlux `@RequestParam` reads **query** parameters only, rather than implicitly merging form/multipart data like Servlet request parameters |
| Inspect full HTTP exchange | `ServerWebExchange` / `ServerHttpRequest` | Do not inject MVC's `HttpServletRequest` into a WebFlux annotated handler |
| JSON request body | `@RequestBody Mono<Command>` | Uses `HttpMessageReader`/decoder by publisher when WebFlux is actually active |
| Form/multipart | `exchange.getFormData()`, `@RequestPart`, `FilePart` | Separate parser path; do not treat form/multipart as a JSON request body |
| Principal | `Mono<Principal>`, `exchange.getPrincipal()` | Identity must be authenticated by the security chain; do not trust client-sent `X-User` |

Example keeping routing and body mechanisms in one method:

```java
@PostMapping(path = "/api/books", consumes = "application/json")
Mono<BookView> create(
        @RequestHeader(name = "X-Trace", required = false) String trace,
        @RequestBody Mono<CreateBook> body) {
    // Trace is untrusted metadata and must not be used as a credential.
    return body.flatMap(service::create);
}
```

This is a **snippet** requiring `service`, DTOs, and imports. In WebFlux, `@RequestBody Mono<CreateBook>` is decoded by the framework from the HTTP body publisher; it is not a binding style shared with Servlet MVC. Conversely, `@PathVariable`/`@RequestParam` are resolved from URI/query metadata, so do not arbitrarily wrap them in a reactive publisher.

The dedicated article on **`ServerWebExchange` and parameters** in this chapter explains repeated query values, attributes, principal, session, form/multipart APIs, and binding errors in detail. This article focuses on **mapping selecting the right handler first** before each argument is resolved.

## 7. Choosing Reactive Return Types and HTTP Responses

The return type is also part of the API contract. In annotated WebFlux, a publisher represents **data availability**, while status/headers may be determined at a different time:

| Return type | When is it decided? | Recommended use |
| --- | --- | --- |
| `BookView` / `Mono<BookView>` | Body is typically encoded when a result arrives | 200 with one DTO |
| `Flux<BookView>` | 0..N values; codec depends on media type | Collection or reactive stream |
| `ResponseEntity<BookView>` | Status/headers/body known immediately | 201, 204, explicit headers |
| `Mono<ResponseEntity<BookView>>` | Status/headers chosen **after** async lookup | 200/404 based on data |
| `ResponseEntity<Flux<BookView>>` | Early status/headers, streamed body later | SSE, NDJSON, data stream |
| `Mono<Void>` | Completes/errors without emitting a value | Operation returning no representation |

Two types most easily confused:

```java
// 200 or 404 is decided only when the lookup emits a result.
Mono<ResponseEntity<BookView>> deferred = service.find(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());

// 202 is decided immediately; Mono only represents the body emitted later.
ResponseEntity<Mono<BookView>> immediate =
        ResponseEntity.accepted().body(service.find(id));
```

These are snippets using an existing `service`/`id`. `Mono.empty()` **does not automatically mean 404** in every contract; an API wanting 404 should map it to `ResponseEntity.notFound()` or emit an appropriate `ResponseStatusException`. Nor does `Flux` **guarantee** that each element reaches the browser immediately: the media type (JSON array/SSE/NDJSON), codec, server, and proxy buffering determine actual streaming behavior.

Example `201 + Location`:

```java
return service.create(command)
        .map(saved -> ResponseEntity
                .created(URI.create("/api/books/" + saved.id()))
                .body(saved));
```

Only construct absolute public URLs from a trusted origin/proxy, never from raw `Host` or `X-Forwarded-Host`. The article `@RequestBody with Mono/Flux and ResponseEntity` goes deeper into JSON/NDJSON wire formats, backpressure, cancellation, error operators, and the properties of each publisher combination.

## 8. Validation and HTTP Errors in Annotated WebFlux

Route annotations **do not validate input content**. `@Valid @RequestBody Mono<Dto>` can trigger Bean Validation after the decoder creates the DTO if the project has a validation provider and constraints such as `@NotBlank`. Spring WebFlux 6.1+ distinguishes validation errors on a single argument (typically `WebExchangeBindException`) from method validation (typically `HandlerMethodValidationException`). Without a validator/constraints, simply adding `@Valid` does not enforce a policy.

```java
@PostMapping("/api/books")
Mono<ResponseEntity<BookView>> create(
        @Valid @RequestBody Mono<CreateBook> body) {
    return body.flatMap(service::create)
            .map(saved -> ResponseEntity
                    .created(URI.create("/api/books/" + saved.id()))
                    .body(saved));
}
```

This is an illustrative method inside a controller that has `service`, DTOs, and imports. **The runnable version in section 11** intentionally uses manual validation so no validation starter is needed; to apply the `@Valid` snippet above, you must provide the corresponding annotations and validation provider.

HTTP error handling should have **clear ownership layers**:

- Malformed JSON request, wrong Content-Type, conversion failure, or missing field: distinguish decoder/binding errors before business logic, usually an appropriate 400/415.
- Entity not found: map `Mono.empty()` to 404 per the API contract, rather than returning an empty 200 if callers need to detect absence.
- Business logic raising meaningful exceptions: use `Mono.error(...)` or `ResponseStatusException`, and `@ExceptionHandler`/`@RestControllerAdvice` if a unified error representation is needed.
- Filters, authentication, gateways, and already-committed response streams have **different error boundaries**; controller advice is not guaranteed to catch all of them.
- Do not include exception messages containing secrets, raw user input, stack traces, or internal paths in error JSON.

The article on **binding/Bean Validation** analyzes input error types and groups/custom validators; the article on **ProblemDetail/@RestControllerAdvice** analyzes RFC 9457, error-handling scope, and status after response commit. In this routing article, simply remember that mapping, decoding, validation, and business failure are **distinct phases**.

## 9. Rules for Selecting a Handler with Multiple Mappings

Mapping conditions act together:
- URL path matching;
- HTTP verb;
- query params;
- headers;
- consumes/request Content-Type;
- produces/Accept.

The same path can have separate GET and POST handlers. Two GETs on `/books` can be distinguished by `params="view=full"` or `produces`; however, ambiguous overlap can still occur if the conditions are not distinct enough. Spring uses a comparator with specificity rules, **not the order of methods in source code**.

### 9.1. Static Path vs Variable Path

```java
@GetMapping("/api/books/featured")
Mono<List<BookView>> featured() {
    return service.featured().collectList();
}

@GetMapping("/api/books/{id}")
Mono<BookView> byId(@PathVariable long id) {
    return service.find(id);
}
```

On GET `/api/books/featured`, the static path is generally more specific than the variable path. Even so, you should not leave a variable endpoint expecting a numeric `id` without a regex when multiple aliases exist; you can constrain it:

```java
@GetMapping("/api/books/{id:\\d+}")
Mono<BookView> byNumericId(@PathVariable long id) {
    return service.find(id);
}
```

In a Java string literal, the backslash must be escaped as `\\d+` so the pattern receives `\d+`. This example is a snippet; when copying in an IDE, make sure the literal has the correct escape characters.

### 9.2. Ambiguous Mapping

If two methods have the same `@GetMapping("/api/books")` without distinguishing conditions, it can cause a startup failure or handler selection error depending on timing/framework configuration. The fix is not to rely on class/file names, but to define a concrete route contract: separate the path, method, params/headers/media type, or remove the duplicate.

### 9.3. @RequestMapping on Interfaces

Spring supports annotations on controller interfaces in many cases, though proxying (JDK vs class-based), mixing annotations between implementation and interface, and handler detection have caveats. If you define the API contract on a Java interface, place mapping/parameter annotations consistently and test handler detection rather than arbitrarily duplicating the same annotations onto the implementation.

### 9.4. API Versioning

Spring Framework 7 provides a `version` attribute on request mappings and the ability to configure an API version resolver for WebFlux. **Do not use this new API in Spring Framework 6.2 / Boot 3.5**, because the code will not compile. On the 6.2 stack, versioned routes usually use `/api/v1/books`, header conditions, media types, or a custom strategy. If upgrading to Spring 7, read the corresponding API version strategy/version deprecation docs instead of just adding `version="1.0"` to an older project.

## 10. Important Boundaries Between WebFlux and MVC

### 10.1. Adding the WebFlux Starter Does Not Guarantee the WebFlux Server Is Active

Spring Boot 3.5 docs state: if a project has both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Boot **prefers auto-configuring Spring MVC** because many applications use WebClient inside an MVC app. For a true WebFlux demo, use only:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

If a project intentionally needs the reactive web type even with both starters present, you can configure `SpringApplication.setWebApplicationType(WebApplicationType.REACTIVE)`, though do not treat that as a substitute for analyzing dependencies/configuration. Verify that DispatcherHandler/WebFlux codecs are actually being used.

### 10.2. Do Not Run Blocking Operations on the Event-Loop

```java
// Anti-pattern in a WebFlux controller.
@GetMapping("/blocking")
Mono<BookView> bad() {
    return Mono.just(jdbcRepository.findBook(42));
}
```

The call `jdbcRepository.findBook(42)` executes **before** the Mono is created and can block the request event-loop. Similarly, `Mono.fromCallable(...)` does not switch threads on its own. A bounded bridge looks like:

```java
Mono<BookView> safer = Mono
        .fromCallable(() -> jdbcRepository.findBook(42))
        .subscribeOn(Schedulers.boundedElastic());
```

This is only an adapter for blocking code; it does not make JDBC non-blocking. For applications centered on JPA/JDBC, Spring MVC may be simpler and more suitable. For high-concurrency WebFlux, prefer reactive HTTP clients/drivers, and consider boundedElastic quotas and overload protection.

### 10.3. Servlet Filters vs WebFilter

In MVC, authentication/tracing may use `jakarta.servlet.Filter` and `OncePerRequestFilter`. In WebFlux, use `org.springframework.web.server.WebFilter` and Spring Security's **reactive SecurityWebFilterChain** matching the stack. Do not copy a Servlet Filter and expect it to run automatically in a Netty WebFlux app.

### 10.4. ThreadLocal Does Not Automatically Propagate Across Reactive Boundaries

MVC's `SecurityContextHolder`, MDC, LocaleContextHolder, and request-scoped ThreadLocals are not guaranteed to be present on Reactor schedulers. WebFlux typically uses Reactor Context/context propagation and the Spring Security reactive context; principal/tenant data must be accessed via the appropriate APIs. Never let the client choose a tenant ID from a header when authorization is missing.

### 10.5. Data Binding Differs from JSON Body Decoding

`@ModelAttribute` binds request parameters/URI variables into a model; `@RequestBody` deserializes the HTTP body using a codec. Use explicit DTOs and accept only fields belonging to the contract; Spring Boot/WebFlux supports constructor binding and validators, yet you **should not bind JPA entities directly** containing server-managed fields like `role`, `ownerId`, or `price`.

## 11. Complete Demo: Spring Boot 3.5 / Java 17 / WebFlux

Create a Books REST API using WebFlux annotations, with:
- GET `/api/books`: returns a JSON Flux;
- GET `/api/books/{id}`: returns Mono<ResponseEntity<BookView>>, choosing 200/404;
- GET `/api/books/search?mode=featured`: mapping with `params`;
- POST `/api/books`: accepts `@RequestBody Mono<CreateBook>`, validates, and returns 201 + Location;
- PUT `/api/books/{id}`: replaces title, returns 200/404;
- DELETE `/api/books/{id}`: returns 204/404.

The store is an in-memory ConcurrentHashMap, sufficient to demonstrate routing/binding/responses; it is not a production persistence or auth solution.

### 11.1. Project Dependency

From [Spring Initializr](https://start.spring.io/), create a Maven project with **Spring Boot 3.5.x**, **Java 17+**, and the **Spring Reactive Web** dependency. In the `pom.xml` generated by Initializr, the dependency is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

This is a **POM fragment**; Initializr provides the full parent/BOM/plugins. Reactor Core/Jackson/WebFlux/Reactor Netty are pulled in by the starter. Do not add `spring-boot-starter-web`.

### 11.2. Standalone DemoApplication.java File

Save the **entire** snippet below into `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record BookView(long id, String title) {}
record CreateBook(String title) {}

@Service
class BookStore {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, BookView> books =
            new ConcurrentHashMap<>();

    Flux<BookView> list(int limit) {
        return Flux.defer(() -> Flux.fromIterable(
                books.values().stream()
                        .sorted(Comparator.comparingLong(BookView::id))
                        .limit(limit)
                        .toList()));
    }

    Mono<BookView> find(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(books.get(id)));
    }

    Mono<BookView> create(CreateBook command) {
        return Mono.fromSupplier(() -> {
            long id = nextId.incrementAndGet();
            BookView saved = new BookView(
                    id, command.title().trim());
            books.put(id, saved);
            return saved;
        });
    }

    Mono<BookView> replace(long id, CreateBook command) {
        return Mono.defer(() -> Mono.justOrEmpty(
                books.computeIfPresent(
                        id,
                        (key, previous) ->
                                new BookView(id, command.title().trim()))));
    }

    Mono<Boolean> delete(long id) {
        return Mono.fromSupplier(() -> books.remove(id) != null);
    }
}

@RestController
@RequestMapping(path = "/api/books")
class BookController {

    private final BookStore store;

    BookController(BookStore store) {
        this.store = store;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<BookView> list(
            @RequestParam(name = "limit", defaultValue = "20") int limit) {

        if (limit < 1 || limit > 100) {
            return Flux.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "limit must be 1..100"));
        }

        return store.list(limit);
    }

    @GetMapping(path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<BookView>> get(
            @PathVariable("id") long id) {

        return store.find(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping(path = "/search", params = "mode=featured",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<BookView> featured() {
        // Query param mode=featured is the mapping selection condition.
        return store.list(5);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<BookView>> create(
            @RequestBody Mono<CreateBook> body) {

        return body
                .switchIfEmpty(Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "JSON body required")))
                .flatMap(command -> {
                    validate(command);
                    return store.create(command);
                })
                .map(saved -> ResponseEntity
                        .created(URI.create("/api/books/" + saved.id()))
                        .body(saved));
    }

    @PutMapping(path = "/{id}",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<BookView>> replace(
            @PathVariable("id") long id,
            @RequestBody Mono<CreateBook> body) {

        return body
                .switchIfEmpty(Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "JSON body required")))
                .flatMap(command -> {
                    validate(command);
                    return store.replace(id, command);
                })
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @DeleteMapping("/{id}")
    public Mono<ResponseEntity<Void>> delete(
            @PathVariable("id") long id) {
        return store.delete(id)
                .map(deleted -> deleted
                        ? ResponseEntity.<Void>noContent().build()
                        : ResponseEntity.<Void>notFound().build());
    }

    private static void validate(CreateBook command) {
        if (command == null
                || command.title() == null
                || command.title().isBlank()
                || command.title().length() > 120) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "title is required (1..120 characters)");
        }
    }
}
```

### 11.3. Runnability Notes and Limitations

- A Java file has exactly one public class `DemoApplication`; the remaining `record` and component classes are package-private, which is valid in Java 17.
- `@SpringBootApplication` component scanning finds `BookStore`/`BookController` because they are in the same package.
- The project uses `spring-boot-starter-webflux` and no MVC starter, so it runs the WebFlux server by default (usually Reactor Netty).
- `BookStore` uses `ConcurrentHashMap` and `AtomicLong`; that is in-memory synchronization for demo purposes, **not a reactive database**. Every operation here is tiny and performs no blocking I/O; `Mono.defer/Mono.fromSupplier` only defers work until subscription and **does not make I/O non-blocking on its own**.
- `GET /api/books` uses `Flux.defer` to create a list snapshot on subscription, sorted by ID; a production database should use a reactive repository/R2DBC with pagination.
- `@RequestBody Mono<CreateBook>` demonstrates WebFlux's distinctive API. It uses only a minimal JSON DTO; do not bind entities containing sensitive fields directly.
- `Mono<ResponseEntity<BookView>>` allows deciding between 200 and 404 based on the async result.
- `POST` uses `ResponseEntity.created(...)` to return status 201 + a relative Location.
- `PUT` replaces a title on an in-memory record; it is an example of **replacing a simple representation** without ETag/If-Match. If multiple clients edit concurrently, optimistic versioning in the DB is required to avoid lost updates.
- There is no authentication, CSRF, CORS, database, transactions, or metrics; **do not deploy the demo as a public production API**.
- All methods use explicit HTTP annotations; class-level `@RequestMapping` acts only as a prefix.

### 11.4. Running the Server

In the root of the project generated by Initializr:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows (PowerShell/CMD)
mvnw.cmd spring-boot:run
```

If the port is unchanged, the server listens on `http://localhost:8080`.

### 11.5. GET Empty List

```bash
curl -i -H 'Accept: application/json' \
  'http://localhost:8080/api/books?limit=10'
```

Expected status 200, JSON body:

```json
[]
```

An empty list is a valid response; 404 is not needed. The JSON Content-Type header is determined via `produces` and the codec.

### 11.6. POST Create Book

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"title":"Spring WebFlux"}'
```

Expected output after a fresh startup with no prior creates:

```http
HTTP/1.1 201 Created
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"Spring WebFlux"}
```

Headers such as Date/Transfer-Encoding and JSON whitespace may vary by runtime. If other books have already been created, the ID will not necessarily be 1. The HTTP Location should be read from the actual response header.

### 11.7. GET by ID, 404

```bash
curl -i 'http://localhost:8080/api/books/1'
curl -i 'http://localhost:8080/api/books/9999'
```

When ID 1 exists, the response is 200 JSON `{"id":1,"title":"Spring WebFlux"}`. When ID 9999 does not exist, the status is **404** because of `defaultIfEmpty(ResponseEntity.notFound().build())`.

This differs from simply returning `Mono.empty()`: the API explicitly specifies status 404.

### 11.8. GET Search by params Condition

```bash
curl -i 'http://localhost:8080/api/books/search?mode=featured'
```

The `/search` route has the `mode=featured` query condition and a specific static path. The handler returns at most 5 records. Without `mode=featured`, that mapping does not match; the actual status depends on remaining mappings and error handling, so do not assume `featured()` will be invoked.

### 11.9. PUT Replace Content

```bash
curl -i -X PUT 'http://localhost:8080/api/books/1' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"title":"WebFlux Updated"}'
```

If the ID exists: status **200**, JSON body with the new title. If the ID does not exist: status **404**. If the title is blank or longer than 120 characters: **400** from manual validation.

**Business-logic note:** the example omits If-Match/ETag, so lost updates can occur under concurrent edits. In a real project, add version/CAS/optimistic locking instead of relying on reactive return types to prevent races.

### 11.10. DELETE

```bash
curl -i -X DELETE 'http://localhost:8080/api/books/1'
```

The first time if ID 1 exists: **204 No Content**. Sending the same ID again after deletion: **404 Not Found** per the demo contract. Do not expect a JSON body on 204.

### 11.11. Error Cases

**Invalid limit:**

```bash
curl -i 'http://localhost:8080/api/books?limit=0'
```

Expected status 400 (range check). With `limit=xyz`, argument conversion can return 400 before entering the method.

**JSON missing title:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{}'
```

Expected 400. Manual validation in `validate` does not depend on bean-validation starter.

**Wrong Content-Type:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: text/plain' \
  --data-binary 'hello'
```

Because of `@PostMapping(consumes="application/json")`, the response is usually **415** if no other mapping matches.

**Unsupported Accept:**

```bash
curl -i -H 'Accept: application/xml' \
  'http://localhost:8080/api/books'
```

The mapping `produces="application/json"` does not accept XML-only, so it usually returns **406 Not Acceptable**, unless another XML route exists.

### 11.12. Windows PowerShell and curl

PowerShell may alias `curl` to its own cmdlet. Use `curl.exe`:

```powershell
curl.exe -i "http://localhost:8080/api/books?limit=10"
curl.exe -i "http://localhost:8080/api/books/9999"
```

For JSON requests, create a UTF-8 file `request.json`:

```json
{"title":"Spring WebFlux"}
```

Send:

```powershell
curl.exe -i -X POST "http://localhost:8080/api/books" -H "Content-Type: application/json" -H "Accept: application/json" --data-binary "@request.json"
```

This avoids native-process quote-escaping differences across PowerShell versions.

## 12. Testing WebFlux with WebTestClient

### 12.1. Dependencies

Add the test starter for Spring Boot **3.5**:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

This is a POM fragment. For Boot 4 code, check the modular test starters and new package imports; do not arbitrarily mix Boot 3 imports into Boot 4.

### 12.2. WebTestClient Integration Test

Save `src/test/java/com/example/demo/BookControllerTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BookControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void canCreateAndRead() {
        String location = client.post()
                .uri("/api/books")
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .accept(org.springframework.http.MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"WebFlux Test\"}")
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody()
                .jsonPath("$.title").isEqualTo("WebFlux Test")
                .returnResult()
                .getResponseHeaders()
                .getLocation()
                .toString();

        client.get().uri(location)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("WebFlux Test");
    }

    @Test
    void missingBookReturns404() {
        client.get().uri("/api/books/999999")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void badTitleReturns400() {
        client.post().uri("/api/books")
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"   \"}")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void wrongContentTypeIsRejected() {
        client.post().uri("/api/books")
                .contentType(org.springframework.http.MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isEqualTo(415);
    }

    @Test
    void wrongAcceptIsRejected() {
        client.get().uri("/api/books")
                .accept(org.springframework.http.MediaType.APPLICATION_XML)
                .exchange()
                .expectStatus().isEqualTo(406);
    }

    @Test
    void badLimitReturns400() {
        client.get().uri("/api/books?limit=0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

**Important note about this test:** the `EntityExchangeResult<byte[]> result = ...expectBody().returnResult()` API has a `getResponseHeaders()` method to read Location. `getLocation()` returns a URI when the header is present; if the test lacks Location, the earlier assertion fails. Tests do not hardcode ID=1 because the in-memory store may already hold rows from other POST tests in the same context.

`WebTestClient` can run against a real server as in the RANDOM_PORT test or bind-to-controller/router; this example uses RANDOM_PORT to test the full network/server/reactive codecs stack.

### 12.3. Additional Checks Needed

- `GET /api/books/search?mode=featured` matches properly and is not swallowed by the variable path.
- Duplicate/conflicting mappings do not occur.
- HEAD/OPTIONS behaviors follow the WebFlux contract.
- Malformed JSON and oversized requests do not return 200.
- Params/header conditions: present/absent/wrong value.
- Query/path conversion errors and error bodies.
- Bean Validation (if adding `@Valid`/constraints).
- Authentication/authorization/CORS/CSRF when securing endpoints.
- SSE/NDJSON according to `produces` and response streaming/cancellation.
- Concurrent writes and optimistic versioning in the DB, not only testing an in-memory map.

### 12.4. Running Tests

```bash
# Linux/macOS
./mvnw test

# Windows
mvnw.cmd test
```

If CI runs tests in parallel sharing in-memory state, do not assert hardcoded IDs or delete resources owned by another test. Use test fixtures/isolated contexts or appropriate test database rollback/cleanup.

## 13. Common Mistakes When Migrating MVC Controllers to WebFlux

| Symptom | Cause | Fix |
| --- | --- | --- |
| Controller looks like WebFlux but runs MVC | Project has both web and webflux starters | Check web application type, explicitly select WebFlux server |
| `@RequestBody Mono<T>` does not work | Servlet MVC is handling the request | Use the proper WebFlux stack or a synchronous DTO for MVC |
| `HttpServletRequest` fails to resolve | WebFlux does not use Servlet API as a general abstraction | Use `ServerWebExchange`/`ServerHttpRequest` |
| `@GetMapping` does not match | Wrong class path + method path, version, or path pattern | Test actual URI, method, and conditions |
| GET/POST matched incorrectly | Overly broad bare `@RequestMapping` | Use verb-specific shortcut mappings |
| Path regex in Java has wrong escaping | `\d+` unescaped in string literal | Use `\\d+` in Java |
| `GET /books/featured` hits `/{id}` | Overlapping paths/conversion | Static path/regex route, test specificity |
| Wrong Content-Type on POST | `consumes` not satisfied | Send JSON or declare the right media type |
| `Accept: xml` returns 406 | `produces` is JSON-only | Align client Accept with API representation |
| Mono.empty returns empty 200 | Absence not mapped to HTTP 404 | ResponseEntity.notFound/switchIfEmpty |
| `Flux<T>` output not as expected | Codecs/media type/stream flush | Test JSON/SSE/NDJSON with the right media type |
| `@Valid` has no effect | Missing validation provider/constraints | Declare constraints/validation starter and test |
| @ControllerAdvice misses errors | Copied MVC exception types | WebExchangeBindException/HandlerMethodValidationException |
| WebFlux response stalls | Using JDBC/JPA/Thread.sleep/block() on the event loop | Reactive I/O or bounded boundedElastic |
| CORS preflight blocked | Missing proper CORS/security configuration | @CrossOrigin/Global CORS/SecurityWebFilterChain |
| Controller returns wrong 201/404/204 code | Only returning a body value | Use ResponseEntity/ResponseStatusException |
| Mapping duplicate startup fail | Methods with same path/verb/conditions | Separate routes/conditions, test |
| Controller generates fake Location domain | Trusting raw Host/X-Forwarded-Host | Canonical public base URL + trusted proxy |
| Conditional header treated as authorization | Client can send custom headers itself | Spring Security + ACL |
| Excessive memory with Flux | collectList() on large/infinite sources | Pagination/bounded streaming |
| HTTP error after SSE committed | Cannot change already-sent response status | Event protocol/close/reconnect |

## 14. CORS, Security, and API Responsibilities

Mapping annotations **only determine routing**; they do not authenticate callers. You need:
1. Spring Security reactive `SecurityWebFilterChain` to enforce authentication and endpoint authorization.
2. Object ownership/tenant/ACL checks in the service; `@PathVariable id` does not guarantee access permission.
3. Appropriate CSRF protection when browsers use cookie/session credentials for state-changing POST/PUT/DELETE.
4. CORS origin/header/method allowlists; `@CrossOrigin` does not replace authentication.
5. DTO input allowlists, validation, and mass-assignment prevention; do not let clients set server-managed `role`, `ownerId`, or `price`.
6. Payload size/codec max in-memory limits, file upload limits, quotas, rate limiting, and request timeouts.
7. Fail closed when the permission service errors; never fall back to open access with `onErrorReturn(true)`.
8. Protection against open redirects/Host-header poisoning when building absolute links in Location.
9. Error responses that never leak stack traces/secrets/SQL/tenant data.
10. Logging/tracing reactive context propagation; do not put tokens/PII in URLs/logs.

### 14.1. Codec Buffer Limits

WebFlux has a max-in-memory-size for codecs and Spring Boot supports configuring it, for example in Boot 3.5:

```properties
spring.codec.max-in-memory-size=256KB
```

This is a **codec buffering limit**, not a hard cap for all HTTP bytes, request streaming, file uploads, or the entire system. For large request bodies, enforce additional policies at the gateway/server/decoder and never call `collectList()` on unbounded streams.

### 14.2. @CrossOrigin

```java
@CrossOrigin(origins="https://frontend.example.test")
@GetMapping("/api/public")
Mono<String> publicEndpoint() {
    return Mono.just("ok");
}
```

This is a snippet illustrating an origin allowlist. This origin is an example host, not a real domain. If Spring Security is present, CORS integration and OPTIONS handling must be configured consistently. Do not arbitrarily reflect any Origin with credentials.

## 15. Pre-Release QA Checklist

- [ ] The project actually runs the WebFlux reactive server, without accidentally auto-configuring MVC due to both starters.
- [ ] Class-level prefixes and method-level verbs are correct; no unintended unrestricted `@RequestMapping` methods.
- [ ] Path variables/regexes and catch-all patterns use valid PathPatternParser syntax.
- [ ] Params, headers, consumes, and produces are defined and tested.
- [ ] `Content-Type` describes the request; `Accept` describes the response.
- [ ] `@RequestBody Mono<Dto>` is decoded using WebFlux codecs; DTOs contain no sensitive fields.
- [ ] `@Valid`/manual validation and HTTP 400/404/406/415 responses match the contract.
- [ ] Return `Mono<ResponseEntity<T>>` when status/headers depend on async results.
- [ ] Flux/SSE/NDJSON streams use the right media type; cancellation/errors after commit are handled.
- [ ] No blocking JDBC/Thread.sleep/Mono.block on the event loop.
- [ ] SecurityWebFilterChain/CORS/CSRF/ACL/rate limits cover GET/POST/PUT/DELETE.
- [ ] Raw Host/Forwarded headers are not concatenated into Location/callback URLs.
- [ ] Tested with WebTestClient for JSON, route specificity, error cases, and wrong media types.
- [ ] If API version mapping is needed, distinguish Spring Framework 7 from 6.2.
- [ ] Metrics/logs monitor latency, codec buffer memory, 4xx/5xx, active requests, and client disconnects.
- [ ] Data races/concurrent updates are resolved in the repository/transaction, not by relying on Reactor return types.

## 16. Self-Check Questions

**Question 1.** Do `@RestController` in MVC and WebFlux have the same basic meaning?

**Answer:** Yes. It is equivalent to `@Controller` + `@ResponseBody`; underneath, however, they use different request/response infrastructure.

**Question 2.** Why can `@RequestMapping("/api/books")` without specifying an HTTP method on a handler method be dangerous?

**Answer:** It can match multiple HTTP methods instead of only GET; use `@GetMapping`/`@PostMapping`/... when you want a narrow route.

**Question 3.** If a client sends JSON to a POST endpoint, which annotation checks the input type and which specifies the response type?

**Answer:** `consumes="application/json"` checks the request Content-Type, while `produces="application/json"` is for response Accept/representation.

**Question 4.** When should you use `@RequestBody Mono<CreateBook>`?

**Answer:** When running on the WebFlux reactive stack and wanting to decode the request body asynchronously; do not assume it is an equivalent signature supported by MVC.

**Question 5.** Does `Mono.empty()` always return 404?

**Answer:** No. Use `switchIfEmpty(Mono.error(new ResponseStatusException(404)))` or `Mono<ResponseEntity<T>>` with notFound.

**Question 6.** Both WebFlux and MVC support `@GetMapping`, so does WebFlux use `DispatcherServlet`?

**Answer:** No. WebFlux uses `DispatcherHandler` on the reactive stack.

**Question 7.** If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present in Boot 3.5, which framework does it default to?

**Answer:** Spring MVC, unless you explicitly force the reactive web application type.

**Question 8.** Does `@RequestHeader("X-Role") String role` prove that the user is an admin?

**Answer:** No. Headers are sent by the client; authentication and authorization must be enforced by the security framework and data-source permissions.

**Question 9.** Which exception types can `@Valid` produce in WebFlux?

**Answer:** `WebExchangeBindException` for argument validation, and `HandlerMethodValidationException` when method validation applies; verify based on signature and Spring version.

**Question 10.** How do you verify that an annotated route works properly?

**Answer:** Use WebTestClient integration tests for path, method, params, headers, Content-Type, Accept, expected status/body, and negative cases.

## 17. Official Documentation

- [Spring Framework 6.2 — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller.html): @Controller/@RestController model, method signatures.
- [Spring Framework — Mapping Requests (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): class/method mappings, URI patterns, params/headers/consumes/produces, HEAD/OPTIONS.
- [Spring Framework 6.2 — Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html): @PathVariable, @RequestParam, @RequestHeader, ServerWebExchange, and reactive arguments.
- [Spring Framework 6.2 — Request Body](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): @RequestBody Mono/Flux, HttpMessageReader, validation.
- [Spring Framework 6.2 — Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html): Publisher, ResponseEntity, HTTP response writing.
- [Spring Framework 6.2 — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html): @Valid, WebExchangeBindException, HandlerMethodValidationException.
- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): nonblocking reactive architecture and MVC comparison.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): dependencies, starter choice, WebFlux config/codecs.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): @CrossOrigin, global CORS.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): SecurityWebFilterChain and reactive authentication/authorization.
- [Spring Framework — Spring MVC Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): reference for comparing shared annotations and Servlet differences.

**Conclusion:** learning WebFlux controllers from an MVC background is natural because `@RestController`/`@RequestMapping`/`@GetMapping`/`@RequestBody` syntax is very similar. However, to build reactive applications properly, you must recognize `DispatcherHandler`, `ServerWebExchange`, `HttpMessageReader/Writer`, `@RequestBody Mono<T>`, and native `Mono/Flux` return semantics; never block the event-loop, never skip security/validation, and always test route matching as well as content negotiation over real HTTP. **Identical annotations do not mean identical runtime I/O**.
