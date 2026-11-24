# Turning Input Errors into Consistent Responses Without Blocking in Spring WebFlux

## 1. Goal

A reactive API needs to handle bad, missing, or invalid data in a consistent way so the client knows what to fix, while the server still preserves the proper asynchronous lifecycle. When a client sends malformed JSON, an unconvertible query parameter, a field violating Bean Validation, or an unmet business rule, the controller needs to return an appropriate HTTP status and error body.

This lesson focuses on **Spring WebFlux annotated controllers**, Project Reactor, and Spring Framework 6.1+/Spring Boot 3.2+. Main goals:

- Distinguish **binding**, **type conversion**, **Bean Validation**, and **business validation**.
- Recognize common exceptions, especially `WebExchangeBindException` and `HandlerMethodValidationException`.
- Standardize errors with `@RestControllerAdvice` and RFC 9457 `ProblemDetail`.
- Combine error handling with `Mono/Flux` without calling `block()` or subscribing manually with `subscribe()`.
- Test status codes, error bodies, and error paths with `WebTestClient`.

**Not blocking the thread** does not mean skipping validation. It means keeping asynchronous I/O operations inside the reactive pipeline, not blocking the Netty event loop to wait for results, and not creating a separate subscription detached from the HTTP request.

## 2. Four error classes to distinguish

When a request enters a controller, errors can occur at different stages:

| Class | Example | When does it usually occur? | How to handle |
| --- | --- | --- | --- |
| Binding / decoding | Malformed JSON, unreadable body, missing required value | Reading the request and creating method arguments | HTTP 400 or corresponding status; describe invalid input |
| Type conversion | `?page=abc` while the method requires `int page` | Converting HTTP strings to Java types | HTTP 400; indicate the wrong parameter/format if safe |
| Bean Validation | Invalid email format, blank name, age out of bounds | After binding the object or when checking method parameters | HTTP 400; return list of field/parameter errors |
| Business validation | Email already exists, order state disallows the operation | In the service or when querying business rules | Status per contract, e.g. 409 Conflict |

These four classes should not be lumped into one “server error” message. The client needs to know whether the request has wrong syntax, wrong fields, or conflicts with current state.

Nor should you return the entire exception message or stack trace to the client. An exception can contain class names, SQL statements, rejected values, or internal details. The error response should have a code/status, a stable message, and selected field errors.

## 3. Processing flow in WebFlux

A request passing through a reactive controller can be pictured as:

```text
HTTP request
    |
    v
Resolve route + read headers/query/body
    |
    v
Bind method arguments + convert types
    |
    v
Bean Validation / method validation
    |
    +---- invalid ----> Exception / ErrorResponse
    |                         |
    |                         v
    |                 @RestControllerAdvice
    |                         |
    |                         v
    |                 HTTP ProblemDetail
    |
    v
Controller returns Mono / Flux
    |
    v
Reactive service + non-blocking I/O
    |
    +---- business error ---> onError signal
    |                              |
    |                              v
    |                      @ExceptionHandler
    |
    v
Serialize response asynchronously
```

Spring WebFlux resolves method arguments and applies validation according to the framework contract. When the handler returns `Mono`/`Flux`, the framework manages the subscription and writes the response. Errors arising while reading the body, binding, or validating can be translated into an HTTP error response; errors arising later in the reactive pipeline travel as `onError` signals.

**Bean Validation is normally a synchronous and primarily CPU-bound operation**, for example checking blank strings, lengths, or regexes. The framework calls the validator during request processing. That does not mean every validator is suitable for heavy work: do not call a database, HTTP, or any blocking API from a `ConstraintValidator` on the event loop. Checks that depend on I/O must be expressed as publishers in the service.

## 4. Binding and decoding errors before the controller runs

Example endpoint receiving JSON:

```java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @RequestBody Mono<CreateAccountRequest> body) {
    return body.map(this::toResponse);
}
```

This is illustrative code. When the client sends JSON, WebFlux uses a message reader/codec to read the body and create the object. Several errors happen before the business method receives the object:

- Syntactically invalid or non-deserializable JSON.
- JSON value incompatible with the Java type, for example a string where an integer is required.
- Missing required body.
- Unsupported Content-Type.
- Missing or unconvertible query/header/cookie.

Those errors are not Bean Validation errors. For example, `"age":"many"` failing to convert to `int age` is a decoding/conversion error; whereas `"age":12` deserializes successfully but violates the minimum age rule of 18.

Spring WebFlux has exceptions related to request input such as `ServerWebInputException`, exceptions following the `ErrorResponse` contract, and codec errors. The exact exception class depends on the stage and cause; do not assume every JSON parse error is the exact same class. Built-in exceptions can supply the HTTP status and information for RFC 9457.

## 5. Bean Validation for DTOs and method parameters

### 5.1. Validation on a request object

Use Jakarta Bean Validation annotations on the DTO:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateAccountRequest(
        @NotBlank(message = "name must not be blank")
        @Size(max = 80, message = "name must be at most 80 characters")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email must be valid")
        @Size(max = 254, message = "email must be at most 254 characters")
        String email,

        @Min(value = 18, message = "age must be at least 18")
        @Max(value = 120, message = "age must be at most 120")
        int age
) {}
```

Then use `@Valid`:

```java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @Valid @RequestBody Mono<CreateAccountRequest> body) {

    return body.map(this::toResponse);
}
```

In WebFlux, validation can apply to `@RequestBody` with a reactive wrapper such as `Mono<CreateAccountRequest>`. When the object is read and validation fails, Spring raises `WebExchangeBindException`; the error can be handled in the controller or centralized in an advice.

### 5.2. Direct validation on method parameters

Constraints can be placed directly on query parameters or headers:

```java
@GetMapping("/accounts/by-age")
public Mono<String> byAge(
        @RequestParam("age")
        @Min(18) @Max(120) int age) {

    return Mono.just("accepted age=" + age);
}
```

With the built-in method validation mechanism since **Spring Framework 6.1**, direct constraints on method parameters cause Spring to validate the whole method. When input validation fails, the exception is `HandlerMethodValidationException`.

An easy mistake: `@Valid` **is not** a constraint annotation. `@Valid` asks to validate fields nested inside an object; on its own it does not trigger method validation. Constraints such as `@Min` and `@NotBlank` placed directly on parameters are what make method validation apply.

If a controller has `@Validated` at the class level to trigger method validation via AOP in the old way, behavior can differ. With Spring Framework 6.1+'s built-in method validation, omit class-level `@Validated` from the controller per Spring's guidance so the framework performs built-in method validation.

### 5.3. Two important validation exceptions

| Exception | When commonly seen | Error scope |
| --- | --- | --- |
| `WebExchangeBindException` | Validating an individual command object such as `@Valid @RequestBody` or `@ModelAttribute` | One object, with a `BindingResult` having field/global errors |
| `HandlerMethodValidationException` | Method validation caused by constraints placed directly on parameters or return values | Set of validation results grouped by method parameter |

An application should handle **both**, because the exception depends on the controller signature. `HandlerMethodValidationException` can also relate to return-value validation; in that case the status reflects a server-side error (usually 500), so do not force all cases to 400. Preserve the status provided by the exception when handling generically.

If `Errors`/`BindingResult` comes immediately after an object parameter, Spring can pass errors for the controller to handle itself. However, with `@RequestBody Mono<DTO>`, the body is read asynchronously; you cannot arbitrarily place a `BindingResult` immediately after the reactive wrapper the way you do with an eagerly resolved object. In the reactive body case, global advice or error operators are usually more suitable.

## 6. Standardizing errors with RFC 9457 Problem Details

RFC 9457 defines a standard format for HTTP API problem details. Spring Framework provides `ProblemDetail` and `ErrorResponse` to represent errors with status, headers, and body.

An error body usually has these fields:

| Field | Meaning |
| --- | --- |
| `type` | URI identifying the problem type; can be `about:blank` if there is no specific type |
| `title` | Short, stable name of the error type |
| `status` | HTTP status code |
| `detail` | Human-readable description of the specific error |
| `instance` | URI/path of the error occurrence |
| Extension properties | Extra fields, for example an `errors` list by field |

Example response:

```json
{
  "type": "about:blank",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "instance": "/api/accounts",
  "errors": [
    {
      "field": "email",
      "code": "Email",
      "message": "email must be valid"
    },
    {
      "field": "age",
      "code": "Min",
      "message": "age must be at least 18"
    }
  ]
}
```

Spring can render `ProblemDetail` with media type `application/problem+json`. Extension properties are added with `setProperty(...)`. Using a stable schema helps the frontend handle every error under the same contract, whether the source is binding, validation, or a business rule.

### 6.1. Choosing status codes by error kind

| Situation | Common status | Reason |
| --- | --- | --- |
| Missing required field, malformed JSON, failed type conversion | 400 Bad Request | Request does not satisfy input syntax/contract |
| Unauthenticated | 401 Unauthorized | Valid authentication is needed |
| Insufficient permissions | 403 Forbidden | Identified, but not permitted |
| Resource not found | 404 Not Found | Resource does not exist/is not exposed |
| Duplicate data or state conflict | 409 Conflict | Request is syntactically valid but conflicts with current state |
| Unsupported media type | 415 Unsupported Media Type | Content-Type is not supported by the endpoint |
| Too many requests | 429 Too Many Requests | Rate limit |
| Unexpected error | 500 Internal Server Error | Server-side error |

You can choose 422 Unprocessable Content for some APIs if the contract specifies it clearly, but do not mix 400 and 422 arbitrarily. What matters is that clients can predict statuses and error schemas across all endpoints.

## 7. Centralizing error handling with @RestControllerAdvice

### 7.1. Extracting field errors from WebExchangeBindException

The following advice example standardizes DTO validation errors. It does not return rejected values to avoid leaking sensitive data.

File `src/main/java/demo/ApiExceptionHandler.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ProblemDetail> handleBindingValidation(
            WebExchangeBindException exception) {

        List<ApiViolation> violations = new ArrayList<>();

        for (FieldError error : exception.getFieldErrors()) {
            violations.add(new ApiViolation(
                    error.getField(),
                    error.getCode() == null ? "invalid" : error.getCode(),
                    error.getDefaultMessage() == null
                            ? "Invalid value"
                            : error.getDefaultMessage()));
        }

        for (ObjectError error : exception.getGlobalErrors()) {
            violations.add(new ApiViolation(
                    "$",
                    error.getCode() == null ? "invalid" : error.getCode(),
                    error.getDefaultMessage() == null
                            ? "Invalid object"
                            : error.getDefaultMessage()));
        }

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid.");

        problem.setTitle("Request validation failed");
        problem.setProperty("errors", violations);

        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> handleMethodValidation(
            HandlerMethodValidationException exception) {

        HttpStatusCode status = exception.getStatusCode();
        boolean clientError = status.is4xxClientError();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                clientError
                        ? "One or more request parameters are invalid."
                        : "A server-side validation constraint failed.");

        problem.setTitle(clientError
                ? "Request validation failed"
                : "Response validation failed");

        return ResponseEntity.status(status).body(problem);
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ProblemDetail> handleInvalidInput(
            ServerWebInputException exception) {

        HttpStatusCode status = exception.getStatusCode();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                "The request contains missing or malformed input.");

        problem.setTitle("Invalid request input");

        return ResponseEntity.status(status).body(problem);
    }

    public record ApiViolation(
            String field,
            String code,
            String message) {
    }
}
```

This is a complete Java class for the three common error groups; a real application can add handlers for business exceptions. Imports are grouped by Spring/JDK package; if the IDE sorts imports automatically, keep the required types.

**Why does the method validation handler not force the status to 400?** `HandlerMethodValidationException` can represent an input parameter error or a return-value error. Keeping `exception.getStatusCode()` keeps request errors as 4xx while server-contract errors where the server produced an invalid response keep the server-side status.

### 7.2. Handling business errors

A business error should have its own exception so the advice maps it to the appropriate status:

```java
package demo;

