# Testing Controllers with @WebMvcTest and Response Contracts in Spring Boot

## 1. Goal: testing the HTTP contract at the exact MVC boundary

A Controller in Spring Boot does not simply call a service and return a Java object. Passing through Spring MVC, data also goes through **request mapping**, parameter type conversion, **JSON serialization/deserialization**, **Bean Validation**, exception handling, content negotiation, filters, and HTTP status/headers. Writing a unit test like `new BookController(mockService).get(id)` only checks a Java call; it **does not prove** that a client will actually receive HTTP 200, 201, 400, 404, 409, 415, or 406.

`@WebMvcTest` is designed to test this web MVC layer **without starting the entire application** and without requiring a real HTTP server. With Spring Boot 3.5, it configures `MockMvc`, MVC infrastructure, `@Controller`, `@ControllerAdvice`, converters, filters, and relevant web components; regular services and repositories are not automatically loaded. Collaborators needed by the controller are typically replaced with `@MockitoBean`.

This lesson belongs to **Integration Practice**. It is a *slice integration test*: it uses many real Spring MVC components while substituting business dependencies. Learners need to master:

1. Choosing `@WebMvcTest(BookController.class)` and `MockMvc` to test at the exact HTTP boundary.
2. Using `@MockitoBean` to isolate the service while still testing Spring DI and MVC wiring.
3. Writing contract assertions for **status**, **Content-Type**, **Location**, JSON body, collection shape, and field values.
4. Testing `@RequestBody`, `@Valid`, `@NotBlank`, `@Size`, request media types, and malformed JSON.
5. Testing `@RestControllerAdvice` returning structured errors using `ProblemDetail` with a stable error code.
6. Distinguishing a **record-not-found** 404 from a **route-not-found** 404; 400, 401/403, 406, 409, and 415 are distinct contracts.
7. Using Mockito `given`, `verify`, and `verifyNoInteractions` to ensure the controller communicates with the service with the right arguments.
8. Distinguishing `@WebMvcTest`, `@SpringBootTest + @AutoConfigureMockMvc`, `MockMvcBuilders.standaloneSetup`, and a real HTTP server.
9. Avoiding brittle tests tied to raw JSON strings, timestamps, Map ordering, framework messages, or unloaded security configuration.
10. Running Gradle/JUnit test reports properly, without claiming passes when examples have not been executed.

**Sample stack:** Java 17+, Spring Boot 3.5.8, Spring MVC, Jackson, Hibernate Validator/Bean Validation, JUnit Jupiter, Mockito, AssertJ, and Gradle. The complete project below uses no database, Docker, cloud service, or network exporter. It includes both **14 `@WebMvcTest` tests** and **2 `@SpringBootTest` tests with MockMvc** to clearly show the two integration levels. All runtime examples are **design expectations**, not build results run in this environment.

## 2. Distinguishing Controller unit tests, MVC slices, and full integration

```text
Simulated HTTP request from MockMvc
      |
      v
DispatcherServlet + RequestMappingHandlerMapping
      |
      +--> argument conversion / @RequestBody Jackson
      +--> @Valid Bean Validation
      +--> HandlerInterceptor / servlet Filters if present
      |
      v
Real BookController
      |
      +--> BookService = @MockitoBean       [@WebMvcTest]
      |                   OR
      +--> Real InMemoryBookService          [@SpringBootTest]
      |
      v
ResponseEntity<T> / @RestControllerAdvice
      |
      +--> HttpMessageConverter / Jackson
      +--> status, headers, Content-Type, JSON/problem+json
      |
      v
MockHttpServletResponse inspected by MockMvc
```

| Approach | Real Spring MVC? | Spring ApplicationContext? | Real Service? | Real HTTP socket? | Best suited for |
|---|---|---|---|---|---|
| `new BookController(mock)` | No | No | Mock | No | Unit testing in-method decisions |
| `MockMvcBuilders.standaloneSetup(...)` | Partial MVC configured by test | No full Boot context needed | Depending on builder setup | No | Standalone controller, manual wiring |
| `@WebMvcTest(BookController.class)` | **Yes**, MVC slice | **Yes**, narrowed | Usually `@MockitoBean` | No | Controller HTTP contract |
| `@SpringBootTest + @AutoConfigureMockMvc` | Yes | **Full Boot context** | Can be real bean | No with MOCK | Verifying Controller→Service wiring |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Yes | Full context | Real | **Yes** | Near end-to-end server transport |
| `@WebFluxTest` | **WebFlux**, not MVC | WebFlux slice | Mock/imported as needed | No | Reactive WebFlux controllers |

**Do not choose a test level just because an annotation name looks familiar.** If the requirement is testing routes, JSON, validation, and exception mapping, `@WebMvcTest` is usually fast and sufficient. If the requirement involves repositories, JPA transactions, or a real DB, `@WebMvcTest` cannot prove it; separate data-slice or full integration tests are needed.

## 3. Which components does `@WebMvcTest` load?

Spring Boot 3.5 `@WebMvcTest` is tuned for Spring MVC:
- `@Controller` and `@RestController`.
- `@ControllerAdvice`/`@RestControllerAdvice`, if matched by component scanning.
- Jackson `@JsonComponent`, converters, and related web infrastructure.
- `Filter`, `HandlerInterceptor`, `HandlerMethodArgumentResolver`.
- `WebMvcConfigurer`, `WebMvcRegistrations`, and certain MVC-related beans.
- `MockMvc` and optionally `MockMvcTester` (when AssertJ support is present).
- Spring Security configuration/filter chain if Security is on the classpath.

It **does not** automatically load every `@Service`, `@Repository`, JPA EntityManager, datasource, or messaging client just for being in the same package. That is why a constructor-injected service usually must be supplied via `@MockitoBean` or `@Import` in tests.

### 3.1. Controller must be a real bean, service is mocked

```java
@WebMvcTest(BookController.class)
class BookControllerSliceTest {

    @Autowired MockMvc mvc;

    @MockitoBean BookService books;

    // @Test methods will call mvc.perform(...),
    // not call controller.getById(...) directly.
}
```

This is a fragment; the full runnable class is in Section 10. The import for `@MockitoBean` is:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

With Spring Framework 6.2 and Spring Boot 3.5, this is the current bean override mechanism. Older Boot examples use `@MockBean` in a Boot-specific package; do not carelessly mix imports/semantics from Boot 4 or Spring 7 into a 3.5 project.

`@MockitoBean` operates on a **bean inside the test ApplicationContext**, not a local Mockito mock created separately and silently left uninjected into the Controller. In the MVC slice, mocking `BookService` allows controller constructor injection to complete and lets every service call be stubbed/verified.

### 3.2. When to use `@Import` instead of `@MockitoBean`?

Have a real web component to test (e.g., custom `Converter`, Jackson Module, dedicated `@ControllerAdvice`, custom `WebMvcConfigurer`)? You can `@Import` that exact component/configuration into the slice if it was not scanned.

However, if a service has 15 DB/Kafka/HTTP client dependencies, doing `@Import(WholeApplicationConfiguration.class)` to “fix context load failures” makes the slice heavy and defeats its purpose. Mock collaborators at the Controller boundary and test the service in its own suite.

A `@RestControllerAdvice` under the `@SpringBootApplication` base package is normally picked up automatically by the slice scan. If the advice lives outside the scanned package, import it explicitly and ensure there are no duplicate beans/handlers.

### 3.3. `@WebMvcTest` does not need an extra `@AutoConfigureMockMvc`

`@WebMvcTest` **already** auto-configures `MockMvc`. If you use `@SpringBootTest(webEnvironment=MOCK)` and want `MockMvc`, add:

