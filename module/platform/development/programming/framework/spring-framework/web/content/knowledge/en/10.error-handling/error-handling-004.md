# HandlerExceptionResolver and ResponseEntityExceptionHandler in Spring MVC

## 1. What Problems Do These Two Components Solve?

In Spring MVC, a request can fail **before the controller is called**, **during controller execution**, or **while writing the response**. Examples include malformed JSON, a query parameter that cannot be parsed as a number, Bean Validation violations, missing resources, or exceptions from a service.

Spring MVC provides two related layers with distinct roles:

- **`HandlerExceptionResolver`** is the **infrastructure contract** used by `DispatcherServlet` to delegate exception handling to resolvers. Multiple implementations can exist, forming a chain called in order.
- **`ResponseEntityExceptionHandler`** is a **base class for `@ControllerAdvice`** that returns `ResponseEntity` with standard error responses for many common Spring MVC exceptions. This class itself is **not an implementation of `HandlerExceptionResolver`**: Spring invokes its `@ExceptionHandler` methods through `ExceptionHandlerExceptionResolver`.

This is the most important distinction in this lesson. Typically, REST applications customize errors using **`@RestControllerAdvice` + extending `ResponseEntityExceptionHandler`** or custom `@ExceptionHandler` methods. Only write a custom `HandlerExceptionResolver` if you truly need control at the resolver-chain level.

Examples of different errors requiring appropriate responses:

| Error | Typical exception | Common HTTP status |
| --- | --- | --- |
| Unreadable JSON body | `HttpMessageNotReadableException` | 400 Bad Request |
| Invalid `@Valid @RequestBody` | `MethodArgumentNotValidException` | 400 Bad Request |
| Constraint directly on controller parameter, Spring 6.1+ | `HandlerMethodValidationException` | 400 for input errors; can be 500 for return-value errors |
| Missing required query parameter | `MissingServletRequestParameterException` | 400 Bad Request |
| Request uses disallowed HTTP method | `HttpRequestMethodNotSupportedException` | 405 Method Not Allowed |
| No acceptable representation per `Accept` | `HttpMediaTypeNotAcceptableException` | 406 Not Acceptable |
| Request body has unsupported media type | `HttpMediaTypeNotSupportedException` | 415 Unsupported Media Type |
| Business entity not found | Application-defined domain exception | Usually 404 Not Found |
| Unhandled application bug | `NullPointerException` or similar | 500 Internal Server Error |

The final status depends on resolver configuration, `@ControllerAdvice`, filters, Spring Security, Servlet container, and application code. Do not treat this table as an automatic guarantee for every exception.

## 2. Error Lifecycle Inside `DispatcherServlet`

Simplified flow:

```text
HTTP request
      |
Servlet Filter chain (Security, logging, ...)
      |
DispatcherServlet
      |
HandlerMapping -> HandlerAdapter -> Controller
      |                                |
      |                           exception thrown
      +------------------------------->|
      |
      v
HandlerExceptionResolver chain
      |
      +-- ExceptionHandlerExceptionResolver
      |     local @ExceptionHandler / @ControllerAdvice
      |     ResponseEntityExceptionHandler (via advice)
      |
      +-- ResponseStatusExceptionResolver
      |     @ResponseStatus / ResponseStatusException
      |
      +-- DefaultHandlerExceptionResolver
      |     standard Spring MVC errors -> HTTP status
      |
      +-- other resolvers if registered by application
      |
      v
HTTP error response / ModelAndView
      |
      +-- unhandled? May propagate to Servlet container,
          error dispatch, Spring Boot /error (depending on case)
```

**The order above is the typical default MVC configuration**, not an immutable order when an application adds resolvers and `Ordered`. A resolver that handles the exception stops the chain there; subsequent resolvers are normally not called.

`HandlerExceptionResolver` has the method:

```java
ModelAndView resolveException(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex);
```

This is an illustrative API signature, **not a standalone method to compile with `javac`**. In modern Spring versions, the `handler` parameter may be `null` when no handler has been selected yet. The contract has three outcomes:

- Returning a **non-empty `ModelAndView`**: the exception is handled; Spring can render the specified view.
- Returning an **empty `new ModelAndView()`**: the exception is handled and the response has already been prepared; no view rendering is needed.
- Returning **`null`**: the resolver **did not handle** the exception; `DispatcherServlet` tries the next resolver.

**Do not return `null` after writing the response yourself**, if your goal is to finish handling. Doing so can cause another resolver to also write to the response, resulting in double-writes or wrong statuses.

Exceptions thrown from a Servlet Filter **before entering `DispatcherServlet`** do not automatically pass through the MVC resolver chain. Likewise, errors occurring after the response is committed cannot arbitrarily be replaced with a new JSON error body.

## 3. Key `HandlerExceptionResolver` Implementations

### 3.1. `ExceptionHandlerExceptionResolver`

Executes `@ExceptionHandler` methods inside controllers and `@ControllerAdvice`/`@RestControllerAdvice` beans.

Local declaration example:

```java
@RestController
class ProfileController {

    @GetMapping("/profiles/{id}")
    String profile(@PathVariable long id) {
        if (id <= 0) {
            throw new IllegalArgumentException("invalid id");
        }
        return "profile-" + id;
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> badId(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body("Invalid profile id");
    }
}
```

This is an illustrative Spring MVC class requiring Spring imports. This handler **applies only to that controller**; to reuse across the application, move it to a global advice.

Local `@ExceptionHandler` methods are evaluated before global advices. Across multiple advices, Spring uses `@Order`/`Ordered` to determine precedence; a **root exception match** generally takes precedence over a cause match within **the same advice**, whereas a cause match in a higher-precedence advice can beat a root match in a lower-precedence advice. Therefore, avoid high-precedence broad handlers like `@ExceptionHandler(Exception.class)` without a clear strategy.

### 3.2. `ResponseStatusExceptionResolver`

Reads `@ResponseStatus` on exceptions or `ResponseStatusException` and translates them into the appropriate HTTP status.

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
class BookNotFoundException extends RuntimeException {
    BookNotFoundException(long id) {
        super("Book " + id + " not found");
    }
}
```

When this exception is thrown, `ResponseStatusExceptionResolver` can map it to HTTP 404 **if an earlier resolver has not already handled it**. `@ResponseStatus` does not by itself provide a stable JSON error schema, custom `code` field, or structured field errors.

Spring 6+ supports `ProblemDetail` and `ErrorResponse`; in applications wanting consistent error output, a `@RestControllerAdvice` returning `ProblemDetail`/`ResponseEntity` is usually more convenient.

### 3.3. `DefaultHandlerExceptionResolver`

Handles many standard Spring MVC exceptions (such as unsupported HTTP method, missing request parameter, unsuitable media type) and translates them to their corresponding HTTP statuses. It **does not automatically understand custom business exceptions** like `CustomerNotFoundException` or `InventoryConflictException`.

For JSON APIs, the `ResponseEntityExceptionHandler` base class can intercept many MVC errors and produce `ProblemDetail` responses before reaching the default resolver. If no matching advice exists, the actual response may be completed by the default resolver and the Servlet container / Spring Boot error handling layer.

### 3.4. `SimpleMappingExceptionResolver`

A resolver that maps exception class names to **view names**. Typically useful for traditional MVC applications rendering JSP/Thymeleaf HTML error pages.

For REST APIs returning JSON, `@RestControllerAdvice` or `ResponseEntityExceptionHandler` is usually preferable. Do not configure an HTML error view resolver that catches every error on JSON endpoints and sends unexpected HTML to clients.

## 4. What Does `ResponseEntityExceptionHandler` Solve?

The class `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` provides an `@ExceptionHandler` covering many standard Spring MVC exceptions, building a `ResponseEntity<Object>` with status, headers, and body. Spring Framework 6+ integrates `ProblemDetail` support; in Framework 6.2, the error format follows **RFC 9457**.

Standard usage:

```java
@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {
    // Override protected handleXxx(...) when customization is needed
    // or declare @ExceptionHandler for custom domain errors.
}
```

This is a fragment requiring imports; `ResponseEntityExceptionHandler` handles the known set of Spring MVC exceptions, while custom application exceptions **need their own `@ExceptionHandler` methods**.

Typical hooks available to override in **Spring Framework 6.1/6.2**:

| Protected method | When to use |
| --- | --- |
| `handleMethodArgumentNotValid` | Customize Bean Validation errors on DTOs |
| `handleHandlerMethodValidationException` | Customize native method validation errors (Spring 6.1+) |
| `handleHttpMessageNotReadable` | Standardize malformed or undeserializable JSON |
| `handleHttpRequestMethodNotSupported` | 405 and metadata about allowed HTTP methods |
| `handleHttpMediaTypeNotSupported` | 415 Unsupported Media Type |
| `handleHttpMediaTypeNotAcceptable` | 406 Not Acceptable |
| `handleMissingServletRequestParameter` | Missing required query parameter |
| `handleTypeMismatch` | Input cannot be converted to expected type |
| `handleNoResourceFoundException` | Static resource not found, Spring 6.1+ |
| `handleExceptionInternal` | Common customization point for several exceptions |
| `createResponseEntity` | Final hook to build `ResponseEntity` from body/status/headers |

**Do not add `@ExceptionHandler(MethodArgumentNotValidException.class)` inside this subclass** when the base class already registers that exception via `handleException`. Two matching handlers can cause an **ambiguous exception handler mapping** at startup.

Instead, override **protected `handleMethodArgumentNotValid(...)`**. For new business errors (not among the exceptions handled by the base class), declare `@ExceptionHandler(MyDomainException.class)`.

### Override Signatures and Version Differences

In Framework 6.x, hooks use `HttpStatusCode`:

```java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    // custom handling
}
```

The type names here belong to Spring MVC and require appropriate imports. Do not copy overrides from Spring Framework 5.x with an `HttpStatus` parameter and expect them to override successfully in 6.x. Framework 7 introduces further API evolution, so when upgrading versions check the corresponding Javadoc instead of guessing signatures.

## 5. `ProblemDetail`: Standardizing Error Bodies

RFC 9457 defines the **Problem Details for HTTP APIs** structure. Spring Framework 6+ provides `org.springframework.http.ProblemDetail` with standard fields:

| JSON field | Meaning |
| --- | --- |
| `type` | URI identifying the problem type; defaults commonly to `about:blank` |
| `title` | Short summary used as a label for the error type |
| `status` | Corresponding HTTP status code |
| `detail` | Specific explanation for this error occurrence |
| `instance` | URI identifying the specific occurrence |
| Extension fields | Custom information such as `code`, `fields`, `traceId` |

Example API response with a clear schema:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Book not found",
  "status": 404,
  "detail": "Book was not found",
  "code": "BOOK_NOT_FOUND"
}
```