public class DuplicateEmailException extends RuntimeException {
    public DuplicateEmailException() {
        super("An account with this email already exists.");
    }
}
```

Add to `ApiExceptionHandler`:

```java
@ExceptionHandler(DuplicateEmailException.class)
public ResponseEntity<ProblemDetail> handleDuplicateEmail(
        DuplicateEmailException exception) {

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "An account with this email already exists.");

    problem.setTitle("Account conflict");

    return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
}
```

This handler snippet needs to be placed **inside the ApiExceptionHandler class** in the example above. Do not put arbitrary database exception messages into the response. The message should be stable and not reveal constraint names, SQL, or other users' data.

### 7.3. When to use ResponseEntityExceptionHandler?

Spring provides `ResponseEntityExceptionHandler` as a base class for `@ControllerAdvice` to handle built-in WebFlux exceptions and RFC 9457 error responses. This is a suitable choice if you want broad customization across many framework error types such as method not allowed, unsupported media type, missing request value, and validation.

If you only need to standardize a few business/validation exceptions, specific `@ExceptionHandler` methods like in the example are enough. With Spring Boot, the `spring.webflux.problemdetails.enabled=true` property can enable Problem Details configuration for built-in exceptions. When overriding a built-in handler created by Boot, pay attention to `@ControllerAdvice` ordering per Boot/Spring documentation so the custom handler is chosen.

Do not write a catch-all `Exception.class` handler and turn every error into 400. Programming bugs, database unavailability, network errors, and configuration errors need 5xx statuses; only recognized input errors should return 4xx.

## 8. Combining reactive error operators without blocking

### 8.1. Errors in the pipeline are onError signals

When an exception arises inside an operator such as `map` or `flatMap`, Reactor turns it into an `onError` signal. You can convert the error type with `onErrorMap`:

```java
return accountRepository.save(account)
        .onErrorMap(
                DuplicateKeyException.class,
                error -> new DuplicateEmailException());