```java
@SpringBootTest
@AutoConfigureMockMvc
class FullMvcTest {
    @Autowired MockMvc mvc;
}
```

This is a fragment. `@AutoConfigureMockMvc` provides `addFilters` to customize filter registration, but for security/authorization contracts you must never simply turn filters off and claim an endpoint is protected.

## 4. A “response contract” must be stated clearly before writing assertions

An HTTP contract is more than `status().isOk()`. It typically includes:

| Component | Example endpoint GET /api/books/42 | When to assert? |
|---|---|---|
| URL + HTTP method | GET /api/books/{id} | Routing contract |
| Path/query parameters | 42 or `?author=Ada` | Argument binding |
| Request Content-Type | POST `application/json` | Request converter/consumes |
| Accept | `application/json` | Content negotiation/produces |
| Response status | 200, 201, 400, 404, 409 | Every main scenario |
| Response Content-Type | `application/json` or `application/problem+json` | Client parsing contract |
| Headers | `Location: /api/books/77` on create | Create/redirect/cache/versioning |
| Body structure | object, array, problem detail | API schema |
| Body values | id, title, author; code/message | Business contract |
| Error mapping | `BookNotFoundException`→404 | `@RestControllerAdvice` |
| Validation | blank/too long fields →400 | Request contract |
| Side effects/collaborator | `books.create(request)` called exactly once | Controller-service boundary |
| Security/CORS | 401, 403, preflight headers | Only when Security/CORS is in scope |

Choose **stable, intentional** assertions. Avoid asserting server-generated fields such as `Date`, random request IDs, default stack traces, JSON object key ordering, or framework error messages outside the public API contract.

### 4.1. Distinguishing 200, 201, and 204

- **200 OK**: successful read returning an appropriate JSON body.
- **201 Created**: resource created, typically with `Location` pointing to the new resource; may include a representation.
- **204 No Content**: operation succeeded **with no response body**. Never return `204` and expect MockMvc to see JSON.
- **202 Accepted**: request accepted for async processing; does not prove the work has finished.
- **304 Not Modified**: used for conditional requests/caching; carries no body like 200 does.

In our example, successful POST returns 201 + Location + JSON body; do not use 200 just to simplify tests. This is an explicit API choice; real projects must follow their published contract.

### 4.2. Client errors vs server errors

- **400**: malformed JSON, unconvertible path argument type, or failed Bean Validation.
- **401**: unauthenticated when security policy requires it.
- **403**: authenticated without permission, or CSRF protection rejected an unsafe method.
- **404**: endpoint does not exist **or** looked-up resource does not exist (distinguished in error payload).
- **409**: state conflict, such as duplicate title when policy disallows it.
- **415**: request sent a `Content-Type` not supported by `consumes`.
- **406**: client `Accept`s a media type not supported by the endpoint's `produces`.
- **500**: unmapped system error; never turn every exception into 200/404.

**Do not mock `BookService` to return null and treat that as 404.** If the controller does not handle null, it might return 200 with an empty body; the proper contract here is for the service to throw `BookNotFoundException`, and the advice turns it into HTTP 404 in this sample.

## 5. Project architecture: controller/service/advice/DTO

Standalone file layout:

```text
settings.gradle
build.gradle
src/main/java/com/example/bookapi/
    BookApiApplication.java
    BookView.java
    CreateBookRequest.java
    BookService.java
    InMemoryBookService.java
    BookNotFoundException.java
    DuplicateBookException.java
    BookController.java
    BookApiExceptionHandler.java
src/test/java/com/example/bookapi/
    BookControllerSliceTest.java
    BookApiFullContextTest.java
```

All classes share package `com.example.bookapi` so `@SpringBootApplication` discovers components. The project:
- Uses Java 17 `record` types for explicit request/response fields.
- Uses Jakarta Bean Validation: `@NotBlank`, `@Size`.
- Uses `ResponseEntity` for 201 + Location.
- Uses Spring `ProblemDetail` and `@RestControllerAdvice` for errors with a stable `code`.
- Includes an in-memory service sufficient for `@SpringBootTest` to run **without a DB**.
- Uses `@WebMvcTest` with a Mockito service mock to focus on the HTTP contract.
- Omits Spring Security from the sample `build.gradle`; security is discussed separately in Section 13.

## 6. Creating the Java 17+ and Spring Boot 3.5.8 project

### 6.1. settings.gradle

```groovy
rootProject.name = 'book-api-mvc-contract'
```

### 6.2. build.gradle (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

**Why these two starters?**
- `spring-boot-starter-web`: Spring MVC, Servlet infrastructure, and Jackson HTTP message converters.
- `spring-boot-starter-validation`: Hibernate Validator/Jakarta Bean Validation runtime; without it, `@Valid` may not behave as expected in the app.
- `spring-boot-starter-test`: JUnit Jupiter, Mockito, AssertJ, Spring Test/MockMvc, and Hamcrest-related testing utilities.
- JUnit Platform Launcher is an explicit test-runtime dependency.
- The Spring Boot BOM aligns Spring Framework/JUnit/Mockito/Jackson versions; never copy a random different `spring-test` version.

**The version is a fixed example**, not a claim that it is the latest Spring Boot at all times. The project requires a compatible Gradle wrapper (or installed Gradle) to run commands. `build.gradle` **does not auto-generate** `gradlew` and `gradlew.bat`.

### 6.3. BookApiApplication.java

```java
package com.example.bookapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookApiApplication.class, args);
    }
}
```

Uses this class as the Boot configuration root; `@WebMvcTest(BookController.class)` locates `@SpringBootConfiguration` up the package hierarchy. Do not accidentally place multiple `@SpringBootApplication` classes in the same test package, making configuration selection ambiguous.

## 7. Creating request/response DTOs and service contract

### 7.1. BookView.java: JSON representation

```java
package com.example.bookapi;

public record BookView(
        long id,
        String title,
        String author) {
}
```

Jackson serializes this record into an object with `id`, `title`, and `author`. Tests use `jsonPath` to verify field names and values, rather than comparing raw JSON strings with fixed key ordering.

### 7.2. CreateBookRequest.java: validation belongs to the input contract

```java
package com.example.bookapi;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateBookRequest(

        @NotBlank
        @Size(max = 80)
        String title,

        @NotBlank
        @Size(max = 60)
        String author) {
}
```

When the Controller uses `@Valid @RequestBody CreateBookRequest`, Spring MVC deserializes JSON into the record and runs Bean Validation. `title=""` or `author=" "` violates `@NotBlank`; a title longer than 80 characters violates `@Size(max=80)`. Tests should verify **HTTP 400**, a stable error contract, and that **the service is not called** when validation fails.

If a request property is null or missing, Bean Validation `@NotBlank` still handles null fields; with a Jackson record canonical constructor, keep in mind differences between missing and explicit null if a project uses `@JsonProperty(required=...)` or custom validation. Do not assume every incomplete JSON form yields the exact same error message.

### 7.3. BookService.java: dependency at the Controller boundary

```java
package com.example.bookapi;

import java.util.List;

public interface BookService {

    BookView getById(long id);

    List<BookView> findByAuthor(String author);

    BookView create(CreateBookRequest request);
}
```

The Controller depends only on the interface. In `@WebMvcTest`, Mockito provides an implementation to mock HTTP behavior; in `@SpringBootTest`, Spring creates the real `InMemoryBookService`.

### 7.4. BookNotFoundException.java

```java
package com.example.bookapi;

public final class BookNotFoundException
        extends RuntimeException {

    public BookNotFoundException(long id) {
        super("Book " + id + " not found");
    }
}
```

### 7.5. DuplicateBookException.java

