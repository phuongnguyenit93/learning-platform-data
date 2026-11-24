# @Controller, @RestController, and the Responsibilities of the Request-Handling Layer

When building an API or web application with Spring Boot, a controller is the entry point that receives an HTTP request and forwards that request into the rest of the system. The two most common annotations are `@Controller` and `@RestController`. Both allow Spring MVC to locate handlers via `@RequestMapping`, `@GetMapping`, `@PostMapping`..., but **how the return value is interpreted** differs: a controller targets a view when rendering a UI is needed, whereas a REST controller typically writes data directly into the HTTP response body.

This lesson focuses on **Spring MVC in the Servlet stack of Spring Boot 3.x, Java 17+**. The goal is to understand the routing mechanism, distinguish between a view and a response body, choose the right input/output types, establish the boundary of responsibilities between controller and service, and then implement and test a complete example. Spring Boot application examples require Spring Framework dependencies; they are not plain Java code that can be compiled standalone with `javac`.

## 1. Where does the controller sit in an HTTP request?

A typical Spring MVC processing chain:

~~~text
HTTP client
    |
Servlet container (Tomcat / Jetty / Undertow)
    |
Servlet filters / security filter chain
    |
DispatcherServlet
    |
HandlerMapping -> finds the handler matching the URL, HTTP method, and conditions
    |
HandlerAdapter -> binding, conversion, validation, invokes the controller method
    |
@Controller or @RestController
    |
Service / domain layer -> repository, HTTP client, transactions, and business rules
    |
Controller receives the business result
    |
    +-- Model + logical view name --> ViewResolver / template --> HTML
    |
    +-- @ResponseBody or ResponseEntity --> HttpMessageConverter --> JSON/text/bytes
    |
HTTP status + headers + body
~~~

`DispatcherServlet` is the front controller of Spring MVC, not a class that an application normally writes itself. Spring Boot auto-configuration registers it and the MVC components when `spring-boot-starter-web` and the Servlet web application conditions are satisfied.

A controller **does not directly open sockets, parse the entire HTTP protocol, or serialize JSON by itself**. Spring MVC and the servlet container handle those parts; the controller declares routing metadata and input/output handling methods at the application level.

Components with distinct roles:

| Component | Role |
|---|---|
| `DispatcherServlet` | Coordinates the entire Spring MVC flow |
| `HandlerMapping` | Decides which handler matches a request |
| `HandlerAdapter` | Knows how to invoke a handler and process arguments/return values |
| `WebDataBinder` / `ConversionService` | Binds and converts request data types |
| `HttpMessageConverter` | Reads body into a Java object, writes an object into an HTTP body |
| `ViewResolver` | Resolves a logical view into actual HTML/view |
| `HandlerExceptionResolver` | Converts certain exceptions into HTTP responses |
| `@Controller` / `@RestController` | Declares handlers and orchestrates work at the HTTP boundary |

## 2. What is @Controller?

`@Controller` marks a Spring bean as a controller component. This annotation specializes `@Component`, so the class is typically discovered through the application's component scan.

Example of a controller serving an HTML page:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class CatalogPageController {

    @GetMapping("/catalog")
    String page(Model model) {
        model.addAttribute("title", "Book catalog");
        return "catalog";
    }
}
~~~

When returning the string `"catalog"` from a `@Controller` method **without `@ResponseBody`**, Spring MVC typically treats it as a **logical view name**. If the application has a template engine such as Thymeleaf, the view resolver can look for the template `catalog.html` under `src/main/resources/templates/`.

Key points:
- `@Controller` **does not mean** the class can only return HTML. It can still return JSON/strings directly when `@ResponseBody` is placed on a method.
- A String value does not automatically turn into HTML. It is usually a view name or a redirect/forward target in the view flow.
- Whether the view can be rendered also depends on the view resolver, template dependency, file name, and corresponding configuration.
- When returning `ModelAndView`, the controller can provide both the model and the view at the same time.
- Attributes in `Model` are for rendering the view; they are not automatically placed into a JSON body.

Example of a redirect after processing a form:

~~~java
@PostMapping("/catalog/search")
String search(@RequestParam String keyword, RedirectAttributes redirect) {
    redirect.addAttribute("q", keyword);
    return "redirect:/catalog/results";
}
~~~

This is an **illustrative snippet**; appropriate imports and a matching method/route are required. The `redirect:` prefix is interpreted by the view-resolution infrastructure as an HTTP redirect. Do not treat `"redirect:/..."` as plain response text in a controller without `@ResponseBody`.

## 3. What is @RestController?

