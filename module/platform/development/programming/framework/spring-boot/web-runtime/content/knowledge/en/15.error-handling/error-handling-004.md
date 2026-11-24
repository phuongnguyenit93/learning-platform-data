# @ExceptionHandler, @ControllerAdvice, and @RestControllerAdvice in Spring Boot

> **Scope:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**, **Spring MVC (Servlet)** HTTP applications. This topic covers how to catch and translate exceptions into controlled HTTP responses: local controller handling with `@ExceptionHandler`, shared handling via `@ControllerAdvice` / `@RestControllerAdvice`, precedence order, framework errors, RFC 9457 `ProblemDetail`, testing, and common pitfalls. The final section compares with WebFlux. The complete example uses Maven and Spring Boot **3.5.0**; adjust the version for real deployments.

## 1. Why Do We Need an HTTP Error-Handling Strategy?

Controllers can encounter many kinds of errors:

- A user requests a non-existent book → **404 Not Found**.
- Invalid ID or invalid request body → **400 Bad Request**.
- Unsupported HTTP method → usually **405 Method Not Allowed**.
- Incompatible `Content-Type` or `Accept` → possibly **415** or **406**.
- Business state conflict → possibly **409 Conflict**.
- Unexpected infrastructure failure → **500 Internal Server Error**, without leaking internal details.

Avoid writing large `try/catch` blocks inside every endpoint just to assemble an error JSON string. Instead, let services throw meaningful exceptions and use exception handlers to convert exceptions into **consistent** HTTP statuses, headers, and bodies.

Typical model:

~~~text
HTTP request
     |
     v
Servlet filter chain (possibly including Spring Security)
     |
     v
DispatcherServlet
     |
     +-- HandlerMapping -> Controller -> Service
     |                           |
     |                           +-- returns success result
     |                           |
     |                           +-- throws exception
     |
     +-- HandlerExceptionResolver chain
              |
              +-- local @ExceptionHandler?
              +-- @ExceptionHandler in @ControllerAdvice?
              +-- @ResponseStatus / ResponseStatusException?
              +-- Spring MVC default resolver?
              |
              v
        HTTP status + headers + error body/view
~~~

Conceptual diagram: `@ExceptionHandler` is resolved through `ExceptionHandlerExceptionResolver`; each resolver has its own order and conditions. If left unhandled, errors may reach the Servlet container's error dispatch mechanism and Spring Boot `/error`.

Key point: **exceptions are Java events; HTTP statuses are contracts with clients**. Spring does not automatically know which HTTP code matches every custom exception. Applications must map intentionally while never accidentally turning programming bugs into 200 responses.

## 2. How Do the Three Annotations Differ?

| Component | Where Placed | Scope | Used For |
|---|---|---|---|
| `@ExceptionHandler` | On a method in `@Controller` or an advice | Handles matching exception types | Producing HTTP response/view when an exception occurs |
| `@ControllerAdvice` | On a Spring bean class | Shared across multiple controllers, optionally scoped | `@ExceptionHandler`, `@InitBinder`, `@ModelAttribute` |
| `@RestControllerAdvice` | On a Spring bean class | Same as `@ControllerAdvice`, with response-body semantics | Global JSON/REST exception handling |

**`@RestControllerAdvice` = `@ControllerAdvice` + `@ResponseBody`** via meta-annotation. It does not give `@ExceptionHandler` higher precedence than `@ControllerAdvice`; the primary difference is that return values are serialized as the HTTP response body by default instead of being treated by Spring MVC as a view name.

Quick comparison example:

~~~java
// Fragment inside a REST controller:
@ExceptionHandler(BookNotFoundException.class)
public ResponseEntity<String> notFound(
        BookNotFoundException exception) {
    return ResponseEntity.status(404).body("Book not found");
}
~~~

Placed inside a controller, this handler only serves that controller (and related inheritance). Placed inside an advice, it can serve multiple controllers.

### 2.1. How Does @ExceptionHandler Determine the Exception?

Spring can infer the exception type from the method parameter:

~~~java
@ExceptionHandler(BookNotFoundException.class)
public ResponseEntity<String> handle(
        BookNotFoundException exception) {
    return ResponseEntity.status(404).body("Not found");
}
~~~

You can declare one or multiple exception classes in the annotation, though for clarity use **one handler per primary business error type**, especially when errors carry different HTTP statuses.

Valid MVC handler parameters include the matching exception, `HttpServletRequest`, `HttpServletResponse`, `WebRequest`, `Locale`, and certain other MVC types. Usable parameters depend on the dispatch mechanism. Return types are commonly `ResponseEntity<?>`, `ProblemDetail`, an error DTO, `ModelAndView`, or an intentional view name.

**Do not write an `@ExceptionHandler(Exception.class)` that always returns 400:** many serious system errors must return 500 and be logged for operations.

### 2.2. Which Controllers Does @ControllerAdvice Apply To?

