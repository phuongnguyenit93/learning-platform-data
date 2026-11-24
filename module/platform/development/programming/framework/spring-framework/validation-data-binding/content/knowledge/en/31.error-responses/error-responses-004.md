# `@ExceptionHandler`, `@ControllerAdvice`, and `ResponseEntityExceptionHandler` in Spring MVC

## 1. Why do you need a consistent error response strategy?

When Spring MVC handles a request, errors can originate from multiple layers:

- **HTTP/argument resolution:** missing query parameters, unsupported HTTP methods, unreadable JSON, failed type conversion.
- **Validation:** an object marked with `@Valid` is invalid or a direct constraint on a controller parameter is violated.
- **Business logic:** booking not found, state transition disallowed, resource conflict.
- **System:** database failure, timeout, code bug, controller return value failing postconditions.

If every controller writes its own `try/catch` returning ad-hoc strings, the API quickly suffers from: HTTP 200 returned despite operation failure, inconsistent JSON structures across endpoints, leaked stack traces or sensitive data, and missing message localization.

Spring MVC provides three primary tools:

1. **`@ExceptionHandler`**: declares a method handling one or more exception types.
2. **`@ControllerAdvice`** (or `@RestControllerAdvice`): scopes exception handlers across multiple controllers, optionally filtered by package, annotation, or assignable type.
3. **`ResponseEntityExceptionHandler`**: a base class for global advice that handles many Spring MVC-generated exceptions, defaults to **RFC 9457 Problem Details**, and exposes `protected` hooks for customization.

**Important rule:** When extending `ResponseEntityExceptionHandler`, **override the proper `protected handle...` method** for exceptions Spring already maps in the base class; do not add a second `@ExceptionHandler` for the same exception in the same advice and cause an ambiguous mapping.

The scope of this lesson is **Spring Framework 6.2 + Spring MVC Servlet stack**, with a Spring Boot 3.5.6 and Java 17 example. WebFlux has a class with the same name `ResponseEntityExceptionHandler` in a **different package** using reactive semantics; do not copy the wrong import.

## 2. Overview of the exception handling flow

An MVC request typically flows through this chain:

```text
HTTP request
    |
    v
DispatcherServlet
    |
    +--> argument resolution / body conversion / binding / validation
    |        |
    |        +--> errors may be thrown before entering the controller
    |
    v
@Controller / @RestController method
    |
    +--> may throw a business exception
    |
    v
HandlerExceptionResolver chain
    |
    +--> ExceptionHandlerExceptionResolver
    |       |-- local @ExceptionHandler in the controller
    |       |-- @ExceptionHandler from a matching @ControllerAdvice
    |
    +--> ResponseStatusExceptionResolver
    |       |-- @ResponseStatus / ResponseStatusException
    |
    +--> DefaultHandlerExceptionResolver
            |-- maps certain Spring MVC errors to statuses
    |
    v
HTTP response (status, headers, body)
```

This diagram illustrates typical resolvers and does not replace checking ordering when an application registers custom `HandlerExceptionResolver` beans. MVC configures a resolver chain; once a resolver handles an exception, subsequent steps normally do not run.

For REST APIs, exception handling must decide **all three parts**: HTTP status, response headers, and response body. Returning an error message while keeping status 200 breaks the contract.

### 2.1. Exceptions can occur before the handler body runs

Example:

```java
@PostMapping("/bookings")
public String create(@Valid @RequestBody BookingRequest request) {
    // ...
    return "CREATED";
}
```

This is an **illustrative snippet** requiring the `BookingRequest` DTO and imports. Unreadable JSON can raise `HttpMessageNotReadableException` **before** the body of `create` executes. Readable DTOs that violate constraints typically throw `MethodArgumentNotValidException` if no adjacent `BindingResult` is declared and nothing triggers whole-method validation.

Therefore, a `try/catch` **inside a controller method** cannot catch every input error. Exception handlers at the MVC infrastructure layer cover the appropriate failures.

## 3. `@ExceptionHandler`: handling a specific exception

`@ExceptionHandler` can be placed directly inside a controller:

```java
@RestController
public class BookController {

    @GetMapping("/books/{id}")
    public String get(@PathVariable long id) {
        if (id != 7) {
            throw new BookNotFoundException(id);
        }
        return "Book 7";
    }

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<String> missing(BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body("Book not found");
    }
}
```

This is an **integrated illustrative snippet**, omitting the `BookNotFoundException` class and imports. The local exception handler above applies only to that controller (including subclasses where applicable). It is not system-wide handling.

### 3.1. Ways to specify the exception type

There are two common styles:

```java
@ExceptionHandler(BookNotFoundException.class)
ResponseEntity<String> handle(BookNotFoundException ex) {
    // ...
    return ResponseEntity.notFound().build();
}
```

Or letting Spring infer the type from the method argument:

```java
@ExceptionHandler
ResponseEntity<String> handle(BookNotFoundException ex) {
    // ...
    return ResponseEntity.status(404).body("Not found");
}
```

Both are **fragments**; do not declare both at the same time for the same exception inside the same controller or advice. Be explicit and unambiguous; avoid overlapping handler mappings that are hard to predict.

An `@ExceptionHandler` can accept MVC infrastructure arguments such as the exception, `WebRequest`, `HttpServletRequest`, and `Locale`, and return `ResponseEntity<?>`, `ProblemDetail`, `ModelAndView`, or other MVC-supported return types. However, not every `@RequestMapping` parameter works identically in an exception handler.

### 3.2. Local takes precedence over global

When the same exception can be handled by a controller-local handler and by a global advice, Spring MVC **checks local `@ExceptionHandler` methods before** handlers from `@ControllerAdvice`.

This is useful when one controller needs a custom message or recovery strategy. However, if the application wants uniform error JSON across every endpoint, keep systematic handling in global advice and override locally only with good reason.

## 4. `@ControllerAdvice` and `@RestControllerAdvice`: sharing and scoping

Instead of duplicating methods across controllers:

```java
@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(BookNotFoundException.class)
    ResponseEntity<String> notFound(BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body("Book not found");
    }
}
```

This is an illustrative integration snippet. `@RestControllerAdvice` is a convenience combination of `@ControllerAdvice` and `@ResponseBody`; return values from its exception handlers are written to the response body via HTTP message converters. Plain `@ControllerAdvice` can also return `ResponseEntity`, though it will not automatically write a returned `String` as a response body without `@ResponseBody`.

**Do not confuse `@ControllerAdvice` with a servlet filter or interceptor.** Advice participates in Spring MVC's handler-resolution pipeline; it does not automatically catch exceptions thrown in the security filter chain, before `DispatcherServlet`, or in tasks running outside HTTP requests.

### 4.1. Scoping advice

You can use selectors:

```java
@RestControllerAdvice(basePackages = "demo.api")
class ApiOnlyAdvice {}

@RestControllerAdvice(
    assignableTypes = {BookingController.class}
)
class BookingOnlyAdvice {}

@RestControllerAdvice(annotations = RestController.class)
class RestControllerOnlyAdvice {}
```

These classes are **separate selector examples**; you do not need all of them in one sample app. Without selectors, advice applies broadly. Selectors can scope by package, class, or annotation; when combining multiple selectors, check Spring's matching rules rather than assuming they always intersect.

### 4.2. Ordering multiple global advices

When multiple advices match, use `@Order` or `Ordered` to define precedence:

```java
@RestControllerAdvice
@Order(10)
class BusinessAdvice {}

@RestControllerAdvice
@Order(20)
class FallbackAdvice {}
```

A lower `@Order` value has higher precedence among regular advice beans. Within the **same advice**, a root exception match is normally preferred over a cause match; however, **across advices**, a cause match in a higher-precedence advice may be selected before a root match in a lower-precedence advice.

Consequently, placing an overly broad `@ExceptionHandler(Exception.class)` in the highest-precedence advice can shadow specific handlers in other advices. Design exception groups with clear scopes and ordering.

### 4.3. Root exception vs. nested cause

Spring MVC can match an exception handler against the directly thrown exception or a nested cause in the chain. For example, an `IllegalStateException` wrapping an `IOException` can match an `IOException` handler in an applicable advice.

To avoid ambiguity, keep signatures specific. When a handler receives an exception matched via a nested cause, remember that the delivered object may not be the original root exception; do not write logic assuming every invocation receives the same wrapper layer.

Spring also allows a handler to **rethrow the original exception** to delegate handling to subsequent resolvers/handlers when a dynamic condition does not apply. Use that strategy only when you understand resolver ordering and back it with tests.

## 5. `ResponseEntityExceptionHandler`: built-in extension point for MVC

`org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` is the base class for handling Spring MVC exceptions such as body, binding, validation, HTTP method/media type, and `ErrorResponseException` types.

When using it:

```java
@RestControllerAdvice
public class GlobalApiExceptionHandler
        extends ResponseEntityExceptionHandler {
    // Override the protected methods you want to customize.
}
```

The base class already defines an `@ExceptionHandler` method covering the MVC exceptions it supports. As of Spring 6.2, `handleException(Exception, WebRequest)` is **`final`**. Therefore:

- **Do not override `handleException(...)`.**
- **Do not add `@ExceptionHandler(MethodArgumentNotValidException.class)` in the subclass to compete for the same exception**; override `handleMethodArgumentNotValid(...)` instead.
- You may add `@ExceptionHandler(MyBusinessException.class)` for **custom business exceptions** not handled by the base class.
- You may override `handleExceptionInternal(...)` for cross-cutting behavior, or `createResponseEntity(...)` when you need to intercept the final response creation step.

### 5.1. Selected Spring 6.2 protected hooks