```

This is an **illustrative service snippet**. The repository must return a reactive publisher and DuplicateKeyException must be the actual driver exception type. The service converts the infrastructure exception into a business exception; the advice is responsible for mapping the business exception to HTTP 409.

### 8.2. Using onErrorResume for meaningful fallbacks

```java
return pricingService.findPrice(sku)
        .onErrorResume(PriceUnavailableException.class,
                error -> Mono.just(Price.unavailable()));
```

Use a fallback only when business rules allow returning a substitute result. Do not turn database errors into an empty list or validation errors into HTTP 200 just so the pipeline “does not report an error”.

### 8.3. Do not use try/catch around a publisher to catch errors thrown later

An insufficient example:

```java
try {
    return service.create(request);
} catch (Exception exception) {
    return Mono.error(exception);
}
```

This try/catch catches only exceptions thrown **immediately when calling the method and building the publisher**. Errors can happen later, when the publisher is subscribed to and executed. Use reactive operators instead:

```java
return service.create(request)
        .onErrorMap(DuplicateKeyException.class,
                error -> new DuplicateEmailException());
```

You can use `Mono.defer(...)` if you need to defer even the method call so that exceptions thrown on subscribe are turned into onError. However, with a service that returns a publisher adhering to the contract, there is no need to wrap with `defer` mechanically.

### 8.4. Combining asynchronous business validation

Bean Validation fits local, fast, deterministic conditions such as not blank, range, and format. When you need to check a database or external service, return a publisher:

```java
public Mono<AccountResponse> create(CreateAccountRequest request) {
    return accountRepository.existsByEmail(request.email())
            .flatMap(exists -> {
                if (exists) {
                    return Mono.error(new DuplicateEmailException());
                }

                return accountRepository.save(toEntity(request))
                        .map(this::toResponse);
            });
}
```

This is **illustrative service code** with a reactive repository. Checking existence and then inserting can hit a race condition when two concurrent requests share the same email. The database still needs a unique constraint and the service needs to map unique-key errors to `DuplicateEmailException`. Pre-checking does not replace data integrity.

Do not write:

```java
boolean exists = accountRepository.existsByEmail(email).block();
```

This is a design flaw in WebFlux because it blocks the thread handling the reactive flow. Also do not call `subscribe()` manually inside a service to “run the check ahead of time” and then return a response; that detaches the task from the request and breaks cancellation/error linkage.

## 9. Why must you not block when handling errors?

### 9.1. The Netty event loop must stay free

WebFlux usually uses an event loop to handle many connections. If a controller or exception handler calls `block()`, `Future.get()`, `Thread.sleep()`, or a blocking SDK, the thread can be forced to wait while other requests also need it.

An input error that could have returned a response quickly becomes the cause of increased latency for many other requests. Exception handlers must also stay non-blocking; do not query the database synchronously to build error content.

### 9.2. Returning a publisher instead of subscribing manually

Correct:

```java
@PostMapping("/accounts")
public Mono<ResponseEntity<AccountResponse>> create(
        @Valid @RequestBody Mono<CreateAccountRequest> body) {

    return body.flatMap(accountService::create)
            .map(saved -> ResponseEntity
                    .status(HttpStatus.CREATED)
                    .body(saved));
}
```

Spring WebFlux subscribes to and manages the lifecycle of the returned publisher. If an error occurs during body decoding, validation, or the service, the framework/advice handles it according to the HTTP contract.

Wrong:

```java
@PostMapping("/accounts")
public Mono<String> create(
        @RequestBody Mono<CreateAccountRequest> body) {

    body.subscribe(accountService::create);
    return Mono.just("accepted");
}
```

The snippet above is wrong in both return style and lifecycle: a nested `subscribe` can create a detached subscription, does not wait for work to finish, does not put errors into the response, and does not link cancellation to the HTTP request. Always compose the publisher and return it.

### 9.3. If you must call a blocking library

Prefer reactive drivers/clients. If you must use a legacy blocking library, isolate only that part:

```java
return Mono.fromCallable(() -> legacyClient.lookup(key))
        .subscribeOn(Schedulers.boundedElastic());