```java
package com.example.bookapi;

public final class DuplicateBookException
        extends RuntimeException {

    public DuplicateBookException(String title) {
        super("Book title already exists: " + title);
    }
}
```

Internal exception messages can contain input data. **In API responses**, the sample uses a fixed `ProblemDetail.detail` so arbitrary input is not echoed back and clients do not rely on internal exception messages. This is a good choice for contract stability and limiting data exposure.

### 7.6. InMemoryBookService.java: implementation sufficient for full-context tests

```java
package com.example.bookapi;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class InMemoryBookService implements BookService {

    private final Map<Long, BookView> books =
            new ConcurrentHashMap<>();

    private final AtomicLong nextId =
            new AtomicLong(100);

    @Override
    public BookView getById(long id) {
        BookView found = books.get(id);

        if (found == null) {
            throw new BookNotFoundException(id);
        }

        return found;
    }

    @Override
    public List<BookView> findByAuthor(String author) {
        String filter = author == null
                ? ""
                : author.trim();

        return books.values().stream()
                .filter(book ->
                    filter.isEmpty()
                        || book.author().equalsIgnoreCase(filter))
                .sorted(Comparator.comparingLong(BookView::id))
                .toList();
    }

    @Override
    public synchronized BookView create(
            CreateBookRequest request) {

        String title = request.title().trim();
        String author = request.author().trim();

        boolean duplicate = books.values().stream()
                .anyMatch(book ->
                    book.title().equalsIgnoreCase(title));

        if (duplicate) {
            throw new DuplicateBookException(title);
        }

        long id = nextId.incrementAndGet();

        BookView saved = new BookView(id, title, author);
        books.put(id, saved);

        return saved;
    }
}
```

This is an **in-memory teaching implementation**, not a production repository. `synchronized` protects the duplicate-check→insert sequence within a single JVM. It does not replace **database unique constraints and transactions** in a real system. `ConcurrentHashMap` makes reads safer across independent HTTP calls; the response list is sorted by `id` for deterministic ordering in full-context tests.

For the slice test, the real service is **not used**: the Mockito mock determines each case, and the Controller must translate outcomes into the exact HTTP responses.

## 8. BookController.java: GET/list/POST contracts

```java
package com.example.bookapi;

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
@RequestMapping(
    path = "/api/books",
    produces = MediaType.APPLICATION_JSON_VALUE)
public class BookController {

    private final BookService books;

    public BookController(BookService books) {
        this.books = books;
    }

    @GetMapping("/{id}")
    public ResponseEntity<BookView> getById(
            @PathVariable long id) {

        return ResponseEntity.ok(books.getById(id));
    }

    @GetMapping
    public ResponseEntity<List<BookView>> list(
            @RequestParam(defaultValue = "") String author) {

        return ResponseEntity.ok(
                books.findByAuthor(author));
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(
            @Valid @RequestBody CreateBookRequest request) {

        BookView saved = books.create(request);

        URI resourceUri = URI.create(
                "/api/books/" + saved.id());

        return ResponseEntity.created(resourceUri)
                .body(saved);
    }
}
```

Reading the contract:
- GET `/api/books/42` calls `books.getById(42)`; returns HTTP 200 and JSON `BookView`.
- GET `/api/books?author=Ada` extracts query parameter `author`, returns HTTP 200 and a **JSON array**.
- GET `/api/books` passes `author=""` by default.
- POST `/api/books` accepts only `application/json`, deserializes `CreateBookRequest`, validates, and calls `books.create(request)`.
- Successful POST returns **201 Created**, header `Location: /api/books/{id}`, and the JSON body of the new resource.
- If the service throws `BookNotFoundException` or `DuplicateBookException`, `@RestControllerAdvice` converts the exception into an HTTP error.

**Do not have the Controller return `null` to signal a missing record.** Do not force clients to guess between 200-empty, 204, and 404; the contract must be consistent.

### 8.1. `@Valid` must be placed in the right spot

With `@Valid @RequestBody CreateBookRequest request`, Bean Validation runs after Jackson deserialization and before the service call. `@Valid` **does not run** if you simply invoke `new BookController(...).create(request)` in a Java unit test. That is why `MockMvc` is valuable: it exercises the real Spring argument resolver and validation infrastructure.

For `@PathVariable`/`@RequestParam` requiring `@Positive`, `@Min`, custom constraints, or class-level `@Validated` per Spring 6.2, method validation semantics must be explicitly understood. The sample project only uses `long` conversion for the path ID; `id="not-a-number"` is caught by MVC as a 400 due to type mismatch.

### 8.2. Content negotiation happens before the Controller in some cases

The GET handler defines `produces=application/json`. When a client sends `Accept: application/xml` and the app has no XML representation support, MVC can return 406 before the service is ever called. POST defines `consumes=application/json`; when a client sends `Content-Type: text/plain`, MVC returns 415. Tests should assert **the service was not called** on branches blocked at the MVC layer.

## 9. `@RestControllerAdvice` and `ProblemDetail`: errors with a stable schema

File `src/main/java/com/example/bookapi/BookApiExceptionHandler.java`:

```java
package com.example.bookapi;

import java.util.Comparator;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class BookApiExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            BookNotFoundException exception) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Requested book does not exist");

        body.setTitle("Book not found");
        body.setProperty("code", "BOOK_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(body);
    }

    @ExceptionHandler(DuplicateBookException.class)
    public ResponseEntity<ProblemDetail> conflict(
            DuplicateBookException exception) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "A book with that title already exists");

        body.setTitle("Duplicate book");
        body.setProperty("code", "DUPLICATE_BOOK");

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(body);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> invalidBody(
            MethodArgumentNotValidException exception) {

        var violations = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                    "field", error.getField(),
                    "message", error.getDefaultMessage() == null
                        ? "invalid"
                        : error.getDefaultMessage()))
                .sorted(Comparator.comparing(
                    item -> item.get("field")))
                .toList();

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request body failed validation");

        body.setTitle("Invalid book request");
        body.setProperty("code", "VALIDATION_ERROR");
        body.setProperty("violations", violations);

        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(body);
    }
}
```

**Why use `ProblemDetail`?** Spring Framework 6 supports RFC-style problem details with standard fields like `type`, `title`, `status`, `detail`, and `instance`; Spring's Jackson integration serializes `ProblemDetail` extension properties as top-level JSON fields (here `code`, `violations`).

The sample 404 response contract looks like this:

```json
{
  "type": "about:blank",
  "title": "Book not found",
  "status": 404,
  "detail": "Requested book does not exist",
  "code": "BOOK_NOT_FOUND"
}
```

This is a **minimal illustrative representation** of the meaningful fields; the serializer may add `instance` or order JSON keys differently. Tests do not compare the entire string verbatim. `Content-Type` is `application/problem+json` per the advice response.

### 9.1. Why not expose default exception messages as public API?

Messages from `MethodArgumentNotValidException` and Spring MVC's default error handling can change across framework versions, locales, or validation providers. If clients rely on exact long exception strings, a Spring upgrade can break contract tests even when API semantics did not change.

Keep:
- Standard HTTP `status`.
- Stable machine-readable `code` (`BOOK_NOT_FOUND`, `DUPLICATE_BOOK`, `VALIDATION_ERROR`).
- Stable input field names in `violations[*].field` per schema.
- Concise `detail`, free of internal stack traces or PII.

Validation `violations[*].message` can vary across Bean Validation providers/i18n; if the message text is not part of the public contract, tests should check only the failing field list and error code rather than hard-coding full validator messages.

### 9.2. Why is malformed JSON 400 different from validation 400?