`@RestController` is an annotation that combines **`@Controller` and `@ResponseBody`** at the class level. It is still discovered by Spring MVC like a regular controller, but by default its handler methods return data to be written directly into the HTTP response.

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class StatusController {

    @GetMapping("/api/status")
    String status() {
        return "READY";
    }
}
~~~

For HTTP GET `/api/status`, the body will contain the text `READY`, **without** looking for a template view named `READY`.

When a REST controller returns a Java object/record, Spring MVC uses an appropriate `HttpMessageConverter`, usually the Jackson JSON converter when the Jackson dependency is present:

~~~java
record StatusResponse(String status, int activeJobs) {}

@RestController
class StatusApiController {

    @GetMapping("/api/status")
    StatusResponse status() {
        return new StatusResponse("READY", 3);
    }
}
~~~

Typical JSON body:

~~~json
{"status":"READY","activeJobs":3}
~~~

Do not interpret `@RestController` as "always returns JSON". For example, a method returning `String` can be written as text; a method returning `byte[]` or `ResponseEntity<Resource>` can write other content depending on the converter, the `Accept` header, and handler metadata. This annotation mainly determines **returning a response body instead of a view name**.

## 4. Comparing @Controller, @ResponseBody, and @RestController

| Class/method | Returning `String "home"` | Returning a DTO/record | Used for |
|---|---|---|---|
| `@Controller` without `@ResponseBody` | Usually logical view name `home` | Not serialized as an API object by default; depends on return-value handler/model | MVC pages |
| `@Controller` with `@ResponseBody` on the method | Text body `home` | Converter writes the DTO into the body | Combining HTML pages and APIs in one class |
| `@RestController` | Text body `home` | Converter writes the DTO into the body | REST/JSON or data-returning APIs |

The same `@Controller` class can still serve both response styles:

~~~java
@Controller
class MixedController {

    @GetMapping("/about")
    String aboutPage() {
        return "about";  // logical view
    }

    @ResponseBody
    @GetMapping("/api/about")
    String aboutText() {
        return "About this service";  // response body
    }
}
~~~

You can place `@ResponseBody` at the class level, but when most methods are APIs, `@RestController` conveys intent more clearly. Conversely, if a class primarily renders views, using `@Controller` helps prevent accidentally treating a String as a body.

**A good design convention:** separate API controllers and page-serving controllers when their HTTP contracts, security, or testing strategies differ. This is a maintainable organizational guideline, not a mandatory framework limitation.

## 5. Routing annotations and handler selection conditions

Spring MVC maps requests to methods using `@RequestMapping` and shortcut annotations:

- `@GetMapping`: GET.
- `@PostMapping`: POST.
- `@PutMapping`: PUT.
- `@PatchMapping`: PATCH.
- `@DeleteMapping`: DELETE.
- `@RequestMapping`: general-purpose form that can combine method/path/header/params/consumes/produces.

Example:

~~~java
@RestController
@RequestMapping("/api/books")
class BookRoutes {

    @GetMapping("/{id}")
    String read(@PathVariable long id) {
        return "book-" + id;
    }

    @GetMapping(params = "featured=true")
    String featured() {
        return "featured";
    }
}
~~~

Class-level mapping and method-level mapping are combined: the first method handles `GET /api/books/5`, and the second method handles `GET /api/books?featured=true`. However, **avoid designing multiple methods with ambiguous mappings**. If two handlers match the same request without a clear precedence distinction, an ambiguous mapping error or unexpected handler selection may occur.

Commonly used conditions:

~~~java
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
BookResponse create(@RequestBody BookRequest request) {
    // ...
}
~~~

- `path`: URL accepted by the handler.
- `consumes`: request body media type accepted by the handler, matched against `Content-Type`.
- `produces`: response media type supported by the handler, alongside the client's `Accept`.
- `params`: condition on the presence or value of query parameters.
- `headers`: condition based on HTTP request headers.

A request using the wrong HTTP method can return **405 Method Not Allowed**; an unaccepted request media type can return **415 Unsupported Media Type**; a client `Accept` format that cannot be provided can lead to **406 Not Acceptable**. These errors have different root causes; do not treat them all as JSON parse errors.

Name URLs after resources and resource hierarchies, avoiding names like `/api/doCreateBookNow` when the HTTP contract fits `POST /api/books` better.

## 6. How does a controller receive request data?

Not all HTTP data comes through a single annotation.