By default, an advice can apply broadly across controllers in the Spring context. If you need to restrict it, selectors can include:

~~~java
@RestControllerAdvice(
    basePackageClasses = BookController.class
)
class BookAreaAdvice {
    // Handlers for controllers matching the selector.
}
~~~

This is only an **illustrative fragment**; do not place it beside `ApiExceptionAdvice` from the sample project if both register handlers for the same exception without a clear strategy. `basePackageClasses` is safer for refactoring than String package names; other options include `basePackages`, `annotations`, and `assignableTypes`.

Selectors help organize API groups, though they are not a security mechanism or complete exception isolation boundary. Whenever adding a new advice, verify its effective scope and ordering.

### 2.3. @RestControllerAdvice Does Not Catch Every System-Wide Error Automatically

This annotation does not mean “catch every exception everywhere”. Exceptions from a Servlet `Filter` before entering `DispatcherServlet`, scheduled tasks, or async code running after a response is committed may require different mechanisms. Spring Security uses `AuthenticationEntryPoint` and `AccessDeniedHandler` to generate 401/403 responses. MVC advice generally serves exceptions traveling through MVC's exception-handling system.

## 3. Precedence Order: Local Before Global

When a controller defines its own handler for an exception, the **local** handler is considered before a global `@ControllerAdvice`. This is useful when one API has custom error rules while common errors flow through shared advice.

Example with the same exception type:

~~~java
@RestController
class ExampleController {

    @GetMapping("/example")
    public String example() {
        throw new IllegalArgumentException("Invalid input");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> local(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body("Handled by this controller");
    }
}
~~~

If a global advice also handles `IllegalArgumentException`, the handler in `ExampleController` takes precedence for exceptions thrown by that controller itself.

**Do not place overly broad local handlers.** For instance, `@ExceptionHandler(Exception.class)` inside a controller can intercept errors that global advice would handle better.

### 3.1. Multiple Advices: @Order and Ordered

Advices are sorted according to `Ordered` / `@Order`. Typically **smaller values have higher priority**, for example:

~~~java
@RestControllerAdvice
@Order(0)
class PrimaryAdvice {
    // Important, specific handlers.
}
~~~

~~~java
@RestControllerAdvice
@Order(100)
class FallbackAdvice {
    // Fallback handlers.
}
~~~

These are **two class fragments** illustrating order, not part of the runnable project. Advice beans also have caveats regarding `Ordered`, `PriorityOrdered`, bean scopes, and differing selectors. `@Order` should not be used to paper over multiple advices competing for the same exception; when possible, cleanly separate scopes or exception types.

**Nuance on exception causes:** Within the *same advice*, a handler matching the root exception is generally preferred over one matching the cause exception. However, between **two advices with different priorities**, a handler matching only the cause in a higher-priority advice can be chosen **before** a handler matching the root in a lower-priority advice. Declare primary root mappings in appropriately prioritized advices and write tests for wrapper exceptions.

### 3.2. Do Not Register Ambiguous Handlers

Two handler methods matching the same exception within **a single advice/controller** can cause ambiguity when Spring builds the exception resolver mapping.

Example to **avoid**:

~~~java
// Inside the same class, two handlers target the same error:
@ExceptionHandler(IllegalArgumentException.class)
public String a(IllegalArgumentException ex) { return "a"; }

@ExceptionHandler(IllegalArgumentException.class)
public String b(IllegalArgumentException ex) { return "b"; }
~~~

This snippet illustrates an error and should not be placed in a runnable project. Choose one clear handler, or use dedicated exception subclasses.

## 4. How Does Spring MVC Use HandlerExceptionResolver?

Common components:

| Resolver | Responsibility |
|---|---|
| `ExceptionHandlerExceptionResolver` | Finds and invokes local/advice `@ExceptionHandler` methods |
| `ResponseStatusExceptionResolver` | Handles `@ResponseStatus`, `ResponseStatusException`, and related mappings |
| `DefaultHandlerExceptionResolver` | Translates many standard Spring MVC exceptions into suitable HTTP statuses |
| `SimpleMappingExceptionResolver` | Uses exception-to-view mappings in HTML-rendering MVC apps when configured |

These belong to `DispatcherServlet`'s `HandlerExceptionResolver` chain. One resolver may handle the exception and produce a response; if it cannot, subsequent resolvers are tried depending on configuration.

Spring Boot also provides MVC error mechanisms such as `BasicErrorController`, `ErrorAttributes`, and error pages. Those are **not** an automatic `@RestControllerAdvice` with the same scope. Results can depend on `Accept`, error-handling configuration, and which step handled the exception.

### 4.1. @ResponseStatus and ResponseStatusException

Aside from advice, you can declare:

~~~java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class ProductNotFoundException extends RuntimeException {
}
~~~

This class snippet is an **illustrative fragment** needing imports; it is not in the sample project. The annotation binds the exception to a common HTTP status.

Inside a handler:

~~~java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND, "Resource not found");
~~~