```

This is an illustrative bridge. It offloads the blocking task to an appropriate scheduler; it **does not turn the library into a non-blocking one**. Keep separate timeouts, concurrency limits, and connection limits. If the work can be canceled, check whether the driver genuinely supports cancel/interrupt.

## 10. Complete Spring Boot WebFlux example

This example builds an account creation endpoint, applies validation to a JSON body, validates a query parameter, and returns a unified error body for the selected errors.

### 10.1. Dependencies

The example uses Java 17+, Spring Boot 3.2+ (Spring Framework 6.1+), and Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Assumes the project already has the Spring Boot Gradle plugin and dependency management configured. Let the BOM manage versions of Spring Framework, Reactor, Hibernate Validator, and test libraries.

### 10.2. DTO and response

File `src/main/java/demo/CreateAccountRequest.java`:

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateAccountRequest(
        @NotBlank(message = "name must not be blank")
        @Size(max = 80, message = "name must be at most 80 characters")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email must be valid")
        @Size(max = 254, message = "email must be at most 254 characters")
        String email,

        @Min(value = 18, message = "age must be at least 18")
        @Max(value = 120, message = "age must be at most 120")
        int age
) {}
```

File `src/main/java/demo/AccountResponse.java`:

```java
package demo;

public record AccountResponse(
        String id,
        String name,
        String email,
        int age
) {}
```

### 10.3. Controller