| Data source | Common annotation/API | Example |
|---|---|---|
| Variable in URL | `@PathVariable` | `GET /books/10` -> id=10 |
| Query parameter | `@RequestParam` | `GET /books?page=2` |
| Header | `@RequestHeader` | `Accept-Language: vi` |
| Cookie | `@CookieValue` | `session=...` |
| JSON/XML request body | `@RequestBody` | JSON DTO |
| Form/query data into a command object | `@ModelAttribute` | Search form |
| Multipart file/part | `@RequestPart`, `MultipartFile`, or `@RequestParam` | File upload |
| HTTP metadata | `HttpServletRequest`, `HttpHeaders`, `UriComponentsBuilder`... | Only when truly needed |
| View model | `Model` | Template rendering data |

Example distinguishing path, query, and header:

~~~java
@GetMapping("/api/books/{id}")
BookResponse find(
        @PathVariable long id,
        @RequestParam(defaultValue = "false") boolean verbose,
        @RequestHeader(name = "X-Trace-Id", required = false) String traceId) {
    // Signature declaration example only.
    // The controller passes id/verbose to the service; traceId can be used for observability.
    return service.find(id);
}
~~~

The code above is an illustrative snippet, assuming `service.find` has the corresponding return type. The request `GET /api/books/7?verbose=true` carries id in the path and verbose in the query; if the header is absent, `traceId` can be null.

Some common errors:
- `@PathVariable long id` receiving `/books/abc`: conversion from String to long fails, typically resulting in **400**.
- `@RequestParam int page` missing a required query param: typically **400**, unless configured with `required=false`/an appropriate default.
- `@RequestBody` receiving malformed JSON: the message converter may throw `HttpMessageNotReadableException` -> typically **400**.
- JSON body sent with a `Content-Type` mismatched with `consumes`: typically **415**.
- `@ModelAttribute` is not synonymous with JSON deserialization in the request body. It targets binding request parameters/form data into an object and requires managing the set of allowed bindable fields.

Spring MVC also handles content negotiation, type conversion, and validation before the handler runs. Therefore, not every input error reaches the first line of the controller method.

## 7. DTOs and @RequestBody: maintaining data boundaries

When an API creates or updates a resource, it should accept a **request DTO** representing the data the client is allowed to send, rather than arbitrarily binding directly to a JPA entity.

Example Java record for book creation data:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateBookRequest(
    @NotBlank @Size(max = 100) String title
) {}
~~~

A record fits simple immutable DTOs on Java 17. With the proper Jackson dependency, Spring MVC can instantiate a record from JSON:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json

{"title":"Clean Architecture"}
~~~

Controller declaration:

~~~java
@PostMapping("/api/books")
ResponseEntity<BookResponse> create(
        @Valid @RequestBody CreateBookRequest request) {
    // call service and return response
}
~~~

`@RequestBody` instructs the converter to read JSON into a Java object. `@Valid` requests Bean Validation checks if a corresponding implementation is on the classpath, typically via `spring-boot-starter-validation` in Boot 3.x applications.

**Why not bind entities directly:** an entity may contain fields such as `id`, `role`, `priceApproved`, `isAdmin`, or internal relationship properties. Clients should not be allowed to supply arbitrary fields just because the entity has setters. A dedicated DTO helps prevent over-posting/mass assignment, decouples the API contract from the persistence schema, and makes versioning easier.

An HTTP boundary DTO does not have to match a domain command either; when a system grows complex, you can map the request DTO into an explicit command before calling the service.

## 8. Validation: choosing the right responsible layer

The controller should validate **the validity of HTTP data** before passing it to business logic:
- Are required fields present?
- Do formats and lengths match the contract?
- Can the JSON be parsed?
- Can query/path arguments be converted into valid Java types?
- Are simple constraints such as `@NotBlank`, `@Size`, `@Min` satisfied?

Example:

~~~java
public record CreateBookRequest(
    @NotBlank(message = "title must not be blank")
    @Size(max = 100)
    String title
) {}
~~~

With `@Valid @RequestBody` and an appropriate validator, a request with `"title":""` is normally rejected with **400 Bad Request** before the controller method finishes. The default error body details depend on Spring Boot, `server.error.*`, Problem Details, and application handlers.

**However, business rules should not live solely in DTO annotations**. For example, "cannot borrow more books than the allowed limit", "cannot cancel a completed order", or "cannot create a duplicate code" require business state and data consistency: enforce these in the service/domain and protect them with appropriate transactions/constraints.

Do not rely exclusively on HTTP validation. Services can be invoked from a scheduler, message consumer, CLI, or tests without going through a controller; critical business invariants must still be enforced below the HTTP layer.

## 9. The controller decides HTTP status, headers, and body