| Overridable method | Situation |
| --- | --- |
| `handleMethodArgumentNotValid(...)` | Invalid DTO/form object during argument-level validation |
| `handleHandlerMethodValidationException(...)` | Method validation on controller parameters/return value, Spring MVC 6.1+ |
| `handleHttpMessageNotReadable(...)` | Unreadable JSON/body, value cannot be deserialized |
| `handleTypeMismatch(...)` | Type conversion failure during argument binding |
| `handleMissingServletRequestParameter(...)` | Missing required query/form parameter |
| `handleHttpRequestMethodNotSupported(...)` | Unsupported HTTP method |
| `handleHttpMediaTypeNotSupported(...)` | Unsupported `Content-Type` |
| `handleHttpMediaTypeNotAcceptable(...)` | Cannot negotiate response media type |
| `handleErrorResponseException(...)` | `ErrorResponseException` |
| `handleExceptionInternal(...)` | Common hook after status/body have been determined |
| `createResponseEntity(...)` | Final interception before returning `ResponseEntity` |

**Do not copy Spring 5.x override signatures into 6.2.** Spring 6 uses `HttpStatusCode` in many callbacks rather than `HttpStatus` everywhere. Use your IDE or the matching version's Javadoc to verify method names and parameter order.

Exact signatures of the two validation hooks in Spring 6.2:

```java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    // ...
}

@Override
protected ResponseEntity<Object> handleHandlerMethodValidationException(
        HandlerMethodValidationException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    // ...
}
```

These are **fragments showing signatures only**; appropriate return bodies and imports are needed. A complete program is in Section 8.

### 5.2. Preserve the status and headers determined by the framework

In overrides, the `status` and `headers` parameters are not decorative. For example, a method-not-supported error can carry an `Allow` header; other exceptions may carry headers required by the HTTP contract.

For request validation, the typical status is 400. However, **return-value** validation on a controller can carry status 500. Never write a helper that forces every `HandlerMethodValidationException` to 400.

Calling `handleExceptionInternal(ex, body, headers, status, request)` preserves the base class's standard processing. Only alter status or headers with clear justification and tests.

## 6. `ProblemDetail` and RFC 9457

Spring Framework 6+ supports `org.springframework.http.ProblemDetail`, based on RFC 9457 *Problem Details for HTTP APIs*. Core fields:

| Property | Meaning |
| --- | --- |
| `type` | URI identifying the problem type; defaults typically to `about:blank` |
| `title` | Short, human-readable error title |
| `status` | HTTP status of the problem |
| `detail` | Explanation for this specific occurrence |
| `instance` | URI identifying the occurrence, typically the request path |
| Extension properties | Application-specific fields, such as `fields`, `code`, `traceId` |

Illustrative JSON example:

```json
{
  "type": "about:blank",
  "title": "Invalid request",
  "status": 400,
  "detail": "Request body validation failed",
  "instance": "/bookings",
  "fields": ["customer", "seats"]
}
```

When using `ProblemDetail` as the body, Spring MVC can emit media type **`application/problem+json`** and populate `instance` from the request path if unset. Do not assume JSON key ordering is always identical or that every optional field is present in all configurations.

### 6.1. Creating a `ProblemDetail`

```java
ProblemDetail p = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
p.setTitle("Invalid request");
p.setDetail("Please correct your input");
p.setProperty("code", "INVALID_INPUT");
```

This is a Java **fragment**. `setProperty(...)` adds an extension property, and Spring/Jackson supports serializing these extension properties into the JSON response.

### 6.2. `ErrorResponse` and `ErrorResponseException`

`ErrorResponse` is Spring's abstraction representing error status, headers, and a `ProblemDetail`. Many Spring MVC exceptions implement this contract. `ErrorResponseException` is an implementation you can throw when the application needs to raise an HTTP error with a configured body.

There is also `ResponseStatusException` for reporting status/reason directly in code. Still, to guarantee a unified error format independent of exception message text, prefer `@ControllerAdvice` / `ResponseEntityExceptionHandler` or an intentional error response abstraction.

### 6.3. Security principles for the response body

- Never return exception class names, stack traces, SQL queries, repository paths, tokens, or passwords.
- Never automatically serialize raw `BindingResult` or `FieldError#getRejectedValue()`.
- For HTTP 500, use a generic message; log details server-side with a correlation ID if available.
- Never echo all incoming headers or request bodies into `ProblemDetail`.
- When returning a list of invalid fields, consider allowlisting public field names so sensitive domain structures are not exposed.

## 7. Choosing the right exception for binding and validation

A controller can encounter the following exceptions:

| Case | Typical exception in Spring MVC 6.1+ | Typical status |
| --- | --- | --- |
| `@Valid @RequestBody DTO` fails a constraint, no adjacent `BindingResult`, and whole-method validation not triggered | `MethodArgumentNotValidException` | 400 |
| Direct `@Min(1)` constraint on `@RequestParam` | `HandlerMethodValidationException` | 400 if input invalid |
| Constraint on controller return value | `HandlerMethodValidationException` | 500 |
| Malformed or unreadable JSON | `HttpMessageNotReadableException` | 400 |
| Required query parameter is missing | `MissingServletRequestParameterException` | 400 |
| Cannot convert `page=abc` to `int` | `MethodArgumentTypeMismatchException` | 400 |
| Unsupported HTTP method | `HttpRequestMethodNotSupportedException` | 405 |
| Unsupported request media type | `HttpMediaTypeNotSupportedException` | 415 |
| Application resource not found | Custom exception such as `BookingNotFoundException` | Handler-dependent, usually 404 |
| Unrecognized bug or infrastructure failure | Any exception | 500, should not expose internal details |

These rows are **typical cases**, not a guarantee that every signature or configuration takes one exact exception path. Converters, `@ControllerAdvice`, AOP method validation, and custom argument resolvers can alter the execution path.

### 7.1. Does `BindingResult` make the exception disappear?

A handler such as:

```java
@PostMapping("/forms")
public String save(
        @Valid @ModelAttribute("form") SignupForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "formView";
    }
    return "successView";
}
```

places `BindingResult` **immediately after** the form so the handler can process binding/validation errors inline. In that case, `MethodArgumentNotValidException` is not necessarily thrown. Do not expect global exception advice to receive all validation errors if a controller accepts `BindingResult` and returns a view or status itself.

### 7.2. Direct method constraints since Spring MVC 6.1

`@Valid` on an object is a cascade marker. When you place `@Min`, `@NotBlank`, or other constraints directly on method parameters or return types, Spring MVC can apply **built-in method validation** to the handler.

Adding class-level `@Validated` on a controller can switch to Spring AOP-based method validation. Spring MVC 6.1+ documentation recommends omitting class-level `@Validated` when you want built-in MVC method validation; otherwise, a different exception (such as `ConstraintViolationException`) may be thrown.

### 7.3. Exceptions from filters or the security chain

`@ControllerAdvice` is not the sole mechanism for standardizing system errors. Authentication/authorization failures arising in the Spring Security filter chain are normally handled by `AuthenticationEntryPoint` or `AccessDeniedHandler`. Build a consistent error contract at the corresponding boundary rather than trying to catch every security exception in controller advice.

## 8. Complete application: Java 17 + Spring Boot 3.5.6

This example demonstrates all three tools:

1. The controller throws a **custom business exception**.
2. Spring MVC automatically throws **validation/binding** exceptions.
3. Global `@RestControllerAdvice extends ResponseEntityExceptionHandler` overrides standard hooks and adds an `@ExceptionHandler` solely for the business exception.

The application runs on Java 17+, Maven 3.x, with no database or template engine required.

### 8.1. File structure

```text
mvc-error-response-demo/
├── pom.xml
└── src/main/java/demo/errors/
    ├── ErrorDemoApplication.java
    ├── BookingController.java
    ├── BookingNotFoundException.java
    └── GlobalApiExceptionHandler.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>mvc-error-response-demo</artifactId>
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

`spring-boot-starter-web` configures Spring MVC and embedded Tomcat, while `spring-boot-starter-validation` provides the Jakarta Validation provider.

### 8.3. `ErrorDemoApplication.java`

```java
package demo.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorDemoApplication.class, args);
    }
}
```

### 8.4. `BookingNotFoundException.java`

```java
package demo.errors;

public class BookingNotFoundException extends RuntimeException {

    public BookingNotFoundException(long id) {
        super("Booking " + id + " not found");
    }
}
```

The exception message is only for diagnostics. The global handler does **not** pass raw `ex.getMessage()` into public responses so internal details are never leaked.

### 8.5. `BookingController.java`

```java
package demo.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/bookings")
public class BookingController {

    public record BookingRequest(
        @NotBlank String customer,
        @NotNull @Min(1) Integer seats
    ) {}

    @PostMapping
    public ResponseEntity<String> create(
            @Valid @RequestBody BookingRequest request) {

        return ResponseEntity.status(HttpStatus.CREATED).body(
            "BOOKED:" + request.customer() + ":" + request.seats());
    }

    @GetMapping
    public String list(@RequestParam("page") @Min(1) int page) {
        return "PAGE:" + page;
    }

    @GetMapping("/{id}")
    public String find(@PathVariable("id") long id) {
        if (id != 7L) {
            throw new BookingNotFoundException(id);
        }
        return "BOOKING:7";
    }