- `{"title":"","author":""}`: valid JSON, DTO instantiated, `@Valid` fails → `MethodArgumentNotValidException`, sample advice returns ProblemDetail code `VALIDATION_ERROR`.
- `{broken`: invalid JSON syntax → typically `HttpMessageNotReadableException`, which does **not** enter this `MethodArgumentNotValidException` handler. Spring MVC defaults to 400; if an API wants the same ProblemDetail schema for both cases, add an appropriate handler and dedicated test.

Do not write a malformed JSON test and assert `VALIDATION_ERROR` unless a parse-error mapping exists. The sample test only asserts 400 and `verifyNoInteractions(books)` on the malformed branch.

### 9.3. Class-level `produces` and `problem+json`

`@RequestMapping(produces="application/json")` restricts the media types a successful handler can produce. Advice returns `application/problem+json` **when an exception occurs**. When testing error branches, do not mechanically send `Accept: application/problem+json` if the success mapping only declares JSON; let the request use `Accept: */*` (default when no Accept is set) and assert the `problem+json` response. In production APIs, clearly define content negotiation for both success and error representations.

## 10. `@WebMvcTest` in practice: 14 tests for the HTTP contract

File `src/test/java/com/example/bookapi/BookControllerSliceTest.java`:

```java
package com.example.bookapi;

import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.hasSize;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    BookService books;

    @Test
    void getBookReturns200WithJsonContract() throws Exception {
        BookView book = new BookView(
                42L, "Domain-Driven Design", "Eric Evans");

        given(books.getById(42L)).willReturn(book);

        mvc.perform(get("/api/books/{id}", 42)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title")
                .value("Domain-Driven Design"))
            .andExpect(jsonPath("$.author")
                .value("Eric Evans"));

        verify(books).getById(42L);
    }

    @Test
    void missingBookReturns404ProblemDetail() throws Exception {
        given(books.getById(404L))
            .willThrow(new BookNotFoundException(404L));

        mvc.perform(get("/api/books/{id}", 404))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.title")
                .value("Book not found"))
            .andExpect(jsonPath("$.detail")
                .value("Requested book does not exist"))
            .andExpect(jsonPath("$.code")
                .value("BOOK_NOT_FOUND"));

        verify(books).getById(404L);
    }

    @Test
    void listFilterPassesQueryParameter() throws Exception {
        given(books.findByAuthor("Ada")).willReturn(
                List.of(
                    new BookView(7L, "Algorithms A", "Ada"),
                    new BookView(9L, "Algorithms B", "Ada")));

        mvc.perform(get("/api/books")
                .param("author", "Ada")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$", hasSize(2)))
            .andExpect(jsonPath("$[0].id").value(7))
            .andExpect(jsonPath("$[1].title")
                .value("Algorithms B"));

        verify(books).findByAuthor("Ada");
    }

    @Test
    void emptyCollectionIsArrayNotNull() throws Exception {
        given(books.findByAuthor("")).willReturn(List.of());

        mvc.perform(get("/api/books"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$", hasSize(0)));

        verify(books).findByAuthor("");
    }

    @Test
    void createReturns201AndLocation() throws Exception {
        CreateBookRequest request =
                new CreateBookRequest(
                    "Effective Java", "Joshua Bloch");

        given(books.create(request)).willReturn(
                new BookView(
                    77L, "Effective Java", "Joshua Bloch"));

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(request)))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                "Location", "/api/books/77"))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(77))
            .andExpect(jsonPath("$.title")
                .value("Effective Java"))
            .andExpect(jsonPath("$.author")
                .value("Joshua Bloch"));

        verify(books).create(request);
    }

    @Test
    void invalidBodyReturnsFieldErrors() throws Exception {
        CreateBookRequest invalid =
                new CreateBookRequest("", " ");

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(invalid)))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.code")
                .value("VALIDATION_ERROR"))
            .andExpect(jsonPath(
                "$.violations[*].field",
                hasItems("title", "author")));

        verifyNoInteractions(books);
    }

    @Test
    void titleOverLimitReturns400() throws Exception {
        CreateBookRequest invalid =
                new CreateBookRequest("X".repeat(81), "Ada");

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(invalid)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("VALIDATION_ERROR"))
            .andExpect(jsonPath(
                "$.violations[*].field",
                hasItems("title")));

        verifyNoInteractions(books);
    }

    @Test
    void duplicateReturns409WithStableCode() throws Exception {
        CreateBookRequest request =
                new CreateBookRequest("Clean Code", "Author");

        given(books.create(request)).willThrow(
                new DuplicateBookException("Clean Code"));

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(request)))
            .andExpect(status().isConflict())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(409))
            .andExpect(jsonPath("$.code")
                .value("DUPLICATE_BOOK"))
            .andExpect(jsonPath("$.detail")
                .value(
                    "A book with that title already exists"));

        verify(books).create(request);
    }

    @Test
    void malformedJsonReturns400WithoutCallingService()
            throws Exception {

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{ broken"))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(books);
    }

    @Test
    void unsupportedRequestContentTypeReturns415()
            throws Exception {

        mvc.perform(post("/api/books")
                .contentType(MediaType.TEXT_PLAIN)
                .content("a plain text book"))
            .andExpect(status().isUnsupportedMediaType());

        verifyNoInteractions(books);
    }

    @Test
    void unacceptableRepresentationReturns406()
            throws Exception {

        mvc.perform(get("/api/books/{id}", 42)
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());

        verifyNoInteractions(books);
    }

    @Test
    void badPathVariableReturns400() throws Exception {
        mvc.perform(get("/api/books/{id}", "not-a-number"))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(books);
    }

    @Test
    void wrongRouteReturns404() throws Exception {
        mvc.perform(get("/api/unknown-books"))
            .andExpect(status().isNotFound());

        verifyNoInteractions(books);
    }

    @Test
    void unicodeTitlePreservedInJson() throws Exception {
        given(books.getById(8L)).willReturn(
                new BookView(
                    8L,
                    "Cấu trúc dữ liệu",
                    "Tác giả Việt"));

        mvc.perform(get("/api/books/{id}", 8))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("Cấu trúc dữ liệu"))
            .andExpect(jsonPath("$.author")
                .value("Tác giả Việt"));

        verify(books).getById(8L);
    }
}
```

There are **14 `@Test` methods** in this slice class. All interact with `MockMvc` via request builders, letting Spring MVC perform mapping, argument conversion, validation, handler invocation, and response serialization. None call `controller.create(...)` directly and claim it is an HTTP test.

### 10.1. Reading a successful GET test layer by layer

```java
given(books.getById(42L))
    .willReturn(new BookView(42L, "ABC", "Author"));

mvc.perform(get("/api/books/{id}", 42))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42));

verify(books).getById(42L);
```

This is an illustrative fragment of a test.
- `given`: prepares the return condition when the service is called.
- `mvc.perform`: sends a mock HTTP request through `DispatcherServlet`.
- `status()`: HTTP response semantics.
- `jsonPath`: serialization/schema of the JSON body.
- `verify`: service method was called with the right argument and not altered by controller routing.

A test with only `verify(books).getById(42L)` is **insufficient**: the controller could still return HTTP 500 or mis-serialize the body. Conversely, asserting only the body without verifying the collaborator could miss a bug passing the wrong ID into the service if the mock stub were overly broad.

### 10.2. Why use `ObjectMapper` to send JSON?

```java
.content(mapper.writeValueAsBytes(
    new CreateBookRequest("ABC", "Author")))
```

This is a fragment. It builds request JSON matching the Java record, avoiding quote-escaping mistakes, Unicode issues, and out-of-sync field renames. However, when **testing the exact JSON wire format**, you still need assertions on **keys and representation** independent of the same `ObjectMapper`; if both production code and test code change naming strategy together, a round-trip test can keep passing despite an accidental public API break.