`ResponseStatusException` suits a simple error at a single spot. Across multiple APIs needing a consistent error contract, logging, i18n, and validation fields, shared advice is easier to control.

A matching `@ExceptionHandler` can handle the exception before the resolver dedicated to reading `@ResponseStatus`. Therefore, when mixing `@ResponseStatus` on exceptions with global advice, test the final response rather than assuming the two configurations are independent.

## 5. Using RFC 9457 ProblemDetail for REST APIs

Spring Framework 6.2 supports `org.springframework.http.ProblemDetail` per **RFC 9457** (Problem Details for HTTP APIs). A common error response:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
~~~

Illustrative body:

~~~json
{
  "type": "about:blank",
  "title": "Book not found",
  "status": 404,
  "detail": "No book with id 7",
  "instance": "/api/books/7"
}
~~~

Main fields:

- `type`: identifies the problem type; `about:blank` is the default when no dedicated error-type URI is provided.
- `title`: short, stable error name.
- `status`: HTTP code declared in the problem detail; must stay consistent with the actual HTTP status.
- `detail`: safe explanation for clients, not a raw stack trace.
- `instance`: URI referencing the specific request/error occurrence; the framework may fill in the path if unset.

`ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, "No book with id 7")` creates the error object, on which you can call `setTitle`, `setType`, `setInstance`, or `setProperty`. `ResponseEntity<ProblemDetail>` allows explicitly setting status and headers.

Example:

~~~java
ProblemDetail body = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "Book is missing");

body.setTitle("Book not found");
body.setProperty("errorCode", "BOOK_NOT_FOUND");

return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
~~~

This is a **method body fragment**, not a standalone Java file. With MVC's Jackson converter, custom properties from `ProblemDetail#setProperty` appear as top-level JSON fields; do not use `errorCode` alone as an authorization mechanism.

**Do not mechanically put `exception.getMessage()` into public `detail`.** Messages from SQL, the filesystem, secret-bearing dependencies, or frameworks can leak internal data. Craft client-safe messages intentionally and log internal causes on the server with a correlation ID.

### 5.1. When to Use a Custom Error DTO?

If an API contract already uses a stable error DTO, such as `ApiError(code, message, traceId)`, you can return `ResponseEntity<ApiError>`. Not every application is required to use `ProblemDetail`. However, if you adopt RFC 9457, keep status, media type, and structure consistent across endpoints.

Avoid having one API return an HTML error page, another return custom JSON, and a third return an empty body for no reason. Clients need to know reliably when to parse `application/problem+json`, and the backend must avoid leaking stack traces.

## 6. ResponseEntityExceptionHandler Helps Handle Framework Errors

Spring MVC has many exceptions thrown by the framework itself rather than business services:

| Exception | Common Scenario | Typical HTTP Status |
|---|---|---|
| `MethodArgumentNotValidException` | `@Valid @RequestBody` fails validation | 400 |
| `HandlerMethodValidationException` | Controller method parameter validation | Usually 400 for input; output validation can be 500 |
| `HttpMessageNotReadableException` | Malformed or unparseable JSON body | 400 |
| `MissingServletRequestParameterException` | Missing required parameter | 400 |
| `MethodArgumentTypeMismatchException` | Path/query value cannot convert to target type | 400 |
| `HttpRequestMethodNotSupportedException` | Unsupported HTTP method | 405 |
| `HttpMediaTypeNotSupportedException` | Incompatible `Content-Type` | 415 |
| `HttpMediaTypeNotAcceptableException` | Cannot satisfy `Accept` | 406 |
| `NoResourceFoundException` | Static resource not found in mapping | 404 |
| `NoHandlerFoundException` | No matching handler in configurations that raise this exception | 404 |
| `MaxUploadSizeExceededException` | Multipart upload exceeds limit | Usually 413 when mapped appropriately |

Do not write custom `@ExceptionHandler` methods for **all** framework exceptions when `ResponseEntityExceptionHandler` already handles them. You can extend this class in `@ControllerAdvice` / `@RestControllerAdvice` and override just the hooks you want to customize.

Note: `ResponseEntityExceptionHandler` already declares `@ExceptionHandler` methods covering many standard exceptions and delegates to protected methods like `handleMethodArgumentNotValid` or `handleHttpMessageNotReadable`. If a subclass declares **another `@ExceptionHandler` method for the same framework exception**, it can cause an ambiguous exception mapping. Always **override the protected method** instead of declaring a competing handler.

Correct Spring Framework 6.2 signature example:

~~~java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {

    ProblemDetail body = ProblemDetail.forStatus(status);
    body.setTitle("Validation failed");
    return handleExceptionInternal(
            ex, body, headers, status, request);
}
~~~