With `@RestController`, if a method returns an object successfully and no custom status is configured, the common status is **200 OK**. However, an API with a clear REST contract should actively choose the status:

| Case | Common status | Notes |
|---|---|---|
| GET resource found | 200 | Body contains the representation |
| GET resource not found | 404 | Avoid returning 200 with an ambiguous empty value |
| POST resource created successfully | 201 | Should include `Location` pointing to the new resource |
| POST valid but processed asynchronously | 202 | Use only if accepted for processing and not yet completed |
| PUT updated successfully | 200 or 204 | Depending on whether a body is returned |
| DELETE succeeded | 204 | Do not send a body |
| Malformed JSON/failed validation | 400 | Distinguish from domain errors |
| Conflict with current state | 409 | For example version/conflict when appropriate |
| Unauthenticated | 401 | Security framework handles according to policy |
| Authenticated but forbidden | 403 | Requires security policy |

`ResponseEntity<T>` lets you control status, headers, and body per branch:

~~~java
@GetMapping("/api/books/{id}")
ResponseEntity<BookResponse> find(@PathVariable long id) {
    return service.findById(id)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

`ResponseEntity.created(location).body(value)` returns **201 Created** and a `Location` header. `ResponseEntity.noContent().build()` returns **204 No Content**. When the body is genuinely empty, do not return an empty String just to simulate 204.

`@ResponseStatus(HttpStatus.CREATED)` fits when a method always returns the same status. `ResponseEntity` is more flexible when different statuses/headers are needed depending on the outcome.

Note: if you return `String` from a REST controller, it is a text body; Spring does not automatically set status 201 or generate `Location` just because the method is named `create`.

## 10. @Controller and view rendering for HTML

When building server-rendered UIs, `@Controller` typically puts data into `Model` and returns the template name:

~~~java
@Controller
class BooksPageController {

    private final BookService service;

    BooksPageController(BookService service) {
        this.service = service;
    }

    @GetMapping("/books")
    String listPage(Model model) {
        model.addAttribute("books", service.list());
        return "books";
    }
}
~~~

With the `spring-boot-starter-thymeleaf` dependency, Boot typically configures the view resolver to look for:

~~~text
src/main/resources/templates/books.html
~~~

The template can use Thymeleaf to render the list of books:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Books</title></head>
<body>
  <h1>Books</h1>
  <ul>
    <li th:each="book : ${books}" th:text="${book.title}"></li>
  </ul>
</body>
</html>
~~~

When the method returns `"books"` from `@Controller`, the template is rendered into HTML. If you change the class to `@RestController` and still return `"books"`, the client only receives the text body `books`; **the template will not be selected** under that return-value mechanism.

In Spring MVC, `@ModelAttribute` can contribute data to the view and bind forms. A form-serving controller should consider Post/Redirect/Get to avoid browser POST resubmission on refresh, and use CSRF protection when login sessions exist.

## 11. Responsibilities a controller layer should have

A controller is an **HTTP adapter**. A good controller focuses on:

1. Declaring routes and request-acceptance conditions (path/method/headers/media types).
2. Receiving and binding input data into a request DTO or explicit arguments.
3. Triggering transport/contract-level validation.
4. Resolving necessary input context, such as identity from the security context, locale, or correlation id if the problem requires it.
5. Calling the appropriate service/use case, passing validated data.
6. Mapping results or business errors to response DTOs, HTTP statuses, and headers.
7. For HTML MVC, preparing the model and logical view; for APIs, returning the appropriate response body.
8. Keeping methods short, testable, and not overly coupled to storage infrastructure.

These are **orchestration responsibilities at the HTTP boundary**, not executing all business logic of the system.

Things to avoid placing directly in a controller:
- Writing SQL/JPA queries, creating multi-step transactions, or managing database connections.
- Complex business calculations or mutating state according to domain rules.
- Calling multiple downstream services in long flows without timeout/transaction policies.
- Sending emails, exporting large reports, or running long batch jobs on the request thread without an async plan.
- Writing custom authentication/authorization logic in place of Spring Security.
- Logging raw passwords/tokens/PII or returning internal stack traces to clients.
- Allowing clients to set IDs, statuses, roles, or sensitive values outside the API contract.

A simple boundary:

~~~text
HTTP Controller -> Application Service / Use Case -> Repository / Gateway
       |                    |
  DTO, status, headers      business rules, consistency, transactions
       |
  Spring MVC (binding, validation, converters)
~~~

Some small projects may have fairly compact controllers and a single service layer, yet keeping this boundary still allows reusing business logic from other entry points (event consumers, schedulers, batch jobs).

## 12. The service executes business logic; the controller expresses results over HTTP

A common separation of responsibilities:

~~~java
@Service
class BookingService {
    private final BookingRepository repository;

    BookingService(BookingRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public BookingResult reserve(ReserveCommand command) {
        // Check business rules, update data, preserve transaction.
        return repository.reserve(command);
    }
}
~~~

This is an **architectural illustration**, not code with complete classes to run standalone. `@Transactional` belongs to Spring transaction management and only takes effect when an appropriate transaction manager and proxy/configuration exist.

Controller calling the service:

~~~java
@RestController
@RequestMapping("/api/reservations")
class ReservationController {
    private final BookingService service;

    ReservationController(BookingService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<ReservationResponse> reserve(
            @Valid @RequestBody ReserveRequest request) {
        BookingResult result = service.reserve(toCommand(request));
        return ResponseEntity
            .created(URI.create("/api/reservations/" + result.id()))
            .body(toResponse(result));
    }
}
~~~

In the illustrative example, `ReserveRequest`, `ReserveCommand`, `BookingResult`, and mappers `toCommand`/`toResponse` are application-defined types/methods. The main point is that the controller **does not need to know** whether the service uses JPA, JDBC, an HTTP client, or an in-memory store.

In a Servlet MVC application, controller methods run synchronously on the request thread by default. If a service performs slow blocking I/O, adding more controllers does not automatically make the system non-blocking. Async MVC and Spring WebFlux are separate models requiring appropriate lifecycle, thread, and backpressure handling.

## 13. Error handling with @ControllerAdvice and @RestControllerAdvice

An exception can be caught by Spring MVC and converted into an HTTP response through `HandlerExceptionResolver` implementations, including `@ExceptionHandler` logic in controllers/advice.

`@ControllerAdvice` provides shared handling across multiple controllers. `@RestControllerAdvice` combines `@ControllerAdvice` with `@ResponseBody` so exception handlers return a body directly; it is suited for REST APIs.

Example handling a domain exception:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(DuplicateBookException.class)
    ProblemDetail duplicate(DuplicateBookException ex) {
        ProblemDetail problem =
            ProblemDetail.forStatusAndDetail(HttpStatus.CONFLICT, ex.getMessage());
        problem.setTitle("Book conflict");
        return problem;
    }
}
~~~

This is an illustrative snippet; the application must define `DuplicateBookException`. With Spring Framework 6 / Boot 3.x, `ProblemDetail` is a type representing errors according to the problem details standard; it should be configured and handled consistently with other exception handlers.

Avoid catching `Exception` too broadly and always returning HTTP 200, as that loses error semantics and breaks monitoring. Never send internal exception messages to clients if they could contain SQL, file paths, tokens, or sensitive data.

Some input errors like malformed JSON and Bean Validation are handled by Spring before service logic runs. You can customize them via `ResponseEntityExceptionHandler` or an appropriate exception handler, while explicitly controlling status codes and the response contract.

With `@Controller` rendering views, error handling can return an error page name; with REST APIs, return a clear error body and the right status. Do not use a single error response for both HTML pages and JSON clients if the contracts of the two types differ.

## 14. Security and cross-cutting concerns are not built-in controller features

`@RestController` **does not mean an API is protected**. Authentication, authorization, CSRF, and session/cookie behavior must be configured by appropriate infrastructure, commonly Spring Security and the servlet filter chain.

Some notes:
- Authenticate and authorize at the filter/security layer or via method security as required; the controller can access the verified principal or identity.
- Business code must enforce critical invariants, not blindly trust roles/IDs sent by the client.
- CORS does not replace authorization. Allowing a frontend to make cross-origin calls does not mean it has permission to access data.
- `HandlerInterceptor` can handle common tracing/logging, but it does not completely replace security filters.
- Controllers should not open transactions inside individual methods when the application service is the place that knows the business boundaries.
- Request/response logging must strip secrets, tokens, and sensitive data.

A controller can obtain the authenticated user identity via `Principal` or `@AuthenticationPrincipal` when Spring Security is present. Do not take a user ID from a query param and assume it is the logged-in user.

## 15. Complete runnable example: REST API and HTML page

This example uses **Spring Boot 3.3.x and Java 17+**, `spring-boot-starter-web`, Thymeleaf, Bean Validation, and Spring Boot test. Its purpose is to demonstrate two controller styles sharing one service, without needing a database. Data is stored in memory, so it is lost on restart.

Create a Spring Boot project with dependencies: **Spring Web, Thymeleaf, Validation, Spring Boot Test**. If using Gradle, let the project initializer generate the appropriate wrapper/Gradle plugins, then ensure equivalent dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

If building the project manually, you need the Spring Boot plugin and corresponding Java 17 setup; the `dependencies` block above is the dependency declaration section, **not a complete standalone build.gradle file**.

### 15.1. Java application: one file containing main, DTOs, service, and two controllers

Create the file `src/main/java/com/example/demo/BookApplication.java`:

~~~java
package com.example.demo;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.stereotype.Service;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BookApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookApplication.class, args);
    }
}