This is an **illustrative response**, without claiming every configuration emits these exact headers/fields. Jackson supports serializing `ProblemDetail`, and Spring unwraps extension properties from the map as top-level JSON fields.

Creating manually:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "Book was not found");
problem.setTitle("Book not found");
problem.setProperty("code", "BOOK_NOT_FOUND");
return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
```

This is a fragment inside a handler importing `ProblemDetail`, `HttpStatus`, and `ResponseEntity`. When the body is `ProblemDetail`, Spring MVC prefers the `application/problem+json` media type when a suitable converter is available; still verify negotiated responses in the actual application.

### Distinguishing `status`, `detail`, and Exception Messages

Do not return `ex.getMessage()` directly for every error:

- Exception messages can contain SQL, paths, implementation details, user input, tokens, or stack traces.
- `title` and `code` should be stable for clients to handle; `detail` should be helpful yet safe.
- Put stack traces and internal details into **structured logs/tracing**, not exposed to clients.
- Field validation errors should return **public field names** and chosen error codes, avoiding echoing sensitive passwords/`rejectedValue`.
- `ProblemDetail` does not automatically guarantee localization or security; the application needs `MessageSource` and an explicit data policy.

## 6. Runnable Spring Boot 3.2+ / Spring Framework 6.1+ Example

This lesson uses **Java 17+, Spring Boot 3.2+ with Spring MVC 6.1+**, so both kinds of validation errors are available. The example uses an in-memory map and needs no database. Spring Boot 3.x uses `jakarta.validation.*`.

### 6.1. Dependencies

In a Spring Boot Gradle project already configured with the Boot plugin, repositories, and Java toolchain, include:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is only a **`build.gradle` snippet**; when using Maven, add the corresponding starters. `starter-validation` ensures a Jakarta Bean Validation provider is present; having only the annotation API on the classpath does not guarantee validation runs.

### 6.2. Application and Controller

Create **`src/main/java/demo/errorhandling/ErrorHandlingApplication.java`**:

```java
package demo.errorhandling;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.net.URI;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ErrorHandlingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorHandlingApplication.class, args);
    }
}

record CreateBookRequest(@NotBlank String title) {}

record BookResponse(long id, String title) {}