This is a **method fragment** inside a class extending `ResponseEntityExceptionHandler`, not a standalone file; imports appear in the complete project below. Do not add `@ExceptionHandler(MethodArgumentNotValidException.class)` to the overridden method.

## 7. Complete Spring Boot Project: Local Handler, Global Advice, and Bean Validation

We will build **one REST app** with well-defined behaviors:

| Request | Purpose | Expected Result |
|---|---|---|
| `GET /api/books/42` | Book exists | 200 + BookView JSON |
| `GET /api/books/7` | Does not exist | 404 + ProblemDetail from global advice |
| `GET /api/books/0` | Invalid ID | 400 + ProblemDetail from **local @ExceptionHandler** |
| `POST /api/books` with valid title | Simulated book creation | 201 + BookView JSON |
| `POST /api/books` with blank title | `@NotBlank` fails | 400 + ProblemDetail with `invalidFields` |
| `POST /api/books` with malformed JSON | Parsing fails | 400 via framework exception handling |

The example has no database; id `42` is treated as existing so results are predictable. Creation simply returns a DTO without persisting.

### 7.1. Directory Structure

~~~text
spring-mvc-exceptions/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/errors/
    ErrorHandlingApplication.java
    BookNotFoundException.java
    BookController.java
    ApiExceptionAdvice.java
  src/test/java/com/example/errors/
    BookErrorHandlingTest.java
~~~

### 7.2. pom.xml — Needs starter-validation

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-mvc-exceptions</artifactId>
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
~~~

`spring-boot-starter-validation` is added explicitly so `@Valid` with `@NotBlank` executes as expected. In modern Boot starters, **do not assume** the Web starter includes a Bean Validation provider.

`src/main/resources/application.properties`:

~~~properties
server.port=8080

# Do not automatically expose exception messages/stack traces in Boot's error body:
server.error.include-message=never
server.error.include-stacktrace=never
~~~

These properties belong to **Boot error handling fallback**; they do not alter content you construct manually inside `@ExceptionHandler`. If a handler copies stack traces into `ProblemDetail`, these properties cannot protect you.

### 7.3. Application Entry Point

`src/main/java/com/example/errors/ErrorHandlingApplication.java`:

~~~java
package com.example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorHandlingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorHandlingApplication.class, args);
    }
}
~~~

### 7.4. Custom Business Exception

`src/main/java/com/example/errors/BookNotFoundException.java`:

~~~java
package com.example.errors;

public class BookNotFoundException extends RuntimeException {

    private final long bookId;

    public BookNotFoundException(long bookId) {
        super("Book does not exist: " + bookId);
        this.bookId = bookId;
    }

    public long getBookId() {
        return bookId;
    }
}
~~~

Throwing `BookNotFoundException` by itself does not make Spring return 404. The demo's 404 status comes from the **global @ExceptionHandler** in Section 7.6. The exception message can be used for internal logging; the public response builds a separate `detail` according to the API contract.

### 7.5. Controller with Local @ExceptionHandler

`src/main/java/com/example/errors/BookController.java`:

~~~java
package com.example.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping("/{id}")
    public BookView find(@PathVariable long id) {
        if (id <= 0) {
            throw new IllegalArgumentException(
                    "Book id must be positive");
        }

        if (id != 42) {
            throw new BookNotFoundException(id);
        }

        return new BookView(42, "Spring MVC");
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public BookView create(
            @Valid @RequestBody CreateBookRequest request) {
        return new BookView(100, request.title());
    }

    // Local handler: applies to BookController.
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> invalidId(
            IllegalArgumentException ex) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Book id must be a positive integer");
        body.setTitle("Invalid book id");

        return ResponseEntity.badRequest().body(body);
    }

    public record BookView(long id, String title) {
    }

    public record CreateBookRequest(
            @NotBlank String title) {
    }
}
~~~

Points to understand:

- `GET /api/books/42` returns `BookView` JSON.
- `GET /api/books/7` throws `BookNotFoundException`; there is no local handler for it, so global advice handles it.
- `GET /api/books/0` throws `IllegalArgumentException`; `invalidId` inside the controller handles it as HTTP 400.
- `POST /api/books` uses `@Valid` + `@NotBlank`; a title of `""` or whitespace fails validation.
- `@ResponseStatus(HttpStatus.CREATED)` is placed on the success method, not on an exception handler.
- Java 17 records serve as DTOs; Spring Boot's Jackson converter reads/writes JSON.
- The project uses hardcoded values for easy testing, without real database failures.

### 7.6. Global @RestControllerAdvice Extending ResponseEntityExceptionHandler

`src/main/java/com/example/errors/ApiExceptionAdvice.java`:

~~~java
package com.example.errors;