    @GetMapping("/bad-return")
    @NotBlank
    public String badReturn() {
        // Intentionally violates postcondition to test HTTP 500.
        return "";
    }
}
```

Error paths explained:

- `POST /bookings` with valid JSON creates a booking and returns 201.
- The `BookingRequest` DTO has field constraints; `@Valid` makes MVC validate after deserialization. On invalid input, the handler body is not invoked.
- `GET /bookings?page=0` violates the **direct method constraint `@Min(1)`**. In Spring MVC 6.1+, this takes the `HandlerMethodValidationException` path.
- `GET /bookings/99` throws the custom `BookingNotFoundException`.
- `GET /bookings/bad-return` intentionally returns an empty string while the method has `@NotBlank` on its return value, triggering server-side validation and HTTP 500.

Class-level `@Validated` is omitted on the controller so built-in method validation is used. The `/bad-return` path is more specific than the `/{id}` path-variable mapping; Spring MVC selects the more specific mapping.

### 8.6. `GlobalApiExceptionHandler.java`

```java
package demo.errors;

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
public class GlobalApiExceptionHandler
        extends ResponseEntityExceptionHandler {

    // DTO validation error: override the base class hook.
    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<String> fields = ex.getBindingResult().getFieldErrors()
            .stream()
            .map(FieldError::getField)
            .distinct()
            .sorted()
            .toList();

        ProblemDetail detail = ProblemDetail.forStatus(status);
        detail.setTitle("Invalid request");
        detail.setDetail("Request body validation failed");
        detail.setProperty("fields", fields);

        return handleExceptionInternal(
            ex, detail, headers, status, request);
    }

    // Spring MVC 6.1+ method validation: input 400, return value 500.
    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail detail = ProblemDetail.forStatus(status);
        detail.setTitle(ex.isForReturnValue()
            ? "Invalid server response"
            : "Invalid request parameters");
        detail.setDetail(ex.isForReturnValue()
            ? "Controller returned invalid data"
            : "Controller parameters failed validation");

        return handleExceptionInternal(
            ex, detail, headers, status, request);
    }

    // Unreadable body: decoder/converter failure distinct from constraints.
    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail detail = ProblemDetail.forStatus(status);
        detail.setTitle("Unreadable request body");
        detail.setDetail("Malformed JSON or incompatible value");

        return handleExceptionInternal(
            ex, detail, headers, status, request);
    }

    // Custom business exception not mapped by the base class.
    @ExceptionHandler(BookingNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            BookingNotFoundException ex) {

        ProblemDetail detail = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, "Booking was not found");
        detail.setTitle("Booking not found");

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(detail);
    }
}
```

This is the complete source for the demo app's global advice. Key notes:

1. **Three framework errors are handled via `@Override protected handle...`**. They have no extra `@ExceptionHandler` annotation, avoiding duplicate mappings with the base class.
2. The business exception `BookingNotFoundException` has its own `@ExceptionHandler` because it is not a built-in error type registered by the base class.
3. `HttpStatusCode status` is preserved when calling `handleExceptionInternal(...)`. This keeps 400 vs. 500 accurate per error kind.
4. `FieldError#getField()` is used to produce a sorted list of field names, **never** returning rejected values.
5. `ex.getMessage()` is never returned directly to the client.
6. `ProblemDetail` is serialized by Spring as an RFC 9457 error body; `instance` may be populated automatically from the request path.
7. If you want a public error code, you can call `detail.setProperty("code","INVALID_BOOKING")` and test contract stability.

### 8.7. Running the application

In the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

By default, the server listens on `http://localhost:8080` if the port is free. In another bash/zsh/WSL terminal, test via HTTP.

**Case A — valid booking:**

```bash
curl -i -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/json' \
  -d '{"customer":"Alice","seats":2}'
```

HTTP **201 Created**, body:

```text
BOOKED:Alice:2
```

**Case B — DTO with two invalid fields:**

```bash
curl -i -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/json' \
  -d '{"customer":"","seats":0}'
```

HTTP **400 Bad Request**. The `ProblemDetail` response body includes these key fields:

```json
{
  "title": "Invalid request",
  "status": 400,
  "detail": "Request body validation failed",
  "fields": ["customer", "seats"]
}
```

The JSON above **highlights the fields to check**, rather than being a byte-for-byte literal: Spring may also add `type`, `instance`, and media type `application/problem+json`; property order depends on the serializer. `fields` is sorted for determinism.

**Case C — direct constraint on a query parameter:**

```bash
curl -i 'http://localhost:8080/bookings?page=0'
```

HTTP **400 Bad Request**, `title` is:

```text
Invalid request parameters
```

This error path goes through the `handleHandlerMethodValidationException` override, not `handleMethodArgumentNotValid`.

**Case D — custom not-found business exception:**

```bash
curl -i 'http://localhost:8080/bookings/99'
```

HTTP **404 Not Found**, `title` and `detail`:

```text
title: Booking not found
detail: Booking was not found
```

This is handled by the `@ExceptionHandler(BookingNotFoundException.class)` method added to the subclass.

**Case E — syntactically invalid JSON body:**

```bash
curl -i -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/json' \
  -d '{"customer":'
```

HTTP **400 Bad Request**, `title` and `detail`:

```text
title: Unreadable request body
detail: Malformed JSON or incompatible value
```

This error occurs **before Bean Validation**; therefore, do not expect `fields` to list constraint failures.

**Case F — return-value validation failure:**

```bash
curl -i 'http://localhost:8080/bookings/bad-return'
```

HTTP **500 Internal Server Error**, `title` is:

```text
Invalid server response
```

This is a controller postcondition violation; it must not be collapsed into HTTP 400 merely because it shares the `HandlerMethodValidationException` class.

**Case G — type conversion error:**

```bash
curl -i 'http://localhost:8080/bookings?page=abc'
```

Here `String "abc"` cannot be converted to `int`. MVC typically throws `MethodArgumentTypeMismatchException`, and the base class handles it as a 400 error. Do **not** expect the body from the `handleHandlerMethodValidationException` override, because `@Min(1)` never received a valid numeric value to evaluate.

**Case H — missing query parameter:**

```bash
curl -i 'http://localhost:8080/bookings'
```

Because `@RequestParam("page")` defaults to `required=true`, omitting `page` typically raises `MissingServletRequestParameterException`; the base handler processes it with HTTP 400 per RFC 9457. This is a different branch from `page=0`.

Every `curl -i` call prints both headers and body. The output snippets above show **values to verify**, not a claim that every header or JSON property order is identical across environments.

## 9. Avoid duplicate `@ExceptionHandler` in subclasses

A common mistake:

```java
@RestControllerAdvice
public class WrongAdvice extends ResponseEntityExceptionHandler {

    // NOT RECOMMENDED: maps an error already handled in the base class.
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<String> anotherHandler(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest().body("Invalid");
    }
}
```

This is **intentionally broken illustrative code**; do not add it to the project in Section 8. The base class already declares an `@ExceptionHandler` method covering `MethodArgumentNotValidException`. Adding a competing handler can cause Spring MVC to report **ambiguous `@ExceptionHandler` method mapped**, failing application startup rather than handling requests.

Correct way:

```java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {

    ProblemDetail detail = ProblemDetail.forStatus(status);
    detail.setTitle("Invalid request");
    return handleExceptionInternal(
        ex, detail, headers, status, request);
}
```

This is a valid fragment when placed inside the subclass with appropriate imports.

### 9.1. When to write a separate `@ExceptionHandler`?

Use one for exceptions **not handled by the base class** or when not extending the base class:

- `EntityNotFoundException`/custom business exceptions.
- `OptimisticLockingFailureException` if you map conflicts to HTTP 409 per your domain contract.
- Application-defined exceptions representing "invalid state transition".

Do not catch every `RuntimeException` and return 400 by default; that hides server bugs and violates HTTP semantics. If you add a catch-all for 500, return a safe message, log server-side, and consider letting default error infrastructure handle unexpected failures.

## 10. Validation error responses: body and stable codes

Instead of returning raw `FieldError` objects, define a structured contract:

```json
{
  "type": "https://api.example.test/problems/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid",
  "code": "INVALID_INPUT",
  "violations": [
    {"field": "customer", "code": "NotBlank"},
    {"field": "seats", "code": "Min"}
  ]
}
```

This example only illustrates the design, **not the byte-for-byte body of the demo source**. You can use `ProblemDetail#setType(URI)` and `setProperty("violations", ...)` to attach extension details.

Note that `FieldError#getCode()` is usually a general code like `NotBlank`, whereas `getCodes()` is an array of prioritized object/field codes. Clients should not parse `getDefaultMessage()` sentences for logic. If error codes are part of the public API, define stable mappings owned by the application.

### 10.1. Distinguishing `FieldError` and `ObjectError`

`BindingResult#getFieldErrors()` contains only field errors. Custom validators can register **global errors** via `errors.reject(...)`; these appear through `getGlobalErrors()` or `getAllErrors()`.

The demo only outputs field names; production systems should decide how to represent global errors so multi-attribute rules are not lost. If a response only iterates over field errors, verify that business validators do not have object-level rules that must be exposed.

### 10.2. `MessageSource` and localization

Spring `MessageSource` can resolve `ObjectError`/`FieldError` (which implement `MessageSourceResolvable`) for a `Locale`:

```java
String displayMessage = messageSource.getMessage(error, locale);
```

This is a fragment assuming `messageSource`, `error`, and `locale` are in scope. With `ResponseEntityExceptionHandler`, Spring supports message lookup and configuration for `ProblemDetail`. Align on an i18n strategy and avoid hardcoding English text in advice if the application supports multiple languages.

**Do not confuse** Jakarta Bean Validation's `ValidationMessages.properties` bundle with Spring `MessageSource`'s `messages.properties` unless you have explicitly configured them to share the same source.

## 11. Local handler, global advice, or base handler: which to choose?