record CreateBookRequest(
    @NotBlank @Size(max = 100) String title
) {}

record BookResponse(long id, String title) {}

@Service
class BookService {
    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, BookResponse> books =
        new ConcurrentHashMap<>();

    BookResponse create(CreateBookRequest request) {
        long id = nextId.incrementAndGet();
        BookResponse book =
            new BookResponse(id, request.title().trim());
        books.put(id, book);
        return book;
    }

    Optional<BookResponse> findById(long id) {
        return Optional.ofNullable(books.get(id));
    }

    List<BookResponse> list() {
        return books.values().stream()
            .sorted(Comparator.comparingLong(BookResponse::id))
            .toList();
    }
}

@RestController
@RequestMapping("/api/books")
class BookApiController {
    private final BookService service;

    BookApiController(BookService service) {
        this.service = service;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    List<BookResponse> list() {
        return service.list();
    }

    @GetMapping(
        path = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<BookResponse> findById(@PathVariable long id) {
        return service.findById(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {
        BookResponse created = service.create(request);
        URI location = URI.create("/api/books/" + created.id());
        return ResponseEntity.created(location).body(created);
    }
}

@Controller
class BookPageController {
    private final BookService service;

    BookPageController(BookService service) {
        this.service = service;
    }

    @GetMapping("/books")
    String listPage(Model model) {
        model.addAttribute("books", service.list());
        return "books";
    }
}
~~~

Why does this example observe proper responsibility boundaries?
- `BookApiController` declares the REST contract: GET list, GET by ID, POST create resource. It chooses status 200/201/404 and `Location`.
- `CreateBookRequest` is a DTO for the HTTP body; `@Valid` checks blank strings and length.
- `BookService` manages state and generates IDs. Controllers do not read/write the internal map directly.
- `BookPageController` prepares `Model` and returns logical view `"books"`.
- Both controllers use **the same service** yet produce two kinds of HTTP representation: JSON and HTML.
- `ConcurrentHashMap` and `AtomicLong` are only sufficient for a single-JVM demo. They do not replace a database, transactions, constraints, or multi-instance synchronization in production.

### 15.2. Thymeleaf template

Create the file `src/main/resources/templates/books.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Book catalog</title>
</head>
<body>
    <h1>Book catalog</h1>
    <p>This list is retrieved from the same service as the REST API.</p>
    <ul>
        <li th:each="book : ${books}">
            <span th:text="${book.id}"></span>:
            <strong th:text="${book.title}"></strong>
        </li>
    </ul>
</body>
</html>
~~~

This file is a template, not an asset in `static/`. The Thymeleaf view resolver pairs with `@Controller` to render HTML. If `books` is empty, the `<li>` list has no iterated elements.

### 15.3. Running and testing HTTP

In a Gradle project with the wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Create a new resource:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"title":"Clean Code"}'
~~~

With a fresh application and the first request, typical response:

~~~http
HTTP/1.1 201
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"Clean Code"}
~~~

These are the significant response parts, not an exhaustive list of every server-generated header. Subsequent requests may have different IDs. JSON field order is determined by standard Jackson/record mapping, though clients should parse JSON by field name rather than relying on key position in the string.

Read the resource:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

Typical body:

~~~json
{"id":1,"title":"Clean Code"}
~~~

JSON list:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/books
~~~

Body after one successful POST:

~~~json
[{"id":1,"title":"Clean Code"}]
~~~

HTML page:

~~~bash
curl -i -H "Accept: text/html" http://localhost:8080/books
~~~

The response is HTML rendered from `books.html`. It contains the list from the service, yet **does not use a JSON message converter** to build the HTML page.

Test validation:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":""}'
~~~

Expected HTTP **400 Bad Request**, because of `@NotBlank`. The exact error body depends on Spring Boot configuration and any custom exception handlers the application has.

Test a non-existent resource:

~~~bash
curl -i http://localhost:8080/api/books/99999
~~~

Expected **404 Not Found**. Thanks to `ResponseEntity.notFound()`, this branch is not confused with HTTP 200 and JSON `null`.

**Shell note:** the `\` line-continuation syntax in examples is Bash style. In PowerShell, write curl on a single line or use `curl.exe` with appropriate PowerShell quoting syntax.

## 16. Testing routing and controller responsibilities with MockMvc

Add `spring-boot-starter-test` to the test classpath. The following test runs the Spring Boot context and sends requests via MockMvc without opening a real HTTP socket.

Create the file `src/test/java/com/example/demo/BookControllerTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void postCreatesBookWithLocation() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"DDD\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andExpect(jsonPath("$.title").value("DDD"));
    }

    @Test
    void invalidRequestReturns400() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownBookReturns404() throws Exception {
        mvc.perform(get("/api/books/999999"))
            .andExpect(status().isNotFound());
    }

    @Test
    void pageControllerReturnsView() throws Exception {
        mvc.perform(get("/books"))
            .andExpect(status().isOk())
            .andExpect(view().name("books"));
    }
}
~~~

Run using the project's Gradle wrapper configured for JUnit Platform:

~~~bash
./gradlew test
~~~

These tests verify an **HTTP contract**, without relying on log strings or calling controller methods directly. `@SpringBootTest + @AutoConfigureMockMvc` is well-suited for testing broad application wiring. If you only want to test the MVC layer in isolation, `@WebMvcTest(BookApiController.class)` creates a test slice, though it typically requires `@MockBean` or an equivalent mocking mechanism for the service along with appropriate test configuration.

Do not just unit test Java methods and conclude that binding, Jackson, validation, exception resolution, and ViewResolver work; those parts are provided by Spring MVC and must be tested through the MVC infrastructure.

## 17. What Spring Boot provides out of the box vs. what the controller must still do

When `spring-boot-starter-web` is enabled, Spring Boot typically auto-configures:
- An embedded servlet container matching the dependencies.
- `DispatcherServlet` and servlet registration.
- `RequestMappingHandlerMapping` and `RequestMappingHandlerAdapter` via Spring MVC configuration.
- Available message converters on the classpath, typically Jackson for JSON.
- Binding, type conversion, formatters, and validation integration when dependencies and configuration match.
- Static resources, welcome page, certain view resolvers, and default error handling.
- Customization properties such as `spring.mvc.*`, `spring.web.resources.*`, and `server.*`.

Things Boot **does not automatically know**:
- Which URLs are right for your system's business domain.
- Which DTOs clients are permitted to send and which fields must be hidden.
- Whether a missing resource should return 404 or follow custom domain behavior.
- Which users are allowed to call a specific API.
- Transaction consistency, data security, and business rules.
- How to handle duplicate operations, idempotency keys, and downstream errors.

In controllers, leverage the framework's auto-configuration; customize only when needed. If you only want to add a formatter, interceptor, or CORS mapping, look into `WebMvcConfigurer` instead of enabling `@EnableWebMvc` unnecessarily: `@EnableWebMvc` causes Spring Boot to back off part of its MVC auto-configuration, which can significantly alter default behavior.

## 18. HTTP semantics and API contract consistency

Choosing a controller annotation is not enough to make an API "RESTful". Proper design also includes resource URIs, HTTP methods, statuses, headers, representations, and errors.

Some practical rules:
- GET should be business-safe: do not design important state changes like creating an order inside GET.
- PUT is idempotent per HTTP semantics: sending the same request multiple times should have the same intended effect on the resource (this does not mean the response body is always identical).
- DELETE should also be designed to be idempotent in effect; status 204/404 on subsequent calls may differ according to contract.
- POST creating a resource usually returns 201 and Location; if processed asynchronously it may return 202 when the contract fits.
- For operations with side effects that may be retried, consider an idempotency key to prevent duplicates.
- Pagination, sorting, and filtering should be explicit arguments/DTOs with bounded page sizes.
- For public APIs, use request/response DTOs separate from domain/persistence and control JSON field exposure.

These rules belong to the **API contract** expressed by the controller. Guaranteeing state and transactions still requires the service/domain and persistence layers underneath.

## 19. How does a Spring MVC controller differ from WebFlux?

Spring MVC and Spring WebFlux both have `@Controller`, `@RestController`, `@GetMapping`, and `@RequestBody` in the Spring Web namespace, but their request-processing runtimes differ.

- **Spring MVC** is based on the Servlet stack and typically runs controllers synchronously on a servlet request thread; it supports asynchronous return types in appropriate scenarios.
- **Spring WebFlux** uses the reactive web stack and typically uses Reactor `Mono`/`Flux`, handling reactive I/O and backpressure according to publisher semantics.
- Adding `Mono` to a method signature does not automatically turn a Spring MVC application into a WebFlux runtime.
- Adding both `spring-boot-starter-web` and `spring-boot-starter-webflux` typically causes Boot to choose Servlet MVC by default; you must verify the actual application type.
- Identical annotations do not mean you are allowed to make arbitrary blocking I/O calls on the WebFlux event loop.

This lesson focuses on **the responsibilities of the HTTP-receiving layer**, where the principles remain close: the controller receives/binds requests, calls use cases, and returns representations; it does not execute all business logic itself.

## 20. Common errors and how to find their root cause

| Symptom | Likely cause to consider | How to investigate |
|---|---|---|
| `@Controller` returns a string and gets a 404 view | The string is treated as a view name, template does not exist | ViewResolver, template path, whether `@ResponseBody` is needed |
| `@RestController` returns `"home"` instead of HTML | The string is written straight to the response body | Switch to `@Controller` or return the desired body |
| POST JSON returns 415 | Content-Type does not match `consumes` | Request headers, media type, handler mapping |
| GET returns 406 | Accept header does not match `produces`/converter | Accept, converters, and handler conditions |
| DTO is null/400 | Malformed JSON, binding/validation error | `@RequestBody`, DTO constructors, Java record, Jackson |
| `@PathVariable` or `@RequestParam` does not bind | Argument/annotation name or conversion mismatch | Declare explicit names, URL parameters, primitive/enum |
| One URL matches multiple handlers | Duplicate/ambiguous mapping | Class/method path, HTTP method, params/headers |
| GET missing resource returns 200/null | Controller has not chosen status 404 | Optional/ResponseEntity/error handling |
| Request reaches controller without permission | Security not configured/relying on manual logic | Filter chain, method security, ownership rule |
| An HTTP request takes too long | Blocking service, slow database/downstream | Tracing, client timeouts, queries, thread pool |
| Controller test passes but production endpoint fails | Test calls method directly, bypassing MVC wiring | MockMvc/integration tests, config/profiles |
| API leaks internal fields | Returning a JPA entity directly | Response DTOs, serialization rules |

If an endpoint is not invoked, check in order: verify URL/context path, HTTP method, `consumes`/`produces`, security filters, mapping conditions, component scan, and then Spring MVC logs. In an environment needing debugging, you can enable:

~~~properties
logging.level.org.springframework.web=DEBUG
~~~

If using Spring Boot Actuator and safe exposure is permitted, the mappings endpoint can show registered handlers. Avoid exposing management information publicly or logging sensitive bodies/headers.

## 21. Checklist before finalizing a controller

- [ ] Choose `@Controller` to render views or `@RestController` to return a response body; do not confuse a String view with a String body.
- [ ] Use specific mappings and appropriate HTTP methods; avoid ambiguous routes.
- [ ] Separate path/query/header/body with the right annotations.
- [ ] Use dedicated request DTOs, avoiding direct binding of entities/internal fields.
- [ ] Validate inputs at the HTTP boundary and enforce business invariants in the service/domain.
- [ ] Call services/use cases via constructor injection; do not put all business logic in the controller.
- [ ] Choose clear statuses/headers/bodies, especially 201/404/204 and Location.
- [ ] Have a consistent error contract; do not return 200 for exceptions or expose stack traces.
- [ ] Configure authentication/authorization independently of REST annotations.
- [ ] Use MockMvc to test routing, media types, validation, statuses, and representations.
- [ ] Ensure appropriate timeouts, tracing, and error handling for downstream calls.
- [ ] Keep Boot's MVC auto-configuration unless there is a clear reason to replace it.

## 22. References

- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): `@Controller` and `@RestController` model.
- [Spring Framework — Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): URL/HTTP method/consumes/produces conditions.
- [Spring Framework — Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): `@PathVariable`, `@RequestParam`, `@RequestBody`, `Model`.
- [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): view names, `ResponseEntity`, response bodies, and statuses.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC auto-configuration, embedded server, views, resources, and errors.
- [Spring Framework — Testing MVC](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): MockMvc and testing controllers through the Spring MVC infrastructure.

**Conclusion:** `@Controller` and `@RestController` are both HTTP request-handling layers in Spring MVC. The core difference is **returning a logical view** versus **writing the response body directly**. A controller should keep the role of **translating an HTTP contract into a use case, then translating the result into an HTTP response**; business logic, persistence, transactions, and consistency belong in the service/domain and appropriate layers. Designing clear boundaries makes APIs easy to test, change, and maintain without turning controllers into "god classes".