File `src/main/java/demo/AccountController.java`:

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    @PostMapping
    public Mono<ResponseEntity<AccountResponse>> create(
            @Valid @RequestBody Mono<CreateAccountRequest> body) {

        return body
                .map(request -> new AccountResponse(
                        "acct-001",
                        request.name(),
                        request.email(),
                        request.age()))
                .map(response -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(response));
    }

    @GetMapping("/by-age")
    public Mono<String> byAge(
            @RequestParam("age")
            @Min(18) @Max(120) int age) {

        return Mono.just("accepted age=" + age);
    }
}
```

The controller does not call `block()` or `subscribe()`. `@Valid` applies Bean Validation to the body; `@Min/@Max` on the age parameter triggers Spring Framework 6.1+'s built-in method validation. Do not place class-level `@Validated` on the controller in this example.

### 10.4. Error-handling advice

File `src/main/java/demo/ApiExceptionHandler.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ProblemDetail> handleBodyValidation(
            WebExchangeBindException exception) {

        List<ApiViolation> errors = new ArrayList<>();

        for (FieldError error : exception.getFieldErrors()) {
            errors.add(new ApiViolation(
                    error.getField(),
                    error.getCode() == null ? "invalid" : error.getCode(),
                    error.getDefaultMessage() == null
                            ? "Invalid value"
                            : error.getDefaultMessage()));
        }

        for (ObjectError error : exception.getGlobalErrors()) {
            errors.add(new ApiViolation(
                    "$",
                    error.getCode() == null ? "invalid" : error.getCode(),
                    error.getDefaultMessage() == null
                            ? "Invalid object"
                            : error.getDefaultMessage()));
        }

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid.");

        problem.setTitle("Request validation failed");
        problem.setProperty("errors", errors);

        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> handleMethodValidation(
            HandlerMethodValidationException exception) {

        HttpStatusCode status = exception.getStatusCode();
        boolean clientError = status.is4xxClientError();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                clientError
                        ? "One or more request parameters are invalid."
                        : "A server-side validation constraint failed.");

        problem.setTitle(clientError
                ? "Request validation failed"
                : "Response validation failed");

        return ResponseEntity.status(status).body(problem);
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ProblemDetail> handleInvalidInput(
            ServerWebInputException exception) {

        HttpStatusCode status = exception.getStatusCode();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                "The request contains missing or malformed input.");

        problem.setTitle("Invalid request input");

        return ResponseEntity.status(status).body(problem);
    }

    public record ApiViolation(
            String field,
            String code,
            String message) {
    }
}
```

Specific handlers avoid turning every exception into an input error. Other WebFlux exceptions can be handled by the built-in mechanism or an advice class extending `ResponseEntityExceptionHandler` if the API needs to customize the entire framework exception set.

### 10.5. Calling the endpoint and checking results

Start the application (once you have the main Spring Boot class and appropriate package scanning):

```bash
./gradlew bootRun
```

Send a valid request:

```bash
curl -i -X POST http://localhost:8080/api/accounts   -H "Content-Type: application/json"   -d '{"name":"An","email":"an@example.com","age":25}'
```

Expected response:

```json
{
  "id": "acct-001",
  "name": "An",
  "email": "an@example.com",
  "age": 25
}
```

Status is `201 Created`.

Send an invalid body:

```bash
curl -i -X POST http://localhost:8080/api/accounts   -H "Content-Type: application/json"   -d '{"name":"","email":"not-an-email","age":15}'
```

The response is HTTP 400 with a Problem Details body; the `errors` field contains violations such as name, email, and age. The order of field errors can depend on the validator, so clients/tests should not depend on array ordering.

Send an out-of-range query parameter:

```bash
curl -i "http://localhost:8080/api/accounts/by-age?age=15"
```

Method validation raises `HandlerMethodValidationException`; the advice returns HTTP 400 and a consistent title. If a constraint on a return value fails, Spring may supply status 500; the handler preserves that status so server bugs are not described as client errors.

Send an unconvertible query parameter:

```bash
curl -i "http://localhost:8080/api/accounts/by-age?age=abc"
```

This is a type conversion error before method validation runs. It is not the same as age=15 converting successfully and then violating `@Min(18)`.

## 11. Testing errors with WebTestClient

Test the HTTP contract instead of only calling the validator directly. `WebTestClient` can test the controller without opening a real server.

File `src/test/java/demo/AccountControllerTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(AccountController.class)
@Import(ApiExceptionHandler.class)
class AccountControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void validBodyReturnsCreated() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "An",
                          "email": "an@example.com",
                          "age": 25
                        }
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo("acct-001")
                .jsonPath("$.name").isEqualTo("An");
    }

    @Test
    void invalidBodyReturnsProblemDetails() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "",
                          "email": "not-an-email",
                          "age": 15
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.title")
                    .isEqualTo("Request validation failed")
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.errors").isArray();
    }

    @Test
    void methodParameterValidationReturnsProblemDetails() {
        client.get()
                .uri("/api/accounts/by-age?age=15")
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.title")
                    .isEqualTo("Request validation failed")
                .jsonPath("$.status").isEqualTo(400);
    }

    @Test
    void invalidIntegerConversionIsBadRequest() {
        client.get()
                .uri("/api/accounts/by-age?age=abc")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

Run tests:

```bash
./gradlew test
```

The `spring-boot-starter-test` dependency provides JUnit Jupiter and WebFlux test support; `spring-boot-starter-validation` puts the Bean Validation provider on the classpath. Use Spring Boot's dependency management to select compatible versions.

Tests focus on important contracts: valid requests return 201; invalid DTOs return 400 with an error body; method constraints return 400; conversion errors return 400. If the project has Spring Security, add appropriate test configuration or mock a principal to test error handling within the right security chain.

## 12. Localizing messages and keeping the error schema stable

Validation messages can be written directly in annotations, but multilingual APIs should use a message bundle:

```java
@NotBlank(message = "{account.name.required}")
@Size(max = 80, message = "{account.name.max}")
String name
```

Example in `messages.properties`:

```properties
account.name.required=Name is required.
account.name.max=Name must be at most 80 characters.
account.email.invalid=Email address is invalid.
```

You can create locale-specific files, for example `messages_vi.properties`. Spring uses `MessageSource` to resolve message codes. For exceptions implementing `ErrorResponse`, Spring also supports message codes for ProblemDetail fields.

When returning errors, keep a stable structure:

- `field`: field/parameter name per the API contract.
- `code`: stable error code for clients to handle logic.
- `message`: localizable message for users to read.

Do not force clients to parse free-form prose sentences to decide behavior. Also do not change error codes arbitrarily between deployments if the frontend depends on them.

## 13. Validation in controller, service, and database

Each layer has its own responsibility:

| Layer | Appropriate checks | Example |
| --- | --- | --- |
| HTTP binding | Can the data be read and converted? | Valid JSON, query int, required header |
| Bean Validation | Do field structures/values satisfy local constraints? | NotBlank, Email, Size, Min |
| Service/domain | Rules depending on business logic or multiple objects | Account not locked, state allows change |
| Database | Final constraint protecting data under concurrency | Unique key, foreign key, check constraint |

Do not put every piece of logic into Bean Validation. `ConstraintValidator` runs synchronously; calling remote services/databases from a validator can block threads and make timeouts and retries hard to manage. If you need an asynchronous check, have the service return `Mono<Boolean>`/a publisher and compose with `flatMap`.

Conversely, do not rely only on the controller to protect invariants. Two concurrent requests can both pass an “existence check” and then both insert. Database constraints are still necessary; the service translates constraint errors into a business exception with status 409.

## 14. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating every request error as 500 | Client does not know where the error is | Classify binding, conversion, validation, business, and server errors |
| Handling only WebExchangeBindException | Misses method validation | Also handle HandlerMethodValidationException |
| Forcing every HandlerMethodValidationException to 400 | Server-side return-value validation is misclassified | Preserve status from the exception |
| Thinking @Valid always triggers method validation | Confuses nested object validation with method constraints | Distinguish @Valid from constraint annotations like @Min/@NotBlank |
| Using class-level @Validated and forgetting Spring 6.1 built-in validation | May use AOP method validation under a different mechanism | For built-in method validation, omit class-level @Validated on the controller |
| Returning rejected values or the full exception message | Can leak emails, tokens, SQL, or internal data | Return only selected field, code, and message |
| Using one catch-all and returning 400 | Hides bugs and infrastructure errors as client errors | Map each specific exception; keep 5xx for server errors |
| Calling block in controller/advice | Blocks the event loop and increases latency | Compose Mono/Flux; keep error response in the reactive chain |
| Calling subscribe in service | Detaches work from HTTP lifecycle, errors, and cancellation | Return the publisher to the caller |
| Using try/catch to catch errors raised on subscribe | Misses asynchronous errors | Use onErrorMap/onErrorResume/doOnError |
| Calling the database from a ConstraintValidator | Synchronous validator can block the event loop | Check business rules in a reactive service |
| Turning errors into Mono.empty() unconditionally | Client can receive 200/204 as if successful | Fallback only when the business contract permits |
| Returning stack traces in ProblemDetail | Leaks internal information | Log internally, return safe details |
| Ignoring race conditions after an exists check | Data can still duplicate under concurrency | Use unique constraints and map DB errors |
| Catching Throwable to handle request errors | Can swallow serious errors and confuse cancellation | Handle specific exceptions; cancellation is not onError |

## 15. Error-handling design checklist

When adding a new endpoint, follow this sequence:

1. **Define the input contract:** which fields are required, what types, what limits, can the body be empty?
2. **Choose binding:** DTO for body, annotations for query/header/path, reactive wrapper for body if streaming is needed.
3. **Add local Bean Validation:** NotBlank, Size, Email, Min/Max, and business-appropriate constraints without performing blocking I/O.
4. **Identify exception types:** object binding, method validation, conversion, decode, business conflict, or infrastructure.
5. **Choose status:** 400 for invalid input, 409 for conflict, 415 for media type, 5xx for server errors.
6. **Standardize the body:** RFC 9457 ProblemDetail, field errors with stable codes, no rejected secrets.
7. **Keep the reactive lifecycle:** return Mono/Flux, compose with map/flatMap/onErrorMap/onErrorResume, do not block/subscribe manually.
8. **Handle async business checks:** use reactive repositories/clients and timeouts; the database still keeps constraints against races.
9. **Test:** valid, missing, malformed, type mismatch, bean validation, method validation, business conflict, and unexpected errors.
10. **Observe in production:** log correlation ID, status, error code, and latency; do not log secret payloads or stack traces in responses.

## 16. Official references

- [Spring Framework – WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): two levels of validation, WebExchangeBindException, HandlerMethodValidationException, and visitor API.
- [Spring Framework – WebFlux Error Responses](https://docs.spring.io/spring/reference/web/webflux/ann-rest-exceptions.html): ProblemDetail, ErrorResponse, ResponseEntityExceptionHandler, RFC 9457, and message codes.
- [Spring Framework – WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): validation for reactive request bodies and error handling.
- [Spring Framework – WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): registering a global Validator and validation configuration.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standard format for HTTP problem responses.
- [Project Reactor Reference – Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): onError, onErrorMap, onErrorResume, and error-handling operators.

## 17. Key takeaways

A good WebFlux API classifies errors before standardizing the response: **binding/conversion** for unreadable or unconvertible data; **Bean Validation** for objects violating constraints; **method validation** for constraints on parameters/return values; **business validation** for business rules; and **server errors** for unexpected failures.

With Spring Framework 6.1+, remember to handle both `WebExchangeBindException` and `HandlerMethodValidationException`. Use `@RestControllerAdvice` and `ProblemDetail` to keep status/schema consistent without exposing internal data. Local checks can run synchronously during the validation step; any business-dependent I/O should be composed with `Mono/Flux`. Return publishers for WebFlux to manage, and do not call `block()` or `subscribe()` in controllers/services so the request lifecycle and error propagation stay intact.