| Need | Usually appropriate choice | Why |
| --- | --- | --- |
| One controller needs custom recovery rules | `@ExceptionHandler` inside the controller | Clear local scope |
| Multiple REST controllers share a uniform error contract | `@RestControllerAdvice` | Reuse and centralized management |
| Need to format all standard MVC framework errors | `ResponseEntityExceptionHandler` as base | Dedicated hooks, standard status/headers |
| Only a few custom business exceptions | `@ExceptionHandler` inside advice | Targeted mapping without overriding base |
| Modify final structure of all base responses | `createResponseEntity(...)` | Centralized interception before sending |
| Add shared logic across framework exceptions | `handleExceptionInternal(...)` | Common processing step |
| Auth failures in the Security filter chain | `AuthenticationEntryPoint` / `AccessDeniedHandler` | Not all paths go through `@ControllerAdvice` |
| Exceptions outside MVC requests | Handle at the corresponding boundary | Controller advice does not cover schedulers/Kafka/background tasks |

A system can combine levels, but should minimize duplicate mappings and implicit advice ordering.

## 12. `@Order`, exception specificity, and overly broad handlers

Suppose there are two advices:

```java
@RestControllerAdvice
@Order(10)
class GenericAdvice {

    @ExceptionHandler(Exception.class)
    ResponseEntity<String> all(Exception ex) {
        return ResponseEntity.internalServerError()
                .body("Unexpected error");
    }
}

@RestControllerAdvice
@Order(20)
class BusinessAdvice {

    @ExceptionHandler(BookingNotFoundException.class)
    ResponseEntity<String> missing(BookingNotFoundException ex) {
        return ResponseEntity.status(404).body("Not found");
    }
}
```

This is an **illustrative configuration**; do not add it to the main project. Because `@Order(10)` takes precedence over `@Order(20)`, `GenericAdvice`'s broad handler can intercept business errors intended for `BusinessAdvice`, returning HTTP 500 instead of 404.

Place specific handlers at an appropriate precedence tier, or avoid registering broad catch-all handlers unnecessarily. Within a single advice, Spring compares exception class depth and favors more specific matches; across multiple advices, however, `@Order` takes effect rather than exception specificity alone.

If an advice has a package/type selector, its handlers only apply when the active controller matches that selector. Errors outside that scope fall through to base or default resolvers.

## 13. Using `ResponseEntityExceptionHandler` to add safe metadata

A common extension is adding a uniform error code. If every `ProblemDetail` from the base class should carry `code`, you can override `createResponseEntity(...)`, while preserving exact status and headers and avoiding unintended response changes.

Illustrative fragment:

```java
@Override
protected ResponseEntity<Object> createResponseEntity(
        Object body,
        HttpHeaders headers,
        HttpStatusCode statusCode,
        WebRequest request) {

    if (body instanceof ProblemDetail detail) {
        detail.setProperty("code", "HTTP_ERROR");
    }

    return super.createResponseEntity(
        body, headers, statusCode, request);
}
```

This is a **fragment for a subclass** and is not needed in the main source. Using `code="HTTP_ERROR"` for every status loses root-cause classification. In real applications, map specific codes based on exception type, status, and domain semantics.

### Trace/correlation ID

If your infrastructure has tracing, you can attach a sanitized correlation ID to an extension property. Never return stack traces or request headers containing tokens; never expose MDC or tracing details that the API does not intend to publish.

### Already-committed responses

Once an HTTP response has begun writing headers or body, an exception handler may no longer be able to alter the status. Spring's internal handler may return `null` when the response is already committed. Therefore, exception advice does not replace transactional design, streaming error handling, or client retry strategies.

## 14. Practical testing

Unit tests calling a controller method directly do **not** exercise full argument resolution/validation and do not trigger `HandlerExceptionResolver`. For MVC errors, use `MockMvc` or HTTP integration tests.

Minimum test suite:

| Test | Expectation |
| --- | --- |
| Valid JSON, `customer=Alice,seats=2` | 201, `BOOKED:Alice:2` |
| `customer=""`, `seats=0` | 400, title `Invalid request`, expected field list |
| `GET /bookings?page=0` | 400, title `Invalid request parameters` |
| `GET /bookings?page=1` | 200, body `PAGE:1` |
| `GET /bookings/99` | 404, title `Booking not found` |
| `GET /bookings/7` | 200, body `BOOKING:7` |
| Syntactically invalid JSON | 400, title `Unreadable request body` |
| `GET /bookings/bad-return` | 500, title `Invalid server response` |
| `GET /bookings?page=abc` | 400 from type mismatch, does not enter direct `@Min` handler |
| Missing `page` | 400 from missing request parameter |
| `POST` with unsupported content type | 415, appropriate headers/body |
| Unsupported HTTP method | 405, `Allow` header if applicable |

To verify there are no ambiguous mappings, the application must start the Spring context successfully. A base subclass with two handlers colliding on `MethodArgumentNotValidException` fails when setting up the exception resolver; testing valid endpoints also catches this.