class BookMissingException extends RuntimeException {
    BookMissingException(long id) {
        super("Book id " + id + " does not exist");
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {

    private final AtomicLong nextId = new AtomicLong(1000);
    private final ConcurrentMap<Long, BookResponse> books =
            new ConcurrentHashMap<>();

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {

        long id = nextId.incrementAndGet();
        BookResponse saved = new BookResponse(id, request.title());
        books.put(id, saved);

        return ResponseEntity
                .created(URI.create("/api/books/" + id))
                .body(saved);
    }

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    BookResponse get(@PathVariable long id) {
        BookResponse book = books.get(id);
        if (book == null) {
            throw new BookMissingException(id);
        }
        return book;
    }

    @GetMapping(path = "/page", produces = MediaType.APPLICATION_JSON_VALUE)
    java.util.Map<String, Integer> page(@RequestParam @Min(1) int number) {
        return java.util.Map.of("number", number);
    }
}
```

This is a **valid single Java file on a Boot 3 classpath**, since only `ErrorHandlingApplication` is public and the remaining types are package-private. Spring Boot component scanning from `demo.errorhandling` will discover both the controller and the advice below.

- Valid POST saves the book and returns `201 Created` with `Location: /api/books/{id}`.
- POST `{"title":""}` is rejected by `@NotBlank`, typically producing `MethodArgumentNotValidException`.
- Syntactically invalid POST JSON is rejected by the converter, typically producing `HttpMessageNotReadableException`; validation does not start if JSON cannot be converted into an object.
- GET for a non-existent book throws the business exception `BookMissingException`.
- GET `/api/books/page?number=0` violates `@Min(1)` directly on the method parameter. From Framework 6.1+, this triggers native method validation (`HandlerMethodValidationException`) when the controller does not have class-level `@Validated`.

Because the application uses an in-memory map, data is lost on restart, state is not shared across nodes, and there are no DB transactions. In production, business exceptions should arise from service/domain logic after checking repository state, authentication, and authorization.

### 6.3. Global Advice Extending `ResponseEntityExceptionHandler`

Create **`src/main/java/demo/errorhandling/ApiErrorAdvice.java`**:

```java
package demo.errorhandling;

import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    // Custom business exception: the base class does not know about it.
    @ExceptionHandler(BookMissingException.class)
    ResponseEntity<ProblemDetail> bookMissing(BookMissingException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Book was not found");
        problem.setTitle("Book not found");
        problem.setProperty("code", "BOOK_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    // Error on @Valid @RequestBody DTO: override protected hook.
    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ex.getBody();
        problem.setTitle("Invalid request");
        problem.setProperty("code", "INVALID_FIELDS");

        List<String> fields = ex.getBindingResult().getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        problem.setProperty("fields", fields);
        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    // JSON syntax or type error before the DTO is successfully bound.
    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status, "Request JSON cannot be read");
        problem.setTitle("Malformed request");
        problem.setProperty("code", "INVALID_JSON");

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    // Native method validation from Spring MVC 6.1+.
    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ex.getBody();
        problem.setProperty("code", "METHOD_VALIDATION_FAILED");

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }
}
```

Technical notes:

1. `@RestControllerAdvice` acts as global advice writing bodies directly. `ResponseEntityExceptionHandler` already has general handler methods for known MVC errors.
2. `bookMissing(...)` uses `@ExceptionHandler` **only for the custom domain exception**. This handler returns 404 and a stable code.
3. `handleMethodArgumentNotValid(...)` **overrides** the proper hook rather than re-registering the same exception via `@ExceptionHandler`; it returns the list of failing **field names** without sending back rejected values.
4. `handleHttpMessageNotReadable(...)` returns a safe fixed detail; **do not pass `ex.getMostSpecificCause().getMessage()` to the client**, as it may reveal non-public details.
5. `handleHandlerMethodValidationException(...)` **preserves the `status` determined by Spring**. This is important: input errors are usually 400, but return-value violations can be 500; forcing 400 for both would hide bugs.
6. All protected overrides delegate through `handleExceptionInternal(...)` to preserve the base class's common processing pipeline.
7. `ProblemDetail` provided by `ex.getBody()` carries status/detail from the exception. Adjusting title/extensions is intentional; do not set a new status that mismatches the HTTP response.

**Do not declare** class-level `@Validated` on `BookController` in this example. With Spring MVC 6.1+, placing it at the class level can route method validation through an AOP proxy with a different exception path than native MVC. `@Validated` still has valid roles in the service layer and on DTO parameters for validation groups.

### 6.4. Testing with curl

Run:

```bash
./gradlew bootRun
```

In another Bash terminal:

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Spring MVC"}'

curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":""}'

curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":'

curl -i 'http://localhost:8080/api/books/999999'
curl -i 'http://localhost:8080/api/books/page?number=0'
```

Expected statuses in the sample application, with no filters/security altering behavior:

| Request | Status | `code` extension in body if present |
| --- | --- | --- |
| Valid JSON POST | 201 Created | Not a ProblemDetail body; body is `BookResponse` |
| POST `title=""` | 400 Bad Request | `INVALID_FIELDS`; `fields` contains `title` |
| POST malformed JSON | 400 Bad Request | `INVALID_JSON` |
| GET non-existent ID | 404 Not Found | `BOOK_NOT_FOUND` |
| GET `number=0` | 400 Bad Request | `METHOD_VALIDATION_FAILED` |
| GET `number=2` | 200 OK | JSON `{"number":2}` |

**Do not rely on JSON field order or constraint violation order**. If Spring Security is enabled, clients may receive 401/403 before reaching MVC. If custom filters alter the body/status, adjust tests to match the actual system.

## 7. Integration Testing with `MockMvc`

In the sample project, create **`src/test/java/demo/errorhandling/ErrorHandlingApplicationTests.java`**:

```java
package demo.errorhandling;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorHandlingApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulCreationReturns201() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"Spring MVC"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Spring MVC"));
    }

    @Test
    void invalidDtoUsesOverriddenHook() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":""}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_FIELDS"))
            .andExpect(jsonPath("$.fields[0]").value("title"));
    }

    @Test
    void malformedJsonGetsSafeProblemDetail() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void domainExceptionGets404() throws Exception {
        mvc.perform(get("/api/books/999999"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value("BOOK_NOT_FOUND"))
            .andExpect(jsonPath("$.title").value("Book not found"));
    }

    @Test
    void methodValidationUsesSeparateHook() throws Exception {
        mvc.perform(get("/api/books/page").param("number", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("METHOD_VALIDATION_FAILED"));

        mvc.perform(get("/api/books/page").param("number", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.number").value(2));
    }
}
```

Run:

```bash
./gradlew test
```

With a compatible Spring Framework 6.1+/Boot 3.2+, `spring-boot-starter-validation`, and the classes above, **the five tests are designed to pass**. This is an analytical expectation from the sample code; the lesson does not claim Gradle was executed here.

This test suite verifies the **end-to-end error handling path inside MVC**. To assert the body is always `application/problem+json`, add a `contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)` assertion if that is a published API contract and your Spring version supports that media type. Do not require every error response to be JSON when a client only accepts HTML.

Other tests you should add: missing query parameter, wrong JSON type, 405/406/415, return-value method validation, and Spring Security interaction. In particular, check whether any other global advice accidentally intercepts the same exception types.

## 8. Which Class to Choose for Each Customization?

| Need | Suitable tool | Reason |
| --- | --- | --- |
| One controller needs local error handling | `@ExceptionHandler` in the controller | Simple, narrow scope |
| Entire REST API shares a common error schema | `@RestControllerAdvice` | Centralized handling |
| Customize standard MVC errors (malformed JSON, validation, unsupported method...) | Extend `ResponseEntityExceptionHandler` | Built-in hooks and default statuses/headers |
| Map business exceptions to HTTP | `@ExceptionHandler(DomainException.class)` in advice | Clear status and body |
| REST API needs RFC 9457 error formatting | `ProblemDetail`/`ErrorResponse` | Standard JSON schema |
| MVC renders HTML error pages | `SimpleMappingExceptionResolver` or `@ControllerAdvice` returning a view | Integrates with view resolution |
| Alter resolution at MVC infrastructure level | Custom `HandlerExceptionResolver` | Deep control over ordering/resolution |
| Exception thrown before `DispatcherServlet` from a filter | Appropriate filter/container/security error handling | Not part of the MVC resolver chain by default |

**Rule of thumb:** if you can solve the requirement with `@ExceptionHandler` or overriding `ResponseEntityExceptionHandler`, do not write a custom `HandlerExceptionResolver`. Writing a custom resolver requires handling response output, ordering, null/empty returns, and already-committed responses.

## 9. When to Implement `HandlerExceptionResolver` Yourself?

In systems requiring deep intervention (for example, mixed HTML/REST MVC, framework-level exception governance, or legacy resolver integration), you can create a custom resolver. The following pattern **handles only one specific exception** and returns `null` for everything else:

```java
package demo.errorhandling;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerExceptionResolver;
import org.springframework.web.servlet.ModelAndView;

@Component
class LegacyQuotaResolver
        implements HandlerExceptionResolver, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public ModelAndView resolveException(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        if (!(ex instanceof LegacyQuotaExceededException)) {
            return null; // Other resolvers can continue handling.
        }

        response.setStatus(HttpServletResponse.SC_TOO_MANY_REQUESTS);
        return new ModelAndView(); // Marks handled; empty body.
    }
}

class LegacyQuotaExceededException extends RuntimeException {}
```

This is a **structurally standalone resolver example**, but it must be integrated carefully with how Spring MVC builds the resolver chain. Simply adding `@Component` does not guarantee the desired order/registration in every Boot or custom MVC configuration; inspect the actual resolver list. The sample returns an empty body for `429 Too Many Requests` without `Retry-After` or `ProblemDetail`, so **do not treat it as a complete production endpoint**.

In many cases it is better to write:

```java
@ExceptionHandler(LegacyQuotaExceededException.class)
ResponseEntity<ProblemDetail> quotaExceeded(
        LegacyQuotaExceededException ex) {

    ProblemDetail p = ProblemDetail.forStatus(
            HttpStatus.TOO_MANY_REQUESTS);
    p.setTitle("Too many requests");
    p.setProperty("code", "QUOTA_EXCEEDED");
    return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).body(p);
}
```

This is a `@RestControllerAdvice` fragment, omitting `Retry-After` because it depends on your actual quota policy. When this error originates in MVC/controllers, the advice approach stays consistent with other exception handlers and avoids writing to the Servlet response directly.

**If you need to adjust the resolver chain**, Spring MVC provides `WebMvcConfigurer#configureHandlerExceptionResolvers(...)` and `extendHandlerExceptionResolvers(...)`. In Spring 6.x, `configureHandlerExceptionResolvers` with a list that has custom resolvers added can prevent Spring from registering the usual default chain; `extendHandlerExceptionResolvers` is suited when you only want to modify/augment the existing list. Before changing order, check the Javadoc for your Spring version and ensure `ExceptionHandlerExceptionResolver` and the default resolvers remain present.

## 10. `@ControllerAdvice` Ordering and "Handler Not Running" Cases

An application may have multiple advices:

```java
@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
class DomainAdvice {
    @ExceptionHandler(DomainException.class)
    ResponseEntity<ProblemDetail> handle(DomainException ex) {
        // ...
    }
}
```

This is an illustrative fragment requiring `@Order` and `Ordered` imports and defining `DomainException`; **it is not a runnable class while `...` remains in the method body**.

Principles:

- `@ExceptionHandler` inside a controller is considered before global advice.
- Across global advices, `@Order`, `Ordered`, or `@Priority` determines precedence. Within a single advice, Spring selects the mapping best matching root/cause.
- A high-precedence advice matching a cause can beat a low-precedence advice matching the root. Do not assume "root always wins regardless of order".
- A broad `@ExceptionHandler(Exception.class)` can swallow `ResponseStatusException`, 405/415, framework errors, or custom logic and lose the proper HTTP status.
- A class extending `ResponseEntityExceptionHandler` already provides handlers for many MVC exception types. Avoid adding a second high-precedence catch-all advice without evaluating conflicts.
- If annotation selectors like `basePackages`/`assignableTypes` restrict an advice, controllers outside that region do not receive it.
- With wrapped exceptions, Spring can examine the cause chain; test root/cause and advice ordering rather than relying solely on exception names.
- If a handler rethrows the original exception, resolution may continue through the chain; do not rethrow or return null arbitrarily once a response has been written.

A single global advice extending `ResponseEntityExceptionHandler` in the right place alongside specific domain handlers is usually easier to maintain than multiple advices with overlapping `@Order`.

## 11. Validation Errors: Why Do They Sometimes Produce Different Exceptions?

Two similar-looking APIs follow different execution paths:

```java
// Validate DTO via @Valid on argument:
@PostMapping("/users")
void create(@Valid @RequestBody UserDto body) {}

// Constraint directly on method parameter, Spring MVC 6.1+:
@GetMapping("/users/page")
void page(@RequestParam @Min(1) int number) {}
```

These are fragments inside a controller; `UserDto` needs to be defined.

- The first case typically raises **`MethodArgumentNotValidException`** when the DTO object is invalid and no `BindingResult` immediately follows the parameter.
- The second case triggers **native method validation** and can raise **`HandlerMethodValidationException`**.
- When there is a constraint directly on a method parameter (e.g., `@NotNull` on a method parameter), Spring MVC 6.1+ can apply method validation covering nested constraints as well; DTO errors in that call may then go through method validation.
- If `@Validated` is placed at the **class level** of a controller, method validation may be performed by a Spring AOP proxy, with a different exception/call path. To use native method validation, Spring recommends omitting class-level `@Validated` on controllers where appropriate.
- In Spring Framework 6.0 and earlier, MVC 6.1's native method validation **does not exist**; corresponding AOP configuration/behavior is needed to validate method parameters directly.
- `BindingResult` must immediately follow the validated argument. With method validation, the controller can run only if all relevant errors are handled on parameters with appropriate `Errors`/`BindingResult`; violations on other parameters still throw an exception.

**Do not hardcode "every validation exception is 400"**. For instance, a return-value constraint violation indicates server code broke its own contract and can be handled by Spring 6.1+ as 500. Use the status provided by `HandlerMethodValidationException` and log 5xx cases.

## 12. `ResponseStatusException` and `ErrorResponseException`

When a controller/service wants to signal an HTTP error intentionally without creating a custom domain exception, Spring provides `ResponseStatusException`:

```java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND, "Book was not found");
```

Spring 6+ includes several `ErrorResponse`-style exceptions that can provide `ProblemDetail` and status. For example, `ResponseStatusException` is normally handled by a matching resolver; when `ResponseEntityExceptionHandler` is in an advice, its base handlers can catch it first.

Pros: easy to use for simple errors. Tradeoff: services/domains can become coupled to HTTP semantics if thrown deep inside the business layer. For larger domains, it is usually better to define an independent `BookMissingException` and map it in the web layer with `@ExceptionHandler`.

`ErrorResponseException` in Spring 6+ provides a mechanism to represent exceptions with `ErrorResponse`/`ProblemDetail`. Do not treat it as a mandatory base class for every business exception; choose based on your architecture and error contract.

## 13. HTTP Headers Must Be Preserved When Customizing Errors

Some exceptions carry more than a status code. For example:

- **405 Method Not Allowed**: the **`Allow`** header can list permitted HTTP methods.
- **415 Unsupported Media Type**: the response may carry supported media type info per MVC logic.
- **429 Too Many Requests**: when rate limiting applies, `Retry-After` is helpful per actual policy.
- **401 Unauthorized**: **`WWW-Authenticate`** challenges must be preserved when required by the authentication scheme.
- **413 Content Too Large** or container/network errors: can happen before the controller, requiring inspection of the layer producing the response.

When overriding `handleHttpRequestMethodNotSupported`, `handleHttpMediaTypeNotSupported`, or similar hooks, Spring passes `HttpHeaders headers` along with the chosen `status`. **Do not accidentally drop standard headers** by building a new response that ignores `headers`. Use `handleExceptionInternal(ex, body, headers, status, request)` or construct a `ResponseEntity` including the appropriate headers.

If the response is already committed (flushed or partially streamed), Spring cannot reliably convert it into a new `ProblemDetail`. Exceptions during streaming/file downloads, SSE, or async responses need dedicated strategies.

## 14. Spring Boot `/error` and MVC Resolvers Are Two Different Layers

A Spring Boot Servlet app typically has a fallback `/error` endpoint with `BasicErrorController`/`ErrorAttributes` depending on auto-configuration. It serves error handling via **Servlet container error dispatch** and cases not resolved by an MVC resolver/advice response.

Example path:

```text
Controller throws exception
   |
DispatcherServlet HandlerExceptionResolvers
   |
   +-- Advice builds ResponseEntity<ProblemDetail> successfully
   |      -> returns JSON directly, no BasicErrorController needed
   |
   +-- Unhandled exception or sendError / container error dispatch
          -> may go to Spring Boot /error
          -> BasicErrorController / ErrorAttributes / custom error page
```

Consequently, `server.error.*` properties in Spring Boot affect the `/error` fallback, but **do not assume they transform bodies already returned by a custom `@ExceptionHandler`**. Similarly, configuring `spring.mvc.problemdetails.enabled` in some Boot 3 versions enables built-in ProblemDetail error handling, while an advice returning `ProblemDetail` itself still defines its own contract. Verify properties and defaults for your exact Boot version.

If your application has both paths, test them to ensure a **consistent schema** across controllers, missing handlers/static resources, filters/security, and container errors. However, do not try to force every container error or streaming failure into a JSON body once the response has started sending.

## 15. Combining with Spring Security and the Filter Chain

MVC `HandlerExceptionResolver` **is not a complete replacement for Spring Security**.

- Spring Security filters handle many authentication/authorization errors before a request reaches `DispatcherServlet`; `AuthenticationEntryPoint` and `AccessDeniedHandler` are responsible for producing 401/403 respectively.
- If an exception is thrown from a custom Servlet filter before MVC, global `@RestControllerAdvice` **will not catch it automatically**.
- You can intentionally integrate a filter with an injected `HandlerExceptionResolver` bean to delegate exceptions, but you must be careful with request/response lifecycle, ordering, double-writes, and security semantics. This is an explicit infrastructure decision, not default behavior.
- Expose only safe public error codes and correlation IDs in responses; details about tokens, permissions, SQL, or stack traces belong in internal logs.
- If a reverse proxy/gateway also transforms status/body, run end-to-end tests to spot errors emitted by external layers.

For example, a client without permission to GET a resource may receive 403 directly from Security, even though the controller—if invoked—would throw a 404 `BookMissingException`. To pinpoint responsibility, inspect the HTTP status, filter chain, and logs with the correlation ID.

## 16. Version Compatibility and Migration

| Common Spring Framework / Boot | Handling notes |
| --- | --- |
| Framework 5.x / Boot 2.x | Has `HandlerExceptionResolver` and `ResponseEntityExceptionHandler`; custom signatures often use `HttpStatus` instead of `HttpStatusCode`; Jakarta namespace in many APIs is still `javax.*`; no built-in `ProblemDetail` as in Spring 6. |
| Framework 6.0 / Boot 3.0–3.1 | Java 17+, Jakarta namespace, `ProblemDetail` and `ErrorResponse` added; `ResponseEntityExceptionHandler` handles errors under the new mechanism. |
| Framework 6.1+ / Boot 3.2+ | Native MVC method validation and `HandlerMethodValidationException`; additions like `NoResourceFoundException` for static resources. |
| Framework 6.2 / Boot 3.4–3.5 | `ResponseEntityExceptionHandler` supports RFC 9457 error formatting and the protected hooks needed for the examples. |
| Framework 7.x / Boot 4.x | `HandlerExceptionResolver` infrastructure and base advice continue to exist; re-check signatures, error formatting, and Jackson 3/Boot module changes when migrating existing code. |

To run the example, use **Boot 3.4 or 3.5** so Spring Framework 6.2 matches the protected overrides shown, with Java 17+. If an application overrides the BOM, the actual `spring-webmvc` version determines the API to use.

Do not assume copying an advice from Boot 2 to Boot 3 will compile: `javax.servlet` changed to `jakarta.servlet`, `HttpStatus` parameters in many hooks became `HttpStatusCode`, and the set of supported framework exceptions evolved.

## 17. Diagnosing When API Errors Have the Wrong Format

### Case 1: Controller throws an exception, yet advice does not run

Check:

1. Was the exception actually thrown **inside `DispatcherServlet`**? If it happened in security/filters or another servlet, MVC advice does not participate by default.
2. Is `@RestControllerAdvice` component-scanned? Is the advice's package under the `@SpringBootApplication` root or explicitly imported?
3. Did a local `@ExceptionHandler` or another global advice catch the error first?
4. Was a high-precedence `HandlerExceptionResolver` registered that returned non-null too early?
5. Was the response already committed or using unusual async/streaming handling?

### Case 2: Status is 400, yet the body is `/error` JSON or HTML

Check whether the exception was handled directly by a resolver, an error dispatch reached the container, and how content negotiation behaved for `Accept`. Inspect `Content-Type` headers, `ProblemDetail` content, and logs. In Boot, default `/error` configuration can emit a different JSON structure than your advice. Do not rely only on the status code.

### Case 3: Adding a validation handler causes an ambiguous mapping error

If you `extends ResponseEntityExceptionHandler` and also declare `@ExceptionHandler(MethodArgumentNotValidException.class)` or `@ExceptionHandler(HttpMessageNotReadableException.class)` on the same advice, it can collide with the base class handler. **Override the proper protected hook**, remove the duplicate handler, and write an integration test verifying the context starts.

### Case 4: Everything turns into 500

Audit for a catch-all `@ExceptionHandler(Exception.class)` or custom resolver forcing status 500 and discarding `ErrorResponse` info. Preserve `HttpStatusCode` from known framework exceptions, and map business errors by specific type. Reserve 500 for genuine server-side failures.

### Case 5: An error occurs, yet the client receives 200

A resolver may have written a body while forgetting to set the status; an `@ExceptionHandler` returning a regular object without `@ResponseStatus`/`ResponseEntity.status(...)` will not switch to the intended error code automatically. Check where the status is set in the exception handling layer.

### Case 6: Content negotiation breaks when returning ProblemDetail

If a client sends `Accept` exclusively for an unsupported media type, Spring may fail to serialize the `ProblemDetail` body as intended. Check actual converters (Jackson 2 in Boot 3, Jackson 3 in Boot 4), `Accept`, and mixed HTML/JSON endpoints. Do not try to write JSON into an already-committed response.

## 18. Production Deployment Checklist

- [ ] Have a clear mapping table **domain errors → HTTP status → public error code**, without leaking technical exception names.
- [ ] Have a centralized handling path for common Spring MVC errors using `ResponseEntityExceptionHandler` or an equivalent mechanism.
- [ ] Overrides preserve `status`, `headers`, content negotiation, and proper 5xx behavior.
- [ ] Have specific `@ExceptionHandler` methods for domain errors; avoid catch-alls swallowing framework errors.
- [ ] `ProblemDetail`/JSON schema has title, detail, code, and traceId at safe levels, with versioning when contracts change.
- [ ] Error bodies never contain tokens, passwords, SQL, internal paths, or stack traces.
- [ ] Validation handlers match the Framework version, distinguishing `MethodArgumentNotValidException` and `HandlerMethodValidationException`.
- [ ] Filter/Security/container error paths are evaluated separately; 401/403 errors are not accidentally replaced by MVC advice.
- [ ] Integration tests exist for 400, 404, 405, 415, 500, and realistic content negotiation.
- [ ] Correlation IDs and separate structured logging are in place for operations; expected 4xx errors do not flood logs with full stack traces.
- [ ] Unhandled errors are still logged and monitored; never mask everything as `200 OK`.
- [ ] After Spring/Boot upgrades, review protected override signatures and resolver ordering.

## 19. Self-Check Exercises

1. Explain the difference between `HandlerExceptionResolver` and `ResponseEntityExceptionHandler`. Which class is called directly by `DispatcherServlet`, and which is invoked indirectly by `ExceptionHandlerExceptionResolver`?
2. When a custom resolver encounters an unknown exception, should it return `null` or `new ModelAndView()`? Explain the effect on subsequent resolvers.
3. When `@Valid @RequestBody` fails and you extend `ResponseEntityExceptionHandler`, why should you override `handleMethodArgumentNotValid` instead of adding `@ExceptionHandler(MethodArgumentNotValidException.class)`?
4. In Spring Framework 6.1+, why can `@RequestParam @Min(1) int page` go through `HandlerMethodValidationException`, while `@Valid @RequestBody UserDto` typically goes through `MethodArgumentNotValidException`?
5. Build a `@RestControllerAdvice` mapping `OrderMissingException` to 404 and `OrderConflictException` to 409 using `ProblemDetail` with stable `code`s.
6. If a 405 exception handler drops the `Allow` header, what can be impacted? Preserve the `headers` Spring passes to the protected hook.
7. A custom filter throws an error before `DispatcherServlet`, and global `@RestControllerAdvice` does not run. What is the right layer to handle it and why?
8. An application has two advices: a high-precedence advice catches cause `IOException`, and a low-precedence advice catches root `IllegalStateException`. Which advice can win? Explain in terms of ordering and matching.
9. Write a test proving validation `ProblemDetail` does not contain the rejected password while including a public error code and field name.
10. Upgrading Boot 2 to Boot 3: which imports/signatures must change when overriding `handleMethodArgumentNotValid`, and why can't the old mechanism be copied unchanged?

## 20. Official References

- [Spring Framework — Servlet MVC Exception Resolvers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html): `HandlerExceptionResolver`, the resolver chain, and `ModelAndView` semantics.
- [Spring Framework — `@ExceptionHandler`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): exception mappings, root/cause, and return values.
- [Spring Framework — `@ControllerAdvice`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html): global scope and precedence.
- [Spring Framework — REST Exceptions and Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`/`ErrorResponse` and `ResponseEntityExceptionHandler`.
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): protected overrides and signatures.
- [Spring Framework 6.2 — HandlerExceptionResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/HandlerExceptionResolver.html): resolver contract.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): distinguishing `MethodArgumentNotValidException` and `HandlerMethodValidationException`.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): semantics and standard members of a problem response.
- [Spring Boot — Error Handling](https://docs.spring.io/spring-boot/reference/web/servlet.html): `/error`, `BasicErrorController`, and error fallback.