import java.util.List;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiExceptionAdvice
        extends ResponseEntityExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<ProblemDetail> bookNotFound(
            BookNotFoundException ex) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "No book with id " + ex.getBookId());
        body.setTitle("Book not found");
        body.setProperty("errorCode", "BOOK_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(body);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<String> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> error.getField())
                .distinct()
                .sorted()
                .toList();

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request body failed Bean Validation");
        body.setTitle("Validation failed");
        body.setProperty("invalidFields", fields);

        return handleExceptionInternal(
                ex, body, headers, status, request);
    }
}
~~~

**Why this class works:**

1. `@RestControllerAdvice` registers an advice bean in the component-scanned package.
2. `@ExceptionHandler(BookNotFoundException.class)` turns the business error into HTTP 404 with `ProblemDetail`.
3. `ResponseEntityExceptionHandler` is used by Spring Framework to handle many MVC errors such as invalid request bodies, unsupported methods, and malformed JSON.
4. `handleMethodArgumentNotValid` overrides the exact hook for failed `@Valid @RequestBody`, adding `invalidFields` to ProblemDetail.
5. `@ExceptionHandler(MethodArgumentNotValidException.class)` is not added to the override, avoiding duplicate mapping with the inherited method.
6. `@Order(Ordered.HIGHEST_PRECEDENCE)` declares priority over any other global advices; **`BookController`'s local handler still takes precedence** during MVC exception resolution.
7. `handleExceptionInternal` preserves headers and the HTTP status determined by the framework, which is cleaner than building raw responses manually for every error.
8. `invalidFields` contains only field names, without echoing user-submitted values or internal validation objects into public details.

Do not add a generic `@ExceptionHandler(Exception.class)` to this class just to “make sure every error becomes JSON 400”. If you need a 500 fallback, log the internal error, return safe content, and ensure it does not interfere with Spring Security or filter-layer handling.

## 8. Running the Application and Observing HTTP Responses

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Or package it:

~~~bash
mvn clean package
java -jar target/spring-mvc-exceptions-1.0.0.jar
~~~

The examples below assume the app runs at `http://localhost:8080`.

### 8.1. Successful GET

~~~bash
curl -i http://localhost:8080/api/books/42
~~~

HTTP status `200` and JSON body:

~~~json
{"id":42,"title":"Spring MVC"}
~~~

### 8.2. Business Error: Global Advice Returns 404

~~~bash
curl -i http://localhost:8080/api/books/7
~~~

HTTP status `404` and body fields:

~~~json
{
  "type": "about:blank",
  "title": "Book not found",
  "status": 404,
  "detail": "No book with id 7",
  "instance": "/api/books/7",
  "errorCode": "BOOK_NOT_FOUND"
}
~~~

Spring Framework may populate `instance` with the request path. Key order, spacing, and some headers are decided by the converter; this is **expected JSON structure**, not a guarantee of exact raw bytes.

### 8.3. Input Error: Local @ExceptionHandler Returns 400

~~~bash
curl -i http://localhost:8080/api/books/0
~~~

Body contains `title="Invalid book id"`, `detail="Book id must be a positive integer"`, and `status=400`. This comes from the controller's local handler, not the global `BookNotFoundException` handler.

### 8.4. Valid POST

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Exception Handling"}'
~~~

Returns HTTP `201 Created` and:

~~~json
{"id":100,"title":"Exception Handling"}
~~~

### 8.5. Invalid POST

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":""}'
~~~

Returns HTTP `400 Bad Request`. The ProblemDetail body contains:

~~~json
{
  "type": "about:blank",
  "title": "Validation failed",
  "status": 400,
  "detail": "Request body failed Bean Validation",
  "invalidFields": ["title"]
}
~~~

The framework may add `instance`; the example above focuses on application-controlled fields.

### 8.6. Malformed JSON

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":'
~~~

Because the JSON cannot be parsed, Spring MVC raises `HttpMessageNotReadableException`. `ResponseEntityExceptionHandler` already supports this framework error, returning HTTP **400**. Do not expect an identical body to the custom validation error because this is a **parse error**, not `@NotBlank`.

**Shell note:** multi-line `curl` examples use Bash syntax. In PowerShell, use `curl.exe` with appropriate quoting or combine into a single line. You will not necessarily see the exact same status/body when a project adds Spring Security, filters, custom content negotiation, or a proxy.

## 9. Automated Testing: Verifying Local, Global, and Framework Exceptions

Create `src/test/java/com/example/errors/BookErrorHandlingTest.java`:

~~~java
package com.example.errors;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BookErrorHandlingTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void existingBookReturns200() throws Exception {
        mvc.perform(get("/api/books/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title").value("Spring MVC"));
    }

    @Test
    void localExceptionHandlerReturns400() throws Exception {
        mvc.perform(get("/api/books/0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.title")
                    .value("Invalid book id"))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.detail")
                    .value("Book id must be a positive integer"));
    }

    @Test
    void globalAdviceReturns404() throws Exception {
        mvc.perform(get("/api/books/7"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.title")
                    .value("Book not found"))
            .andExpect(jsonPath("$.errorCode")
                    .value("BOOK_NOT_FOUND"))
            .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void beanValidationReturns400AndInvalidFields()
            throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.title")
                    .value("Validation failed"))
            .andExpect(jsonPath("$.invalidFields[0]")
                    .value("title"));
    }

    @Test
    void validPostReturns201() throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"New book\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(100))
            .andExpect(jsonPath("$.title").value("New book"));
    }

    @Test
    void malformedJsonIsRejectedAs400() throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The test suite verifies:

- Normal MVC returns HTTP 200 and the DTO.
- The local handler inside the controller returns 400 with the designed title/detail.
- Global advice catches the 404 business exception and returns `application/problem+json`.
- `@Valid`/`@NotBlank` throws the framework exception, overridden by the advice to return a body with `invalidFields`.
- Malformed JSON is handled by the framework as 400.
- Other successful requests still return 201, unaffected by global handlers.