In the sample suite, response assertions `jsonPath("$.title")` and `jsonPath("$.author")` verify the public contract rather than merely round-tripping a DTO with the same config.

### 10.3. When is `verifyNoInteractions` important?

For invalid POST bodies, malformed JSON, wrong `Content-Type`, and unacceptable `Accept`, the request must be stopped at the MVC layer before the Controller calls the service. `verifyNoInteractions(books)` proves that within the mocked bean's scope.

Do not rigidly apply `verifyNoMoreInteractions` to every endpoint just for strictness: if the service later adds a benign helper call that does not alter the public contract, tests become brittle. Use interaction verification when the interaction itself is part of the requirement (do not write to the DB if invalid, do not call downstream adapters on wrong media type).

### 10.4. Why not assert a verbatim JSON response string?

Compare:

```java
.andExpect(content().json(
    "{\"id\":42,\"title\":\"ABC\",\"author\":\"Author\"}"))
```

This is a valid fragment, though you should understand that `content().json` uses JSON comparison semantics unlike `content().string`. **A typical mistake** is comparing raw strings sensitive to property order and whitespace. Prefer `jsonPath` for contract fields, and JSON comparison when you want to verify the whole structure (configuring strict/lenient mode appropriately).

Never use `content().string("{...}")` to “lock field order” unless the API guarantees that order; JSON objects are unordered semantically.

## 11. `@SpringBootTest`: two cases to see the limits of a slice

`@WebMvcTest` tests Controller → Mock Service, so it **does not** prove that a POST actually saves data and a subsequent GET retrieves it. To verify the real Controller → Service flow in the in-memory project, use `@SpringBootTest + @AutoConfigureMockMvc` with the full context.

File `src/test/java/com/example/bookapi/BookApiFullContextTest.java`:

```java
package com.example.bookapi;

import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class BookApiFullContextTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void fullContextPostThenGetWorks() throws Exception {
        String title = "Title-" + UUID.randomUUID();

        CreateBookRequest request =
                new CreateBookRequest(title, "Tester");

        String location = mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(request)))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value(title))
            .andReturn()
            .getResponse()
            .getHeader("Location");

        assertThat(location)
                .startsWith("/api/books/");

        mvc.perform(get(location))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value(title))
            .andExpect(jsonPath("$.author")
                .value("Tester"));
    }

    @Test
    void fullContextUnknownBookReturns404()
            throws Exception {

        mvc.perform(get("/api/books/{id}",
                Long.MAX_VALUE))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                .value("BOOK_NOT_FOUND"));
    }
}
```

These two tests use the real `InMemoryBookService`, with no `@MockitoBean`. Randomizing the title avoids duplicate collisions when the full Spring context is cached across test methods; the test **does not assert a specific UUID**, only keeping the generated value for verification. This is context integration, yet **there is no real DB**, so do not market it as a persistence integration test.

**Important design note:** The full-context test has a mutable in-memory store. If running in parallel, manage fixture ownership and ensure assertions do not depend on total record count or execution order. In the sample, the unknown-book GET queries near `Long.MAX_VALUE`, which cannot collide with IDs starting at 100 in ordinary practice runs.

### 11.1. When should you use `RANDOM_PORT`?

If you want to prove embedded Tomcat/Jetty TCP listening, servlet container startup, network stack, or reverse-proxy-related behaviors, `@SpringBootTest(webEnvironment=RANDOM_PORT)` combined with an HTTP test client is closer to reality. However, the server handles requests on a different thread from the JUnit test thread; **test-managed `@Transactional` does not automatically cover the HTTP request's transaction**. When a DB is present, an explicit cleanup/transaction policy is needed.

For Controller HTTP mapping contracts, `MockMvc` is usually sufficient and faster. Not every HTTP contract test needs to open a socket.

## 12. Testing JSON schemas and contracts at the right stability level

### 12.1. JSON object vs JSON array

`GET /api/books/42` returns an object:

```json
{
  "id": 42,
  "title": "Domain-Driven Design",
  "author": "Eric Evans"
}
```

`GET /api/books` returns an array:

```json
[]
```

Never return `null` instead of an empty array when the client contract specifies a collection. Testing `jsonPath("$", hasSize(0))` guards this, beyond merely checking 200.

### 12.2. Checking object fields without over-relying on order

With `jsonPath("$.id").value(42)` and `jsonPath("$.title").value(...)`, the test checks specific keys and values. If the public API guarantees a required field is always present, assert its presence and type. You can use:

```java
.andExpect(jsonPath("$.id").isNumber())
.andExpect(jsonPath("$.title").isString())
.andExpect(jsonPath("$.author").isString())
```

This is a fragment inside a request builder and MockMvc result chain. If the API enforces nullability/versioning rules, assert them according to the OpenAPI/JSON Schema contract instead of relying solely on default Jackson behavior.

### 12.3. `BigDecimal`, `Instant`, and non-string enums

A production API with `BigDecimal amount`, `Instant createdAt`, or an enum status:
- Avoid asserting floats with tolerance if the JSON contract is exact decimal; parse response bytes into `JsonNode`/`BigDecimal`.
- Assert UTC/ISO-8601 format if required by the contract; inject `Clock` for deterministic timestamps.
- Assert wire enum values (e.g., `"ACTIVE"`) as the contract, rather than relying on `toString()` if the app uses `@JsonValue`.
- Control timezone/locale explicitly when testing date formatting; do not mutate JVM global defaults in a concurrent suite.
- When using Jackson `@JsonProperty` and `@JsonInclude`, write dedicated tests for field names and missing/null behavior.

The sample project keeps representations simple so learners focus on `@WebMvcTest` without noise from custom serializers.

### 12.4. `Content-Type` assertions should handle charsets and versions properly

Use `content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)` when checking JSON compatibility without locking down irrelevant charset parameters. When the contract requires **exact** `application/problem+json`, assert the corresponding media type; if servers/filters append a charset, choose the appropriate matcher.

Never assert only `status().isOk()` and assume JSON conversion occurred; if a controller accidentally returns HTML or plain text, clients can still fail despite status 200.

## 13. Spring Security/CSRF and filters in `@WebMvcTest`

**The sample project does not add `spring-boot-starter-security` to the classpath.** Hence POST `/api/books` in the tests above is not blocked by Security's default CSRF protection. In a real application using Spring Security, `@WebMvcTest` normally loads security filters; the same POST can return **403** if a CSRF token is missing or **401** if authentication is invalid.

### 13.1. Do not disable filters just to make tests pass

Anti-pattern:

```java
@WebMvcTest(BookController.class)
@AutoConfigureMockMvc(addFilters = false)
class TestWithoutSecurityFilters {
    // Disabling filters does not verify the security contract.
}
```

This is an illustrative fragment. It may help when the goal is **explicitly controller mapping only**, but you must not claim authentication, authorization, or CSRF was tested. If the API has security requirements, maintain a separate suite **keeping filters enabled** to assert 401/403/200 for the right roles.

### 13.2. Testing Security properly when dependencies are present