### 14.1. Example test with `MockMvc`

If you add `spring-boot-starter-test` with `test` scope to `pom.xml`, you can write:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ErrorApiTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidQueryGetsProblemDetail() throws Exception {
        mvc.perform(get("/bookings").param("page", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.title")
                .value("Invalid request parameters"));
    }
}
```

This is a **test fragment** without imports, test dependency, or standalone source file, so it is outside the minimal runnable app. `MockMvc` runs Spring MVC's resolver chain and exception advice; calling `new BookingController().list(0)` lacks the runtime machinery needed to verify this.

## 15. Common mistakes and fixes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Spring reports ambiguous exception handler mapping | Base subclass adds `@ExceptionHandler` for a built-in exception | Override `handleMethodArgumentNotValid` or the corresponding hook |
| DTO is invalid but advice never runs | Controller declares an adjacent `BindingResult` and handles it inline | Decide clearly between local and centralized validation handling |
| Direct `@Min` throws an unexpected exception | Spring MVC 6.1+ uses whole-method validation | Handle `HandlerMethodValidationException` |
| Invalid JSON still returns default format | Only validation hooks overridden, not decoder hook | Customize `handleHttpMessageNotReadable` |
| Controller-local handler is skipped | Failure occurs before controller selection or scope mismatch | Check handler selection and advice/global fallback |
| Status 500 accidentally turned into 400 | Treating all validation exceptions with one status | Respect `status` and `isForReturnValue()` |
| Required headers disappear | Building a brand-new response and ignoring `headers` | Forward the `headers` passed by the base class |
| Business 404 caught by generic 500 handler | `@Order` or catch-all too broad | Prioritize specific handlers; avoid masking via generic advice |
| API leaks stack trace or input data | Serializing exception/`BindingResult` directly | Use `ProblemDetail` with safe fields/codes/messages |
| Security exceptions never reach advice | Thrown inside the Security filter chain | Configure `AuthenticationEntryPoint`/`AccessDeniedHandler` |
| Swagger/client expects `application/json` but gets `problem+json` | RFC 9457 uses a distinct media type | Document content negotiation and schema |
| Direct controller test sees no errors | Bypasses Spring MVC runtime | Use `MockMvc`/HTTP integration tests |
| Override signature fails to compile | Copied Spring 5.x signature or omitted `HttpStatusCode` | Check Javadoc for the exact Spring version |
| Exception handled yet response unchanged | Response headers/body already committed | Inspect streaming/async semantics |

## 16. Safe implementation guidelines

1. **Classify errors by source:** input validation 400; not found 404; conflict 409; unsupported method 405; unexpected server errors 500.
2. **Keep the contract stable:** client-facing codes must not depend on English/Vietnamese phrasing, exception class names, or stack traces.
3. **Use `ProblemDetail`/RFC 9457 intentionally:** standard fields for HTTP semantics, extension properties for public data.
4. **Preserve framework status and headers:** especially when overriding protected base hooks.
5. **Do not let catch-alls shadow important exceptions:** review `@Order` and scopes.
6. **Do not ignore errors captured in `BindingResult`:** global advice will not automatically know if a controller swallowed errors and returned success.
7. **Prevent information leaks:** never serialize raw arguments, rejected values, SQL queries, or environment paths.
8. **Test real HTTP requests:** content type, validation, conversion, binding, and method return-value validation.
9. **Distinguish MVC from WebFlux:** `ResponseEntityExceptionHandler` lives in a different package; imports and reactive error semantics differ.
10. **Do not use exception handlers in place of authorization or transactions:** enforce permissions and control side effects at the proper layers.

## 17. Summary

**`@ExceptionHandler`** handles exceptions by type within a controller or advice. **`@ControllerAdvice` / `@RestControllerAdvice`** applies handlers across multiple controllers using selectors and ordering. **`ResponseEntityExceptionHandler`** is the built-in base class for standardizing MVC framework errors, offering hooks such as `handleMethodArgumentNotValid`, `handleHandlerMethodValidationException`, `handleHttpMessageNotReadable`, and `handleExceptionInternal`.

With Spring MVC 6.2, prefer **overriding protected hooks for built-in exceptions** and add `@ExceptionHandler` only for custom business exceptions. Use `ProblemDetail` to convey HTTP status/title/detail along with safe extension properties, preserve framework-supplied status and headers, and test failures occurring before the controller, inside the controller, and on controller return values.

## References

- Spring Framework 6.2 — Exception handlers: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework 6.2 — Controller advice, scope and precedence: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html
- Spring Framework 6.2 — Error Responses, ProblemDetail and RFC 9457: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — HandlerExceptionResolver chain: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework 6.2 Javadoc — ResponseEntityExceptionHandler: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.2 Javadoc — HandlerMethodValidationException: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 Javadoc — ProblemDetail: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/http/ProblemDetail.html
- Spring Framework 6.2 — Validation in annotated controllers: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457