**Limitation:** `MockMvc` tests MVC dispatching inside the Spring context without opening a real HTTP socket. If you need to verify the Servlet container, reverse proxies, infrastructure filter chains, forwarded headers, or real error dispatch, add tests with `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client.

## 10. Handling Errors in @ControllerAdvice and @RestControllerAdvice

### 10.1. When an Application Renders HTML Views

An MVC app with Thymeleaf templates can use `@ControllerAdvice` to return a view name:

~~~java
@ControllerAdvice
public class HtmlErrorAdvice {

    @ExceptionHandler(ProductNotFoundException.class)
    public String showNotFound(
            ProductNotFoundException ex,
            Model model) {

        model.addAttribute("message", "Product not found");
        return "errors/not-found";
    }
}
~~~

This is a **conceptually standalone fragment**, lacking `ProductNotFoundException`/template/imports and not part of the REST app in Section 7. If the app has a template `errors/not-found.html`, returning a String is treated as a view name. The same method inside `@RestControllerAdvice` would be treated as a response body string rather than a view.

### 10.2. When an API Needs JSON

For a REST API, a clearer approach is:

~~~java
@RestControllerAdvice
public class JsonErrorAdvice {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ProductNotFoundException ex) {

        ProblemDetail body = ProblemDetail.forStatus(
                HttpStatus.NOT_FOUND);
        body.setTitle("Product not found");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(body);
    }
}
~~~

This is an **illustrative fragment**; do not create this class in `com.example.errors` from Section 7 because it requires another exception type and would duplicate error strategies.

`@ControllerAdvice` can also return JSON if the handler is annotated with `@ResponseBody` or returns `ResponseEntity`. `@RestControllerAdvice` simplifies semantics for most REST error handlers rather than having “stronger” exception-handling powers.

## 11. Sensible HTTP Error Mapping Rules

Before choosing an HTTP status, determine the **nature of the error**:

| Scenario | Common Choice | Notes |
|---|---|---|
| Client sends unreadable JSON body | 400 | Do not expose parser stacktraces |
| Missing required field, Bean Validation fails | 400 | May return safe field names |
| Resource does not exist | 404 | May avoid leaking resource existence if security requires |
| Resource has state/version conflict | 409 | Per business contract |
| Unauthenticated | 401 | Use auth entry point when using Spring Security |
| Authenticated but lacks permission | 403 | Never trust self-declared role headers |
| Request exceeds size limit | 413 | Depends on container/proxy and exception mapping |
| Unsupported HTTP method | 405 | Preserve `Allow` header if generated by framework |
| Wrong request Content-Type | 415 | Preserve content negotiation semantics |
| Response cannot satisfy Accept | 406 | Do not unconditionally return JSON if client rejects it |
| Programming bug or internal dependency failure | 500 | Log internally, return generic message |

**Never catch all errors and return 200 with `{"success":false}`**: doing so breaks HTTP semantics, monitoring, retry behavior, and cache policies. Also do not return 404 for every backend error: operations teams must distinguish missing resources from database outages.

### 11.1. Preserving Meaningful HTTP Headers

Framework exceptions can carry headers that should be preserved, such as `Allow` for 405 or media-type details. When overriding `ResponseEntityExceptionHandler`, pass Spring's `headers` into `handleExceptionInternal` to avoid accidentally dropping them.

Rate limiting may require `Retry-After` on certain responses. Authentication requires `WWW-Authenticate` through the security mechanism. Returning “pretty JSON” is never a reason to strip standard headers.

## 12. Validation Exceptions Come in More Than One Flavor

### 12.1. @Valid @RequestBody

In a Spring MVC app with a Bean Validation provider, `@Valid @RequestBody` typically raises `MethodArgumentNotValidException` when the body binds into an object whose constraints fail. For example, `title=""` violates `@NotBlank`.

### 12.2. Method Parameter Validation

If a controller places constraints directly on method parameters, Spring Framework 6.1+ provides method validation raising `HandlerMethodValidationException`. Do not assume every `@NotBlank`/`@Min` surfaces as `MethodArgumentNotValidException`.

### 12.3. JSON Parsing Differs from Validation

A body like `{"title":` is not a `@NotBlank` error; the parser cannot construct the DTO and throws `HttpMessageNotReadableException` before Bean Validation even runs.

If you need a unified error contract, write tests for **each category**: parse failures, type mismatches, field validation failures, method validation failures, and business validation errors. Ensure details never leak sensitive values.

## 13. Common Mistakes When Writing @ExceptionHandler

| Symptom | Common Cause | Fix |
|---|---|---|
| Custom exception returns 500 instead of 404 | Missing handler or `@ResponseStatus` | Add `@ExceptionHandler`/`ResponseStatusException` in proper scope |
| Global handler does not run | Advice outside component scan or selector mismatch | Check packages, beans, and `@RestControllerAdvice` |
| Local handler runs instead of global | Local takes precedence in MVC | Keep local handlers only for controller-specific errors; test intent |
| Startup fails with ambiguous exception mapping | Two handlers target the same exception in one class | Merge or clarify mappings |
| A 400 error becomes 500 | Handler throws an exception itself or maps wrongly | Check server stack trace, write tests for error handlers |
| `@Valid` does not run | Missing validation provider/dependency or misplaced annotation | Add validation starter, check arguments |
| Malformed JSON skips validation handler | It is a parse error, not Bean Validation | Use `ResponseEntityExceptionHandler`/appropriate hook |
| `@ControllerAdvice` returns text view instead of JSON | Method returns String without response-body semantics | Use `@RestControllerAdvice`, `@ResponseBody`, or `ResponseEntity` |
| HTTP body leaks sensitive content | Copying raw exception message/stacktrace | Use client-safe detail, log internally |
| Security 401/403 skips MVC advice | Spring Security handles it in filter layer | Configure `AuthenticationEntryPoint`, `AccessDeniedHandler` |
| Pre-servlet filter error skips advice | Never reached `DispatcherServlet` | Handle at filter/security/container layer |
| `@ExceptionHandler` cannot fix error after response commit | Status/headers already sent | Design async/streaming error paths and observability |
| 405 response loses Allow header | Building `ResponseEntity` manually and ignoring framework headers | Use `handleExceptionInternal` or preserve headers |
| Two advices have surprising precedence | `@Order`, `Ordered`, selectors, cause matching | Test order and separate ownership clearly |
| API mixes HTML and JSON errors | Content negotiation/fallback differences | Design and test per `Accept` header |

### 13.1. A Catch-All Exception Handler Is Not the Default Plan

A global `@ExceptionHandler(Exception.class)` can be useful as a 500 fallback, but it can easily shadow specialized handlers. If used, ensure:

1. Return **500** only for unclassified errors—never convert every exception into 400.
2. Log server-side at an appropriate level with a correlation ID, without logging secrets.
3. Never send raw exception messages, SQL, or sensitive query params.
4. Do not break 401/403/405/415 handling or strip their headers.
5. Test internal errors, client errors, and Security behavior.

Not every error from background threads enters the MVC exception resolver; executors and message listeners require their own error handling.

### 13.2. Avoid Calling Exception Handlers Directly from Services

Services should express business errors via exceptions or result types, rather than importing or invoking `ApiExceptionAdvice` to build HTTP responses. Doing so couples the business layer to Spring Web and hurts reusability.

Recommended responsibility flow:

~~~text
Controller / Router
       |
       v
Application / Domain Service
       |
       +-- throws meaningful business error
       |
       v
MVC exception resolution
       |
       v
ApiExceptionAdvice -> HTTP response
~~~

### 13.3. Avoid Swallowing and Returning Null

~~~java
// Anti-pattern:
try {
    service.execute();
} catch (Exception ex) {
    return null;
}
~~~

This is a **fragment** assuming a `service`. Returning `null` can give the client an invalid response lacking an error body/status while hiding failures from operations. If a handler cannot resolve an issue, let the exception reach the proper layer or return a contracted error response.

## 14. Exception Handling with WebFlux and Functional Routers

Spring WebFlux uses `DispatcherHandler`, not Servlet `DispatcherServlet`. Although `@ExceptionHandler` / `@RestControllerAdvice` also support **WebFlux annotated controllers**, the base class, async return types, and exception pipeline belong to the **reactive stack**.

| Spring MVC | Spring WebFlux |
|---|---|
| `DispatcherServlet` | `DispatcherHandler` |
| `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` | `org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler` |
| `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` |
| `HandlerExceptionResolver` | Reactive exception handling/`WebExceptionHandler` |
| WebMvc.fn handler | WebFlux.fn handler returning `Mono<ServerResponse>` |

With **WebFlux.fn functional routes**, exceptions can be handled using `RouterFunction` filters, reactive infrastructure error handlers, or Boot's `ErrorWebExceptionHandler`. Never assume a `@RestControllerAdvice` written for annotated controllers covers every failure from functional handlers or `WebFilter`s.

**Do not copy the MVC override signature** `handleMethodArgumentNotValid(MethodArgumentNotValidException, HttpHeaders, HttpStatusCode, WebRequest)` verbatim into WebFlux: `WebRequest` and base-class hooks differ across stacks and versions. Check the reactive `ResponseEntityExceptionHandler` Javadoc for your version before overriding.

A WebFlux controller can return `Mono<T>`; if an error happens inside the Publisher, reactive error handling must also account for whether the response is already committed. `Mono.onErrorResume` can be used at the pipeline level for **intentional** error handling, but should never turn every failure into a successful 200 response.

## 15. Logging, Correlation IDs, and Error Localization

### 15.1. Public Detail vs. Internal Diagnostics

The two audiences serve different purposes:

- **Client error body:** HTTP status, public error code, safe detail, optional trace ID.
- **Server diagnostics:** exception chain, stacktrace, request timing, authenticated principal, correlation ID, dependency service, and origin.

Never put stacktraces, database credentials, absolute filesystem paths, SQL queries with secrets, or JWT tokens inside `ProblemDetail.detail`.

### 15.2. Correlation ID Is Not Authorization

You can attach a properly generated or validated request/trace ID via `ProblemDetail#setProperty("traceId", ...)`. However, if an ID comes from a client-supplied `X-Request-Id`, it **must never be used for authorization** and must be validated for format/length; tamper-resistant audits require server-generated IDs.

### 15.3. i18n with MessageSource

Spring Framework supports message codes for `ErrorResponse` and `ProblemDetail` via `MessageSource`. For common errors, locale-based message bundles can provide localized titles/details.

Even with i18n, keep a stable **machine-readable errorCode** or `type URI`; clients should not parse English or Vietnamese text from `detail` to drive business branching.

### 15.4. Type URI Is an API Contract

In `ProblemDetail`, `type` can be a URI pointing to documentation explaining the error category, such as a stable API documentation page. Do not invent URIs that do not exist or aren't controlled by your organization and force clients to depend on them. If no error-type registry exists yet, `about:blank` plus a documented custom code can suffice for lab work.

## 16. Pre-Deployment Testing Checklist

- [ ] Custom exceptions return accurate HTTP statuses (400/404/409...) rather than unexpectedly defaulting to 500.
- [ ] Local `@ExceptionHandler` handles only errors genuinely specific to that controller.
- [ ] Global `@RestControllerAdvice` is component-scanned and free of duplicate/ambiguous mappings.
- [ ] `@Order` and root/cause matching across advices are tested if multiple advices exist.
- [ ] Project includes `spring-boot-starter-validation` if using Bean Validation.
- [ ] JSON parsing, type mismatch, field validation, and method validation errors are tested separately.
- [ ] `ResponseEntityExceptionHandler` overrides match the exact API/version without duplicate handler declarations.
- [ ] HTTP statuses, `Content-Type`, `Allow`, `Retry-After`, or `WWW-Authenticate` are accurate where applicable.
- [ ] `ProblemDetail` is consistent and never leaks stacktraces/secrets/private data.
- [ ] Security 401/403 responses are handled properly at the filter/security boundary.
- [ ] Filter/async/streaming errors after response commit are explicitly designed.
- [ ] Error contract is tested with `Accept: application/json`, `application/problem+json`, and unmapped routes.
- [ ] Success paths are tested to confirm advices do not interfere with normal responses.
- [ ] HTTP integration tests run against a real container when production involves custom proxies/filters.
- [ ] Logging and monitoring include correlation IDs for diagnostics without exposing sensitive data.

## Official References

- [Spring Framework 6.2 — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html): exception mapping, handler arguments, result types, and cause matching.
- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html): scope, `@RestControllerAdvice`, local before global.
- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): RFC 9457 `ProblemDetail`, `ErrorResponse`, `ResponseEntityExceptionHandler`.
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): overridable protected methods.
- [Spring Framework 6.2 — Controller Advice Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html): ordering, causes, and selectors.
- [Spring Framework 6.2 — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): equivalent mechanism for the reactive stack.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Spring MVC and Boot error handling.
- [Spring Boot 3.5 — Spring Boot Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `server.error.*` and related options.

**Conclusion:** `@ExceptionHandler` answers “how is this exception turned into a response”; `@ControllerAdvice` shares handling across MVC controllers; `@RestControllerAdvice` provides convenient response-body semantics for REST. In modern Spring MVC, combining local handlers for special cases, global advice for business errors, and `ResponseEntityExceptionHandler` for framework errors gives your API clear statuses, `ProblemDetail` bodies, and reliable tests without leaking internal details.