To test protected endpoints:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-security'
testImplementation 'org.springframework.security:spring-security-test'
```

This is an **additional dependency fragment** for projects using Security, **not part of the runnable build in Section 6**. An example MockMvc request:

```java
mvc.perform(post("/api/books")
        .with(user("editor").roles("EDITOR"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content(validJson))
    .andExpect(status().isCreated());
```

This fragment requires static imports `user`, `csrf`, `validJson`, and a security config enforcing the role policy. **You cannot assume 201 just because `user+csrf` are passed** if the endpoint requires another role or a different authentication adapter; tests must match the real contract.

For stateless token-based APIs, CSRF may be disabled per security policy; inspect the actual filter chain rather than blindly adding `.with(csrf())` as if every POST needed it.

### 13.3. `ControllerAdvice`, filters, and the error contract

Exceptions thrown by Controllers/services pass through `@ExceptionHandler` in advice. Exceptions raised by a **Servlet Filter** (e.g., an authentication filter) may bypass that exception handler chain and render via `AuthenticationEntryPoint`/`AccessDeniedHandler`. Therefore error JSON schemas for 401/403 may differ from 400/404/409 unless Security configuration is aligned; test them separately.

CORS preflight `OPTIONS` is also an HTTP contract; when a CORS policy is designed, test `Origin`, `Access-Control-Request-Method`, and `Access-Control-Allow-Origin` against the real filter/MVC config. Never infer correct CORS from a successful GET's status code.

## 14. Mocking does not mean testing service business logic

`@MockitoBean BookService books` replaces the real service with a mock inside the MVC slice. This has two major consequences:

1. **Benefit**: tests do not depend on a database, remote API, or complex logic. They stay focused on Controller HTTP mapping, validation, headers, and error mapping.
2. **Limitation**: if `InMemoryBookService` has a duplicate-detection bug or the persistence repository throws an unexpected exception, slice tests can still pass because Mockito returns whatever fake result you stubbed.

Separate responsibilities:
- **Controller contract tests**: `MockMvc` + `@WebMvcTest` + mocked collaborator.
- **Service unit tests**: instantiate service + fake repo, business invariants, exceptions.
- **Repository slice tests**: `@DataJpaTest`/`@JdbcTest` with an appropriate DB configuration.
- **Full integration**: `@SpringBootTest` with real dependencies/containers when contracts require it.
- **Consumer contract**: OpenAPI/JSON schema/provider-client verification if the team maintains a public API.

Never use a single `@WebMvcTest` as “end-to-end proof” of the entire system.

### 14.1. Stubbing the right exception types with Mockito

```java
given(books.getById(404L))
    .willThrow(new BookNotFoundException(404L));
```

This is a fragment. The Controller calls the service and the advice returns 404; the test asserts both the status and the machine-readable code. If the mock returns `null` or a different exception, the test does not prove the right branch. When adding an exception handler, never catch `Exception.class` and always map it to 404: it hides 500 errors and disguises system outages as “record not found”.

### 14.2. `@MockitoBean` and the Spring context cache

A `@WebMvcTest` uses Spring's TestContext cache. Mockito mocks in the context may be reset by Spring Test listeners between test methods. In a suite with JUnit parallel execution enabled, multiple tests can share the same context/mock state: one test may stub/verify/reset while another runs. If flaky verification occurs:
- Keep methods sequential by default within classes using `@MockitoBean`, unless mocks/fixtures are genuinely isolated.
- Do not abuse `@DirtiesContext` to reset everything, as it slows bootstrapping and can disrupt concurrent tests.
- Avoid static mocks or shared `MockMvc` helpers holding mutable per-test state.
- If multiple beans share a type, use `@Qualifier`/name on `@MockitoBean` or clarify collaborators so the wrong bean isn't mocked.

In Spring Framework 6.2, `@MockitoBean` offers `enforceOverride=true` if you want to **fail when no existing bean is present to replace** instead of silently creating one; in an MVC slice, services are typically not scanned so the default `REPLACE_OR_CREATE` is appropriate.

### 14.3. Over-mocking strips tests of value

Do not mock `MockMvc`, `ObjectMapper`, `RequestMappingHandlerAdapter`, `DispatcherServlet`, and every converter just to test a Controller. Mocking web framework internals turns the test back into a plain Java unit test while pretending to test HTTP semantics.

Conversely, never mock `BookController` inside `@WebMvcTest`: the Controller must be the real subject under test, mocking only collaborators at the boundary.

## 15. `@WebMvcTest` with exception handlers, filters, and custom serialization

If the Controller uses:
- Custom `HandlerMethodArgumentResolver`: must be loaded/imported by the slice.
- Custom `Converter<String, CustomId>`: test route argument conversion with the real converter.
- Jackson `Module`/custom serializer: import the production config and assert the wire format.
- `@ControllerAdvice` outside the base scan package: import the advice explicitly.
- `@ConfigurationProperties`: use `@EnableConfigurationProperties` or `@Import` per Boot docs.
- Spring Security configuration: keep the filter chain if testing auth/CSRF/CORS.
- Locale/resolver: send `Accept-Language` and assert messages if localized errors are part of the contract.

**Rule:** Do not open the full application context every time a slice misses a bean. First determine whether that bean truly belongs to the web contract, then import or mock **at the exact boundary**. Never resort to unrestricted `@ComponentScan` or `@SpringBootTest` as an unthinking workaround when your goal is still an MVC slice.

### 15.1. Why does `@WebMvcTest` sometimes fail with "No qualifying bean"?

If `BookController`'s constructor takes `BookService`, the slice does not scan `@Service` beans, so Spring finds no matching bean. The right fix for a Controller test is:

```java
@MockitoBean
BookService books;
```

Do not add `@Import(InMemoryBookService.class)` unless the test genuinely intends to use the real service (in which case the goal changes and service dependencies may be pulled in). To keep the slice fast, mock the service and write separate service tests.

### 15.2. Why did a response return 404 without running the advice?

Two kinds of 404:
- `BookNotFoundException` thrown by the service when `/api/books/42` matched a route; advice creates `ProblemDetail` with code `BOOK_NOT_FOUND`.
- `/api/unknown-books`: no controller route matches; Spring returns 404 via default handling. There is no reason to expect `BookNotFoundException` advice to handle this case.

If the API requires every 404 to share the same error schema, configure no-handler/static-resource exception mapping for your Spring Framework version and test it separately; do not merely add `@ExceptionHandler(BookNotFoundException.class)` and assume it catches every missing route 404.

## 16. Anti-pattern: calling a Controller directly and treating it as an HTTP test

Wrong for the goal:

```java
BookController controller = new BookController(books);
ResponseEntity<BookView> response =
        controller.getById(42L);
assertThat(response.getStatusCode().value())
        .isEqualTo(200);
```

This fragment assumes `books` has already been created. It only checks the **Java method return value**; it bypasses:
- `@GetMapping` route resolution.
- `@PathVariable` conversion.
- `@RequestBody` and Jackson.
- `@Valid` argument validation.
- `@RestControllerAdvice` exception mapping.
- Servlet Filters/interceptors.
- Content negotiation and JSON response serialization.

Direct tests can be useful for non-MVC logic, but they are not proof of an HTTP contract. When a requirement states “the Controller returns status 400 if the body is invalid”, you need `MockMvc.perform(post(...))`.

## 17. Testing 401/403/404/409/415/406: reading errors at the right layer

| Status | When in this lab? | Layer producing the status | Mock service needed? |
|---|---|---|---|
| 200 | GET BookView or list | Controller + response conversion | Stub result |
| 201 | Valid POST CreateBookRequest | Controller ResponseEntity.created | Stub create |
| 400 | `@Valid` fails | MVC validation + advice | Service not called |
| 400 | Malformed JSON | HttpMessageConverter/MVC | Service not called |
| 400 | Path id cannot parse as long | Argument resolver/converter | Service not called |
| 404 | Service throws BookNotFoundException | Advice | Stub exception |
| 404 | Non-existent URL | MVC handler mapping | Service not called |
| 409 | DuplicateBookException | Advice | Stub exception |
| 415 | POST text/plain violating consumes | MVC mapping/media type | Service not called |
| 406 | GET accepting only XML violating produces JSON | MVC content negotiation | Service not called |
| 401 | Unauthenticated when Security is present | Security filter/entrypoint | Depends on config |
| 403 | Unauthorized or missing CSRF token | Security filter/access denied | Depends on config |
| 500 | Unexpected server-side failure | Error handling pipeline | Never convert to 404/200 |

**Note on error response schema:** In the sample, 404 from `BookNotFoundException`, 409, and validation 400 return `application/problem+json` with `code`. Parse/path 400s, 406, 415, or route 404s may use MVC default error handling and need not include `code`. This is an **intentional contract of the example**; a production API requiring one uniform schema must add corresponding handlers/filters and tests.

### 17.1. An assertion that is too weak

```java
mvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{}"))
    .andExpect(status().is4xxClientError());
```

This is a fragment. It passes for 400, 403, 404, 405, 406, or 415; yet those statuses mean very different things. For a validation contract, assert **400**, `VALIDATION_ERROR`, and the `title/author` fields when Bean Validation failure is expected. For a security contract, assert 401 or 403 per policy, not merely “4xx”.

### 17.2. An assertion that is too brittle

```java
assertThat(responseText).isEqualTo(
    "{\"title\":\"ABC\",\"id\":1,\"author\":\"Ada\"}");
```

This is an anti-pattern fragment: field order and whitespace are serializer details, not part of the JSON semantic contract. Unless a public API promises byte-level serialization (such as a signed payload), avoid snapshotting raw strings like this.

## 18. Debugging failing `@WebMvcTest` runs

| Symptom | Common cause | How to verify and fix |
|---|---|---|
| `NoSuchBeanDefinitionException BookService` | Slice does not scan `@Service` | Add `@MockitoBean` for the service |
| Context loads too many beans/DB | `@Import` or `@ComponentScan` too broad | Narrow slice and dependency boundary |
| ControllerAdvice not applied | Advice outside scan root, wrong exception type | Check scan/import and exception handler mapping |
| POST gets 403 instead of 201 | Spring Security CSRF/filter active | Use `spring-security-test`, auth+csrf per policy |
| GET gets 401 | Security requires authentication | Test mock user/token or adjust expectations |
| `status 415` sending JSON | Forgot Content-Type or different consumes | Send `contentType(application/json)` |
| `status 406` on GET | Accept incompatible with produces | Match Accept to contract |
| `status 400` before service | JSON parse/type conversion/validation | Print `andDo(print())`, inspect exception |
| Invalid POST still calls service | Missing `@Valid`/validation starter | Check `@Valid @RequestBody` and dependencies |
| `jsonPath` misses field | Jackson naming/visibility/`@JsonIgnore` | Inspect actual response body |
| Null `Location` | Controller returned 200 instead of created | Use `ResponseEntity.created` |
| 404 test has different JSON code | Confused route 404 with record 404 | Stub service exception and match route |
| 409 returns 500 | Advice lacks handler for DuplicateBookException | Add/check `@ExceptionHandler` |
| `verifyNoInteractions` fails | Controller/service still invoked | Inspect validation/mapping timing |
| Test passes only in isolation | Shared mock/context/global state in parallel suite | Isolate fixtures, avoid parallel shared Mockito |
| `@WebMvcTest` finds 2 Boot configurations | Multiple `@SpringBootConfiguration` | Specify context root in right package |
| App has both WebFlux and MVC | Boot selects web app type | Use `@WebMvcTest` specifically for Servlet MVC |
| `@MockBean` import fails on version | Spring Framework/Boot API drift | Boot 3.5 prefers `@MockitoBean` |
| 500 response serializing DTO | Jackson module/missing getters/record mapping | Test real ObjectMapper/MVC converters |
| Mock returns null because unstubbed | `given(...)` argument mismatch | Stub accurately, verify argument |
| Custom filter skipped | Test disabled `addFilters` or filter bean unscanned | Enable/import filter when part of HTTP contract |
| `@SpringBootTest` slower than slice | Loads full Spring context | Use `@WebMvcTest` for MVC-only contracts |
| Task `NO-SOURCE` or 0 tests | Wrong Gradle/JUnit discovery/filter | Check `useJUnitPlatform`, reports/test names |

### 18.1. MockMvc `andDo(print())` to inspect reality

When debugging a tricky test, temporarily add:

```java
mvc.perform(get("/api/books/{id}", 42))
        .andDo(print())
        .andExpect(status().isOk());
```

This fragment requires static import `org.springframework.test.web.servlet.result.MockMvcResultHandlers.print`. Output displays the request, selected handler, resolved exception, and response fields. Do not leave `print()` scattered across all CI tests if logs can contain sensitive data; use it selectively for diagnosis.

### 18.2. JSON assertion failures vs service failures

If `verify(books).getById(42L)` passes while `jsonPath("$.title")` fails:
- Routing into the Controller probably worked.
- It is unlikely to be a business service bug, since the service is mocked.
- Check Jackson serialization, response DTO, naming strategy, `@JsonIgnore`, converters, and response media type.
- Read `MockHttpServletResponse.getContentAsString()` while debugging rather than arbitrarily changing expected values to make the test green.

Conversely, if status 404 occurs before Mockito is called, the route likely did not match; inspect the request method, path, `produces`, and `consumes` before suspecting the service.

## 19. Testing the same contract along positive and negative paths

A **positive** case alone only proves valid requests work. For solid coverage:
- GET existing: 200 + JSON object + exact route ID.
- GET missing: 404 + stable ProblemDetail code.
- GET list with filter: 200 + JSON array + query parameter passed to service.
- GET empty list: 200 + `[]`, not null.
- Valid POST: 201 + Location + body.
- POST blank fields: 400 + validation fields, service not called.
- POST oversized field: 400 + title validation.
- Duplicate POST: 409 + conflict code.
- Malformed JSON: 400, service not called.
- Wrong Content-Type: 415.
- Unsupported Accept: 406.
- Wrong path ID type: 400.
- Non-existent route: 404, distinct from record 404.
- Unicode: preserved without encoding corruption.
- Full context: POST→GET through the real service, catching bugs beneath the Controller slice.

This is not a checklist to blindly “tick off” on every API. For a GET-only endpoint, do not invent POST tests; for an API without uniqueness constraints, do not fabricate 409s. Your test matrix must come from the real system's resource and error contracts.

## 20. An API contract test policy to avoid brittle tests

### 20.1. Keep machine-readable error codes

Clients should branch on public `status` + `code`, not parse localized `detail` text. Renaming `BOOK_NOT_FOUND` to `NOT_FOUND_BOOK` is an **API breaking change** requiring review/versioning or backward compatibility.

### 20.2. Never expose internal stack traces in error JSON

`ProblemDetail` may carry a brief `detail` and a `type` URI referencing error docs; it does not need to expose class names, SQL, filesystem paths, or credentials. Testing `jsonPath("$.code")` matters more than asserting full exception messages.

### 20.3. API schema changes must be caught

If `BookView.title` is renamed to `name`, the `$.title` test should fail because the client contract changed. Do not merely deserialize the response into the updated `BookView` and assert object equality: if the test model changes alongside production code, tests can miss breaking changes. On large public APIs, combine OpenAPI diff/schema checks with consumer-driven contract tests.

### 20.4. Do not mix MockMvc controller tests with DB assertions

In `@WebMvcTest`, there is no real repository. If a test writes:

```java
assertThat(bookRepository.count()).isEqualTo(1);
```

that fragment is out of scope (no repository exists in the slice). A Controller test must focus on the HTTP response and service invocation. Inserts, commits, and rollbacks belong to service/repository/full integration suites.

### 20.5. Avoid shared mutable mock state under parallelism

JUnit parallel execution inside a cached Spring context can cause Mockito stubbing/resets across tests to collide. If a suite uses `@MockitoBean`, do not treat it as a per-thread bean. Run the test class with default sequential semantics or design test context isolation before optimizing concurrency.

## 21. Practicing extensions for new requirements

### 21.1. Adding DELETE per 204 contract

If the API defines `DELETE /api/books/{id}` returning 204 upon deletion:
- The service has `delete(id)` or checks for not-found.
- Controller `@DeleteMapping("/{id}")` returns `ResponseEntity.noContent().build()`.
- Success test asserts `status().isNoContent()` **and an empty body**.
- Not-found test asserts 404 ProblemDetail.
- If Spring Security is present, test CSRF/auth policy on DELETE.

Do not add this endpoint to the sample above so code, controller, and tests stay aligned; this is an extension exercise.

### 21.2. Adding pagination/query filters

For `GET /api/books?page=0&size=20`:
- Test `@RequestParam` integer parsing.
- Test invalid `page=-1` or `size > max` if business validation is implemented.
- Body includes `items`, `page`, `size`, `total` matching the published schema.
- Assert ordering **only when** the API contract guarantees ordering.
- Mock the service with the exact `PageQuery`; full DB pagination belongs in the data layer.

Do not keep using `jsonPath("$[0]")` once the real schema changes from a bare array to a paged object.

### 21.3. Adding ETag or conditional GET

If the API supports `ETag` and `If-None-Match`:
- Assert the `ETag` response header.
- Requests with matching `If-None-Match` return 304 if policy requires it.
- 304 carries no body.
- Clarify which controller/filter/service computes the ETag; the test slice only loads the relevant component.
- Never assert unstable ETag hashes derived from uncontrolled timestamps or random data.

## 22. Running Gradle/JUnit and reading reports

A Gradle wrapper compatible with Spring Boot 3.5 and Java 17 toolchain is needed; if missing, use a suitable Gradle installation to generate the wrapper. The lesson project provides `settings.gradle`, `build.gradle`, Java sources, and tests; it **does not** generate `gradlew` automatically.

Linux/macOS:

```bash
./gradlew test --tests "com.example.bookapi.BookControllerSliceTest"
./gradlew test --tests "com.example.bookapi.BookApiFullContextTest"
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.bookapi.BookControllerSliceTest"
.\gradlew.bat test --tests "com.example.bookapi.BookApiFullContextTest"
.\gradlew.bat test
```

When diagnosing a single method:

```bash
./gradlew test --tests "com.example.bookapi.BookControllerSliceTest.invalidBodyReturnsFieldErrors" --info
```

**Expected from source:** 14 methods in `BookControllerSliceTest` + 2 methods in `BookApiFullContextTest` = **16 JUnit Jupiter `@Test` methods**. There are no `@Disabled` or intentionally flaky tests in the project. Do not claim all 16 tests ran and passed before Gradle actually executes them.

### 22.1. Read reports, not just `BUILD SUCCESSFUL`

Gradle HTML report:

```text
build/reports/tests/test/index.html
```

JUnit XML results:

```text
build/test-results/test/
```

Verify:
- Number of tests **discovered**, executed, failed, skipped.
- `No tests found`, `NO-SOURCE`, `UP-TO-DATE`, `FROM-CACHE` in Gradle task output.
- Actual JUnit test names and stack traces.
- Context bootstrap duration, exception converters/validation, Mockito mismatches.
- Whether any test was filtered out by `--tests` or tags.

`BUILD SUCCESSFUL` on a cached/skipped task does not prove tests ran in the current build. `--rerun-tasks` removes doubt about Gradle up-to-date caching when investigating, though it is unnecessary on every PR if CI caching is well managed.

### 22.2. Distinguishing build errors from HTTP contract failures

If Gradle fails because dependencies fail to resolve, that is not an HTTP test failure. If JUnit context fails immediately for a missing bean, that is a **test configuration failure**, not a Controller returning 500. When a body assertion fails, inspect the `MockMvc` response, selected handler, resolved exception, and `@ControllerAdvice` before editing business code.

## 23. QA Checklist for response contracts

- [ ] `@WebMvcTest(Controller.class)` clearly scopes the subject under test.
- [ ] The Controller under test is a real bean, not mocked.
- [ ] Service-layer collaborators are `@MockitoBean`/mocked appropriately.
- [ ] `MockMvc` is auto-configured, without assuming a server socket is listening.
- [ ] Exact URL, path, query, and HTTP method are verified.
- [ ] Positive tests exist for 200/201 matching the contract.
- [ ] For POST 201, `Location` and body are asserted if specified by the API.
- [ ] Response `Content-Type` is compatible with JSON or `problem+json` on the right branch.
- [ ] JSON field names/values/types are asserted with `jsonPath` or JSON-aware comparison.
- [ ] Empty collections return `[]` if specified by the public contract.
- [ ] `@Valid @RequestBody` and the validation starter are active.
- [ ] Invalid/malformed bodies never call the service.
- [ ] Bean Validation 400s are distinguished from JSON parse/type conversion 400s.
- [ ] Record-not-found 404 has its own code; route-not-found is understood separately.
- [ ] Duplicate conflict 409 is mapped by `@RestControllerAdvice`.
- [ ] 415 is tested on wrong request `Content-Type` and 406 on wrong `Accept`.
- [ ] Error schema has `status`, `title`, `detail`, `code` per contract.
- [ ] No internal exception messages, SQL, stack traces, or PII are exposed.
- [ ] Assertions do not arbitrarily lock JSON key order or auto-generated timestamps.
- [ ] `verify(books).method(...)` checks exact arguments when interaction is part of the contract.
- [ ] `verifyNoInteractions` is not misused as a blanket criterion for every request.
- [ ] If Spring Security is present, tests cover auth/CSRF/filter chain per real policy.
- [ ] `addFilters=false` is never used to claim an endpoint is secured.
- [ ] `@WebMvcTest` is not confused with `@WebFluxTest` or `@SpringBootTest`.
- [ ] Separate service/full integration tests exist for persistence and business constraints.
- [ ] Mockito mocks/context cache do not race under parallel JUnit execution.
- [ ] Classpath/Boot BOM/JUnit Launcher versions are compatible.
- [ ] Real JUnit reports are inspected before reporting a runtime pass.

## 24. References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): scope of `@WebMvcTest`, `MockMvc`, `@MockitoBean`, `@AutoConfigureMockMvc`, and test contexts.
- [Spring Boot 3.5 — Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): testing with Security/MockMvc.
- [Spring Framework 6.2 — @MockitoBean/@MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): bean override scopes, attributes, qualifiers.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): standalone/web application context setup, request builders, and assertions.
- [Spring Framework — HTTP message conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/message-converters.html): Jackson converters, content negotiation.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `@RequestBody`, method validation.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, and `@ExceptionHandler`.
- [Spring Framework — @ControllerAdvice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html): scope and exception mapping.
- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): mock users, CSRF, and filter integration.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `Test` tasks, filters, reports.
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/): JUnit 5 assertions, annotations, and execution.

**Conclusion:** `@WebMvcTest` verifies the **HTTP contract** of a Spring MVC Controller using the real web framework and a mocked service: routing, conversion, validation, headers, JSON, and error mapping. To test well, define each 200/201/400/404/409/415/406 contract clearly, assert status + body + headers + service interactions as needed, and keep a stable error schema like `ProblemDetail` with a distinct `code`. `@MockitoBean` keeps tests focused on the web layer without proving persistence/service behavior; `@SpringBootTest + @AutoConfigureMockMvc` or a real HTTP server provides the complementary layer when needed. Read actual JUnit reports rather than treating direct method calls as proof of correct HTTP responses.