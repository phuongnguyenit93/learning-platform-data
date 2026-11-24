# ResponseStatusException, @ResponseStatus, and Choosing HTTP Status Codes

When a Spring Boot API cannot fulfill a request as expected, the **HTTP status code is part of the communication contract**: it tells clients whether the request is valid, whether the user is authorized, whether the resource exists, whether business state conflicts, or whether the server is temporarily overloaded. Choosing the wrong status causes clients to retry inappropriately, display misleading messages, or mix errors with successful responses.

In Spring Framework 6 / Spring Boot 3.3, common ways to express status include **`ResponseStatusException`**, the **`@ResponseStatus`** annotation on a method or exception class, and **`ResponseEntity`** alongside `@ExceptionHandler`/`@RestControllerAdvice` when a stable response body is required. Each serves a different role; no single tool is best for every case.

This lesson belongs to the **Error Handling** group of **Spring Boot - web-runtime**, focusing on status selection and exception flow in **Spring MVC/Servlet**. At the end, it compares with WebFlux, provides a Spring Boot 3.3.13 + Java 21 + Gradle example, and includes MockMvc tests. Examples use the `jakarta.*` namespace compatible with Spring Boot 3.

## 1. HTTP Status, Exception, and Error Body Are Three Separate Things

Example of an HTTP response:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Resource not found"
}
~~~

Distinctions:

- **Status**: a number such as 404 or 409 in the HTTP response status line, used by clients, proxies, monitoring, and retry logic.
- **Exception**: a Java object used for control flow inside the application; exception names do not have to map 1:1 to statuses.
- **Body**: error description data for the client, which may be `ProblemDetail`, JSON matching an organization's schema, or an HTML page. Status **does not automatically guarantee a JSON body**.

A well-designed API decides both the **HTTP status** and the **error representation**. Throwing `new ResponseStatusException(HttpStatus.NOT_FOUND)` is enough to target status 404, but **does not mean the body is guaranteed to be a JSON object with every key you expect**. The body depends on Spring MVC exception resolvers, Spring Boot error handling, Problem Details configuration, content negotiation, and the request's actual path.

Similarly, a controller returning JSON with `"status":404` while the real HTTP status is 200 is a poor contract: clients and proxies still treat it as HTTP 200 unless special handling exists. Always use the accurate HTTP status at the protocol layer.

## 2. Status Code Families: 2xx, 3xx, 4xx, 5xx

| Code Range | General Meaning | Notes |
| --- | --- | --- |
| **2xx** | Request processed successfully per the code's semantics | 200, 201, 202, 204 |
| **3xx** | Redirect or representation/cache conditions | 301, 302, 303, 304, 307, 308 |
| **4xx** | Request cannot be served due to client/request/authorization/state conditions | 400, 401, 403, 404, 405, 409, 415, 422, 429 |
| **5xx** | Server or an upstream component failed to process the request | 500, 502, 503, 504 |

Do not lump every business error into 500. If an ID is valid but the record does not exist, 404 fits better than 500. If a user sends malformed JSON, 400 is usually more appropriate than 500.

Conversely, do not turn an unexpected database failure into 400 just to avoid alerts. Unforeseen errors without dedicated handling rules should generally be classified as 500 and logged appropriately for operations.

**Do not automatically retry every 5xx and do not retry every 429 by default.** Retrying must account for operation type, `Retry-After`, deadlines, idempotency, jitter/backoff, and potential task conflicts.

## 3. Common HTTP Status Selection Table

| Code | Name | When to Consider | Common Pitfalls |
| --- | --- | --- | --- |
| **200** | OK | Successful GET, or POST that executes and returns a normal result | Do not return 200 with an error body pretending HTTP succeeded |
| **201** | Created | Resource was created, usually with `Location` | Do not use 201 if merely accepted into a queue |
| **202** | Accepted | Request accepted for later processing, not yet complete | Needs a status-tracking mechanism if genuinely async |
| **204** | No Content | Succeeded and no response body is needed | 204 carries no message body |
| **400** | Bad Request | Invalid input, malformed body, failed validation, or bad query | Distinguish from 422 according to API policy |
| **401** | Unauthorized | Missing or invalid authentication credentials | Typically Security layer; `WWW-Authenticate` header matters |
| **403** | Forbidden | Request is identified/authenticated, but not permitted | Do not replace authorization with ad-hoc checks in controllers |
| **404** | Not Found | Route/resource missing, or resource existence intentionally hidden | Do not default to 500 |
| **405** | Method Not Allowed | Path exists, but HTTP method is unsupported | Framework may generate `Allow` header |
| **406** | Not Acceptable | Cannot produce a representation matching `Accept` | Usually tied to content negotiation |
| **409** | Conflict | Request conflicts with current state of resource/system | Duplicate unique value or version conflict per policy |
| **410** | Gone | Resource once existed and was permanently removed per server knowledge | Not every missing ID is 410 |
| **412** | Precondition Failed | `If-Match`/`If-Unmodified-Since` condition not met | Important for HTTP optimistic concurrency |
| **415** | Unsupported Media Type | Request `Content-Type` or payload format is unsupported | Different from 406; applies to request content |
| **422** | Unprocessable Content | Payload is syntactically valid, but semantic rules cannot be processed | Not mandatory for all Bean Validation 400 errors |
| **429** | Too Many Requests | Rate/quota limit exceeded per policy | Consider `Retry-After` and limit details |
| **500** | Internal Server Error | Unexpected server error | Never expose stack traces or SQL secrets |
| **502** | Bad Gateway | Gateway/proxy received invalid upstream response | Not normally emitted by a controller |
| **503** | Service Unavailable | Server temporarily unable to serve due to overload/maintenance | Can include `Retry-After` |
| **504** | Gateway Timeout | Gateway/proxy did not receive timely upstream response | Distinct from all internal service timeouts |

`HttpStatus` is Spring's enum of common HTTP codes. Spring Framework 6 also provides `HttpStatusCode` to represent status codes as an interface, and `HttpStatusCode.valueOf(int)` when a numeric code is needed. Never invent nonstandard codes without a clear contract.

### 3.1. Three Commonly Confused Pairs

**400 vs. 422:** Malformed JSON or missing required data is usually returned as 400 by Spring MVC's default binding/validation path. 422 can be used by policy when JSON is valid yet a business rule cannot be satisfied. There is no law requiring every validation failure to be 422.

**401 vs. 403:** 401 means authentication is incomplete/invalid; 403 means permission is denied. For OAuth2/Bearer tokens, Spring Security and the authentication entry point typically emit 401 with scheme-appropriate headers; the access denied handler emits 403. Controllers should not emit statuses manually without required security headers when Security manages them.

**404 vs. 410:** 404 makes no claim as to whether a resource ever existed or was permanently deleted. Use 410 only when the application has sufficient information and contract semantics to confirm the resource is permanently gone.

## 4. ResponseStatusException: Choosing Status at Runtime

Full class name:

~~~java
org.springframework.web.server.ResponseStatusException
~~~

Despite `web.server` in its package, Spring Framework supports this exception in **both Spring MVC and WebFlux**.

Inside a controller/service adapter:

~~~java
if (id <= 0) {
    throw new ResponseStatusException(
        HttpStatus.BAD_REQUEST,
        "id must be positive"
    );
}

if (!repository.existsById(id)) {
    throw new ResponseStatusException(
        HttpStatus.NOT_FOUND,
        "resource not found"
    );
}
~~~

This is a **code fragment** assuming `id` and `repository` exist. The status is decided **dynamically**, based on request data and processing outcomes.

Spring 6.1 constructors:

~~~java
new ResponseStatusException(HttpStatus.NOT_FOUND);
new ResponseStatusException(HttpStatus.NOT_FOUND, "book not found");
new ResponseStatusException(
    HttpStatus.BAD_REQUEST,
    "input invalid",
    cause
);
~~~

`cause` is an existing `Throwable`. Pass a sensible cause only to preserve internal diagnostics; never send SQL causes, credentials, or sensitive exception messages to clients.

### 4.1. ResponseStatusException Extends ErrorResponseException

In Spring 6.1, `ResponseStatusException` extends `ErrorResponseException` and implements `ErrorResponse`. It carries status, headers, and a `ProblemDetail` body at the abstraction level. The exception's `reason` is typically mapped by default to `ProblemDetail`'s `detail`.

**However, `exception.getBody()` and the actual JSON over HTTP are not always identical**: which resolver handles the exception, whether Boot enables Problem Details, whether a custom `@ControllerAdvice` exists, and whether the response is committed all affect the result. Never write a client contract assuming “throwing the exception guarantees the JSON body always contains reason”.

### 4.2. Example in WebFlux Mono/Flux

In a reactive chain, errors should be emitted through the publisher:

~~~java
return service.findBook(id)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(
            HttpStatus.NOT_FOUND,
            "book not found"
        )
    ));
~~~

This is a WebFlux fragment assuming `service.findBook(id)` returns `Mono<Book>`. Never call `subscribe()` or `block()` just to convert an exception into an HTTP response.

**Committed responses:** if a stream has already written headers/body before emitting an error, the earlier status cannot be retroactively changed to 404 or 500. Clients must understand streaming protocols, and the server must clean up resources.

## 5. @ResponseStatus on Controller Methods: Static Status

Example:

~~~java
@PostMapping("/validate-only")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void validateOnly(@Valid @RequestBody CheckRequest request) {
    // Only checks conditions; no response body returned.
}
~~~

The status value is fixed and attached directly to the method. For a successful `void` method, 204 clearly signals **no body**. If the method throws an exception, the error status can come from exception handling instead of 204.

You can write:

~~~java
@ResponseStatus(code = HttpStatus.CREATED)
@PostMapping("/items")
public ItemView create(@RequestBody CreateItem input) { ... }
~~~

This is only an **illustrative fragment**; use 201 when the resource **has actually been created**, and `Location` should be constructed appropriately. If different branches need different statuses/headers or `Location`, `ResponseEntity` usually expresses the contract better.

### 5.1. Do Not Add @ResponseStatus to Every Method Reflexively

- For `@RestController` returning a normal DTO, 200 is the common default.
- For POST creating a resource, 201 is reasonable once persisted.
- For an operation completing with no body, 204 is appropriate.
- For a request **accepted for async processing** in a real queue, 202 fits.
- For failure branches, throwing an exception with a clear status is better than pretending to return a success DTO.

The annotation fixes **one** status per method or exception class. If the same method may return 200, 201, or 409 depending on runtime outcomes, use `ResponseEntity`/exception handling instead of forcing one status for all cases.

### 5.2. @ResponseStatus on a Controller Class Can Affect the Entire Class

The annotation can also be placed on a class; the status can apply to request-mapping/exception-handler methods unless overridden at the method level. This easily causes surprises when a class hosts routes with different semantics. In REST controllers mixing GET/POST/DELETE, prefer placing status **on specific methods** rather than class-wide.

## 6. @ResponseStatus on Exception Classes: Fixed Mapping

Example of a business exception with an unchanging status:

~~~java
@ResponseStatus(HttpStatus.GONE)
public class RetiredResourceException extends RuntimeException {
    public RetiredResourceException() {
        super("Resource is retired");
    }
}
~~~

When this exception is not caught/transformed by another advice, `ResponseStatusExceptionResolver` can convert it into 410 Gone. Advantage: the status is tied to the **exception type**, not each throw site.

Drawback: the domain exception becomes coupled to HTTP semantics. If the domain layer is reused in batch jobs, messaging, CLIs, or standalone libraries, adding web annotations to shared exceptions may be undesirable. A `@RestControllerAdvice` can map domain exceptions to HTTP contracts at the web layer without making domain code aware of `HttpStatus`.

### 6.1. Be Especially Careful with reason in @ResponseStatus

Example to avoid in REST APIs:

~~~java
@ResponseStatus(
    code = HttpStatus.NOT_FOUND,
    reason = "Book not found"
)
public class BookMissingException extends RuntimeException {
}
~~~

Per Spring Framework 6.1 Javadoc, with **the annotation on an exception class** or a **non-empty `reason`**, Spring MVC may call `HttpServletResponse.sendError(...)`. After `sendError`, the response is considered complete for that handling path; the Servlet container or Boot error dispatch may produce **a default HTML page or default JSON error**, rather than the body your controller intended to serialize.

Therefore, if your API must reliably return a consistent JSON problem document, do not rely on the annotation's `reason`. Use `@ExceptionHandler` returning `ProblemDetail` or `ResponseEntity` with tested content type/fields.

**Key distinction:** `@ResponseStatus(HttpStatus.NO_CONTENT)` on a successful method without `reason` works normally with a return value; adding a non-empty `reason` can cause the return body to be ignored due to `sendError`.

## 7. @ResponseStatus vs. ResponseStatusException vs. ResponseEntity

| Approach | Status Selection | Body/Schema | Best When |
| --- | --- | --- | --- |
| `@ResponseStatus` on method | Fixed per method | Normal return handling when no special reason is set | Fixed 201/202/204 with clear semantics |
| `@ResponseStatus` on exception | Fixed per exception class | May pass through `sendError`/Boot error path | A very specific exception always has an invariant status |
| `ResponseStatusException` | Chosen at runtime per branch | Body not guaranteed consistent without handler/config design | Simple runtime conditions like 400/404 |
| `ResponseEntity<T>` | Chosen per response | Controls status, headers, and body | 201 + Location, 204, 200 with headers, multiple branches |
| `@RestControllerAdvice` + `@ExceptionHandler` | Chosen per exception/domain mapping | Controls shared schema, ProblemDetail, localization | API needs consistent error contract across controllers |

Recommended choices for common situations:

- **Validation-only command returning 204**: `@ResponseStatus(NO_CONTENT)` on the method is simple and clear.
- **Resource not found by ID**: `ResponseStatusException(NOT_FOUND)` can suffice when no custom error body is required.
- **Resource creation**: `ResponseEntity.created(location).body(dto)` accurately conveys 201/Location/body.
- **Business conflict with stable error code**: domain exception + `@RestControllerAdvice` producing `ProblemDetail`.
- **Spring Security 401/403**: configure Security entry point/access denied handler rather than throwing ad-hoc exceptions in controllers.

### 7.1. ResponseEntity Can Explicitly Define Status and Headers

~~~java
return ResponseEntity
    .created(URI.create("/api/books/42"))
    .body(new BookView(42L, "Java 21"));
~~~

This is a code fragment inside a method returning `ResponseEntity<BookView>`, used when a resource is actually created. Here `Location` is a relative URI; for public APIs requiring an absolute URI, use a URL builder aware of context path and trusted forwarded headers rather than hardcoding localhost or internal hosts.

Without a body:

~~~java
return ResponseEntity.noContent().build();
~~~

No `@ResponseStatus` is needed. If code combines `@ResponseStatus` with returning `ResponseEntity`, the framework applies precedence rules; avoid redundant configuration that confuses reviewers.

## 8. How Exceptions Travel Through Spring MVC

Simplified flow when a controller or binding fails:

~~~text
HTTP request
     |
     v
DispatcherServlet / HandlerAdapter
     |
     +-- request mapping / binding / validation
     |      |
     |      +-- may throw framework exception
     |
     +-- controller / service
            |
            +-- may throw custom exception
            |
            v
HandlerExceptionResolver chain
     |
     +-- ExceptionHandlerExceptionResolver
     |      -> @ExceptionHandler on controller / @ControllerAdvice
     |
     +-- ResponseStatusExceptionResolver
     |      -> @ResponseStatus / ResponseStatusException
     |
     +-- DefaultHandlerExceptionResolver
            -> default Spring MVC errors
     |
     v
HTTP status + headers + body or error dispatch
~~~

This is a **conceptual diagram of the default mechanism**, not an invariant ordering guarantee for custom resolvers; resolver beans have `Ordered`, individual configs, and composition rules. If a matching `@ExceptionHandler` catches the exception and returns a response, it determines the final status—annotations on the exception are not an “immutable decree” overriding every resolver.

Some errors are handled by Spring before reaching a controller:

- No matching mapping → usually 404.
- Path exists, wrong method → usually 405.
- Incompatible `Content-Type` → 415.
- Unsatisfiable `Accept` → 406.
- JSON parse failure, missing required body, or failed validation → usually 400.
- Authentication/authorization failures may be handled by the **Spring Security filter chain** before MVC.

**Do not throw `ResponseStatusException` for framework errors Spring already identifies accurately.** Add handlers only when you need custom bodies, logging, or policies; preserve accurate statuses and required HTTP headers.

## 9. Using ProblemDetail to Standardize Error Bodies

Spring Framework 6 supports `org.springframework.http.ProblemDetail` and `org.springframework.web.ErrorResponse` for RFC 9457 error representations. Common standard fields:

| Field | Role |
| --- | --- |
| `type` | URI identifying the problem type; defaults to `about:blank` |
| `title` | Short name describing the error class |
| `status` | HTTP status number in the problem document |
| `detail` | Client-facing explanation of the error (no secret leaks) |
| `instance` | URI identifying the specific error occurrence if provided by app |

Sample body:

~~~json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "A book with this title already exists",
  "code": "TITLE_ALREADY_EXISTS"
}
~~~

`code` is an **application-specific extension property**, not a mandatory RFC field. Spring supports adding properties via `ProblemDetail.setProperty(...)`; Jackson integration writes extension properties at the top level.

### 9.1. Do Not Rely on Default JSON Errors for a Strict Contract

In Spring Boot 3.3, the property:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

enables Problem Details auto-configuration for supported MVC exceptions. However, depending on configuration, custom `@ControllerAdvice` beans, `@ResponseStatus` exceptions, and error dispatch paths, fields and formatting may vary. **Do not assume every error becomes a ProblemDetail simply by enabling the property.**

If an organization requires a unified error schema, write appropriate exception handlers/`ResponseEntityExceptionHandler`, define clear precedence, and test every supported error case.

### 9.2. Unexpected Errors Must Not Expose Details

Never place raw `SQLException` messages, stack traces, absolute file paths, SQL queries, tokens, other users' data, or infrastructure details in `ProblemDetail.detail`. Use client-safe messages, stable error codes, and correlation IDs to support investigations in server logs.

`ProblemDetail.status` must match the actual HTTP status. If the body says 409 while the HTTP status line says 200, clients and proxies receive conflicting signals.

## 10. Runnable Example: Spring Boot MVC + Three Ways to Choose Status

The demo below includes:

1. `ResponseStatusException` returning 400 for an invalid ID, 404 when the ID does not exist.
2. `@ResponseStatus(HttpStatus.GONE)` on an exception class returning 410 when a resource is retired.
3. `@ResponseStatus(NO_CONTENT)` on a validation-only POST method returning 204.
4. `@RestControllerAdvice` returning 409 + `ProblemDetail` when a title conflicts.
5. MockMvc tests verifying statuses and JSON schema for the advice case.

The demo project uses no database and creates no real resources; data branches are intentionally simulated. Do not use this example to justify returning 201 Created without actually creating a resource.

~~~text
http-error-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/httperror/
    │   ├── HttpErrorDemoApplication.java
    │   ├── BookController.java
    │   ├── RetiredBookException.java
    │   ├── DuplicateTitleException.java
    │   └── ApiExceptionHandler.java
    └── test/java/com/example/httperror/
        └── BookControllerTest.java
~~~

### 10.1. Gradle Build and Entrypoint

**settings.gradle**

~~~groovy
rootProject.name = 'http-error-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/com/example/httperror/HttpErrorDemoApplication.java**

~~~java
package com.example.httperror;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpErrorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpErrorDemoApplication.class, args);
    }
}
~~~

`spring-boot-starter-web` provides embedded Tomcat/Spring MVC and Jackson JSON. `spring-boot-starter-validation` adds Jakarta Bean Validation. No standalone Tomcat installation is required.

### 10.2. Two Exception Classes in the Example

**src/main/java/com/example/httperror/RetiredBookException.java**

~~~java
package com.example.httperror;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.GONE)
public class RetiredBookException extends RuntimeException {
    public RetiredBookException() {
        super("This book is retired");
    }
}
~~~

The annotation declares only the status, **without setting `reason`**. Along the default handling path, the framework returns 410. Do not assume the error body has stable JSON keys.

**src/main/java/com/example/httperror/DuplicateTitleException.java**

~~~java
package com.example.httperror;

public class DuplicateTitleException extends RuntimeException {
    public DuplicateTitleException() {
        super("Book title already exists");
    }
}
~~~

The second exception **does not depend on Spring HTTP statuses**. The web adapter maps it to 409 and a consistent body inside `ApiExceptionHandler`.

### 10.3. Controller with Explicit Error Branches

**src/main/java/com/example/httperror/BookController.java**

~~~java
package com.example.httperror;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/books")
public class BookController {

    public record Book(long id, String title) {
    }

    public record TitleRequest(@NotBlank String title) {
    }

    @GetMapping("/{id}")
    public Book find(@PathVariable long id) {
        if (id <= 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "id must be positive"
            );
        }
        if (id != 1L) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "book not found"
            );
        }
        return new Book(1L, "Java 21");
    }

    @GetMapping("/retired")
    public Book retired() {
        throw new RetiredBookException();
    }

    @PostMapping(
        path = "/validate-only",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void validateOnly(@Valid @RequestBody TitleRequest input) {
        // Validate only; do not create or modify any record.
    }

    @PostMapping(
        path = "/check-title",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, Boolean> checkTitle(
            @Valid @RequestBody TitleRequest input) {
        // Simulate business state; no database used.
        if ("Java 21".equalsIgnoreCase(input.title())) {
            throw new DuplicateTitleException();
        }
        return Map.of("available", true);
    }
}
~~~

**Breakdown:**

- `GET /api/books/1` → 200, returns JSON from the `Book` record.
- `GET /api/books/0` → 400; invalid ID.
- `GET /api/books/9` → 404; not found in demo data.
- `GET /api/books/retired` → 410; exception class annotated with `@ResponseStatus(GONE)`.
- `POST /api/books/validate-only`, valid JSON body → 204, no response body.
- `POST /api/books/check-title` with a duplicate title in the demo → custom exception, handled by advice as 409.
- `POST /api/books/check-title` with a different title → 200 and JSON `{"available":true}`.
- Empty/whitespace or null title → `@NotBlank` validation typically yields 400.

Do not rely on an in-memory check like this example to enforce uniqueness in production: two concurrent requests can pass the check simultaneously. With real data, database unique constraints/transactions and race-aware exception mapping are required.

### 10.4. @RestControllerAdvice Returning ProblemDetail with a Stable Schema

**src/main/java/com/example/httperror/ApiExceptionHandler.java**

~~~java
package com.example.httperror;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(DuplicateTitleException.class)
    public ResponseEntity<ProblemDetail> duplicateTitle(
            DuplicateTitleException ex) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "A book with this title already exists"
        );
        problem.setTitle("Conflict");
        problem.setProperty("code", "TITLE_ALREADY_EXISTS");

        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
~~~

With `DuplicateTitleException`, the status is set on both the **actual HTTP response** (`ResponseEntity.status(CONFLICT)`) and `ProblemDetail.status`. The body uses `application/problem+json` along with extension field `code` for stable client handling.

`ex` is accepted to match the error type, while intentionally **not forwarding `ex.getMessage()` directly** to the client. This reduces the risk of leaking backend details. In a real product, you can safely log the error with a correlation ID without logging sensitive personal data.

### 10.5. Running and Testing with curl

With JDK 21 and a compatible Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

If the project lacks a wrapper yet has a compatible Gradle installed, generate one:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Successful request:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

Expected HTTP 200 and JSON:

~~~json
{"id":1,"title":"Java 21"}
~~~

Two cases throwing `ResponseStatusException`:

~~~bash
curl -i http://localhost:8080/api/books/0
curl -i http://localhost:8080/api/books/9
~~~

Expected 400 and 404 respectively. **Do not hardcode assumptions about the JSON body** for these two responses since the default error path can vary by configuration and environment.

Exception annotated with `@ResponseStatus`:

~~~bash
curl -i http://localhost:8080/api/books/retired
~~~

Expected 410 Gone. Status is the focus in this demo; do not assume the body includes the Java exception message.

Method annotated with `@ResponseStatus(NO_CONTENT)`:

~~~bash
curl -i -X POST http://localhost:8080/api/books/validate-only \
  -H "Content-Type: application/json" \
  -d '{"title":"Clean Code"}'
~~~

Expected **204 No Content**, with no response body.

Conflict handled by advice:

~~~bash
curl -i -X POST http://localhost:8080/api/books/check-title \
  -H "Content-Type: application/json" \
  -H "Accept: application/problem+json" \
  -d '{"title":"Java 21"}'
~~~

Expected response includes 409, `Content-Type: application/problem+json`, and a body equivalent to:

~~~json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "A book with this title already exists",
  "code": "TITLE_ALREADY_EXISTS"
}
~~~

`instance` and other headers may be added depending on framework/configuration; JSON object key order is insignificant. In real APIs, test HTTP status and JSON field values rather than comparing the entire response verbatim.

## 11. MockMvc Tests: Checking Status and Body

**src/test/java/com/example/httperror/BookControllerTest.java**

~~~java
package com.example.httperror;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validBookHas200() throws Exception {
        mvc.perform(get("/api/books/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Java 21"));
    }

    @Test
    void responseStatusExceptionReturns400Or404() throws Exception {
        mvc.perform(get("/api/books/0"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/api/books/9"))
            .andExpect(status().isNotFound());
    }

    @Test
    void annotatedExceptionReturns410() throws Exception {
        mvc.perform(get("/api/books/retired"))
            .andExpect(status().isGone());
    }

    @Test
    void annotatedMethodReturns204WithNoBody() throws Exception {
        mvc.perform(post("/api/books/validate-only")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Clean Code\"}"))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""));
    }

    @Test
    void adviceReturns409WithProblemDetails() throws Exception {
        mvc.perform(post("/api/books/check-title")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_PROBLEM_JSON)
                .content("{\"title\":\"Java 21\"}"))
            .andExpect(status().isConflict())
            .andExpect(header().string(
                "Content-Type", MediaType.APPLICATION_PROBLEM_JSON_VALUE))
            .andExpect(jsonPath("$.status").value(409))
            .andExpect(jsonPath("$.title").value("Conflict"))
            .andExpect(jsonPath("$.code")
                .value("TITLE_ALREADY_EXISTS"));
    }

    @Test
    void blankTitleIsBadRequest() throws Exception {
        mvc.perform(post("/api/books/check-title")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unsupportedMethodGets405() throws Exception {
        mvc.perform(put("/api/books/1"))
            .andExpect(status().isMethodNotAllowed());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The tests use `@SpringBootTest` + `@AutoConfigureMockMvc` to load the application context and MVC test infrastructure **without needing to open a real Tomcat TCP socket**. They verify exception resolvers and response bodies at the Spring web layer, and do not replace integration tests through a reverse proxy or security gateway.

Be careful asserting exact `Content-Type` headers if converters/configs append a charset. The code explicitly sets `application/problem+json` in the advice; if more flexibility is needed in custom environments, use `contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)`.

**Do not assert the `reason` content of `ResponseStatusException` via JSONPath in this test.** The 400/404 responses depend on error configuration; this lesson demonstrates the status contract first, while stable bodies are guaranteed by dedicated advice.

## 12. ResponseStatusException with @ExceptionHandler and @ControllerAdvice

A practical policy:

- In controllers/web adapters, `ResponseStatusException` helps express simple conditions when no complex error schema is needed.
- In the domain layer, use exception/return types independent of Servlet/WebFlux.
- At the web boundary, `@RestControllerAdvice` maps domain exceptions to `ProblemDetail` or error DTOs.
- For built-in framework errors, choose appropriate overrides of `ResponseEntityExceptionHandler` or properly ordered advice.

You can add a dedicated handler for `ResponseStatusException` if the API requires a uniform JSON body, but watch **interactions with Spring Boot's exception handlers**, especially when Problem Details is enabled. Never catch all `Exception.class` and return 400/200; that hides system failures and skews metrics.

### 12.1. Advice Order and Scope

`@ControllerAdvice` can limit its scope by controllers/packages/annotations and use `@Order` to adjust precedence. If multiple advices catch the same exception type, the outcome depends on precedence.

Keep specialized handlers for business errors, retain default framework behavior for request mapping/validation until you have a reason to change it, and write integration tests for standardized error paths.

### 12.2. Which HTTP Codes Should Internal Exceptions Map To?

A guiding principle is that the business layer emits exceptions describing **why an operation could not complete**; the web adapter interprets them in the context of an HTTP operation:

~~~text
Domain:
  DuplicateTitleException
       |
       v
Web adapter:
  409 Conflict + TITLE_ALREADY_EXISTS

Domain:
  BookNotFoundException
       |
       v
Web adapter:
  404 Not Found

Infrastructure:
  DatabaseUnavailableException
       |
       v
Web adapter / operational policy:
  503 Service Unavailable (when genuinely temporarily unavailable)
  or 500/Internal Server Error depending on actual cause
~~~

This is a **guideline**, not a rule that every database error is 503. An internal database connection timeout might yield 500, 503, or a gateway timeout depending on the situation and architecture.

## 13. Validation, Authentication, and Routing: Who Decides the Status?

Some errors happen before the controller method is ever called:

| Layer | Scenario | Typical Status |
| --- | --- | --- |
| HTTP parsing/binding | Invalid JSON, missing required body | 400 |
| Jakarta Bean Validation | `@NotBlank`/`@NotNull` in `@Valid @RequestBody` fails | 400 per MVC defaults |
| Request mapping | Path does not exist | 404 |
| Request mapping | HTTP method unsuitable | 405 |
| Content negotiation | `Content-Type` not accepted | 415 |
| Content negotiation | `Accept` cannot be satisfied | 406 |
| Spring Security | Unauthenticated | 401 or redirect to login depending on scheme |
| Spring Security | Unauthorized | 403 or hidden resource per policy |
| Application | Resource ID does not exist | 404 |
| Application | Resource state conflict | 409 or 412/422 per contract |
| Infrastructure | Unexpected failure | 500 or policy-appropriate code |

Do not duplicate all of this logic in every controller. Spring MVC and Spring Security already have appropriate resolvers and handlers; customize error bodies and logging without breaking HTTP semantics.

### 13.1. 401 Needs Authentication Challenges

With HTTP authentication, 401 typically requires `WWW-Authenticate` per scheme. Throwing `ResponseStatusException(UNAUTHORIZED)` manually in a controller may omit the challenge header or bypass Spring Security's configured policy.

The proper solution is configuring `AuthenticationEntryPoint`/authentication mechanisms and testing with matching clients.

### 13.2. 403 and 404 for Sensitive Resources

Some systems intentionally return 404 to avoid revealing resources the client is not allowed to see. That must be a **consistent security/privacy policy**, not a casual substitute for authorization; internally you still need proper auditing and enforcement.

## 14. 409, 412, and 422: Distinguishing Business Errors

Three statuses often conflated:

**409 Conflict**: the request conflicts with the current state—for instance, a unique name already exists, or a state transition is disallowed because the resource is in another stage. The client can adjust data/refresh state and retry.

**412 Precondition Failed**: the client sent an HTTP precondition like `If-Match`, and the ETag is no longer valid. Used for HTTP-level optimistic concurrency to stop clients from overwriting modified resources.

**422 Unprocessable Content**: the HTTP body is syntactically valid and the media type is understood, yet semantic instructions cannot be processed under policy. For example, a syntactically valid payment request violating a specific business rule; depending on contract, 409 or 422 may be chosen.

There is no automatic standard mapping saying “all business exceptions = 422”. Document which code applies to each error type in OpenAPI, tests, and client documentation.

### 14.1. Duplicate Keys and Race Conditions

Code:

~~~java
if (repository.existsByName(name)) {
    throw new ResponseStatusException(HttpStatus.CONFLICT);
}
repository.save(entity);
~~~

is an anti-pattern illustrating a **check-then-act race**. Two concurrent requests can both see the name absent and both save. To guarantee uniqueness, use database constraints (or real synchronization mechanisms), transactions, and exception mapping to status 409 per policy.

Never return raw SQL unique-constraint messages or internal table/column names to clients. When a stable error code is needed, return a public `code` like `TITLE_ALREADY_EXISTS` in the error response.

## 15. 429 and 503: Overload, Retries, and Retry-After

**429 Too Many Requests** usually indicates the client exceeded a rate limit/quota. **503 Service Unavailable** indicates the server temporarily cannot handle requests due to maintenance or overload. Both can include a `Retry-After` header:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
~~~

`Retry-After: 30` specifies a wait time in seconds per header syntax. It can also be an HTTP-date. Do not send a dummy value just “to fill the header” if the server lacks an actual policy.

An API client should:

1. Check whether the request can be safely retried (idempotency, idempotency key, transaction state).
2. Respect `Retry-After` when present.
3. Use exponential backoff + jitter to avoid retry storms.
4. Enforce retry limits and overall deadlines.
5. Not blindly retry 400 validation errors or 404 resource errors continuously without reason.

When a controller integrates real rate limiting, the web layer can return 429/`Retry-After`; however, **rate limiting must be designed explicitly**, not assumed to exist just because `ResponseStatusException` exists.

Do not use 429 simply because the database is slow; if the entire server is temporarily overloaded, 503 reflects reality better. When an API gateway returns 502/504, separate proxy-originated errors from backend-originated errors before changing status handlers.

## 16. Status Codes and Observability

HTTP status is an important monitoring signal:

- Rising 5xx rates often indicate server/infrastructure failures.
- Rising 400s after a release can mean clients send a different format or validation changed.
- Rising 401/403s can reflect auth misconfiguration, client credential issues, or unauthorized activity.
- Rising 404s can signal changed routes, broken links, or missing business resources.
- Rising 409s can reflect concurrency conflicts or business rules.
- Rising 429s can show quotas/rate limits kicking in or unexpected load spikes.
- Rising 503/504s can indicate overload, dependency outages, or gateway timeouts.

Do not log every `ResponseStatusException(NOT_FOUND)` as a critical system error. Use appropriate log levels, metrics, trace IDs, and per-endpoint tracking. Conversely, never “hide” 500s by returning HTTP 200 to make dashboards look prettier.

Never attach messages containing personal data, tokens, or SQL to error responses. In production, include a non-sensitive correlation/request ID to trace logs. Client-facing descriptions should be stable, safe, and localized if needed.

## 17. Common Mistakes and Misconceptions

### 17.1. @ResponseStatus(reason=...) Guarantees a JSON Message

False. In Servlet MVC, a non-empty `reason` can trigger `sendError`; the container or Boot may produce a different body or ignore the method return value. If an API needs stable JSON, use an explicit response or exception handler.

### 17.2. new ResponseStatusException(404) Always Outputs ProblemDetail

Not guaranteed. Framework 6 has `ErrorResponse`/`ProblemDetail` abstractions, but the resolver path and Boot Problem Details configuration decide the final HTTP body. Test actual statuses/bodies in the application.

### 17.3. @ResponseStatus Can Pick Multiple Statuses at Runtime

Not how the annotation works: an annotation attaches a fixed status to a method or exception class. To pick 400/404 based on data, use dynamic exceptions or `ResponseEntity`/advice.

### 17.4. HTTP 200 with {"success":false} Is Equivalent to an Error HTTP Status

Not equivalent: HTTP clients, caches, API gateways, and monitoring rely on the status line. Emit the proper HTTP status; any `success` field in the body is supplementary at best.

### 17.5. Validation Failures Should Default to 500

No. Invalid input is something the client can correct, typically 400. Reserve 500 for genuine server errors.

### 17.6. 401 and 403 Are Interchangeable

No. Incomplete authentication is distinct from unauthorized access. Let Spring Security handle challenges and access denials per scheme.

### 17.7. 404 Always Proves No Controller Mapping Exists

No. A controller may intentionally return 404 for a missing resource ID, or a security policy may conceal a resource.

### 17.8. 409 and 422 Can Be Swapped Arbitrarily

Avoid doing so. Choose explainable semantics, document them per error type, and keep client contracts consistent.

### 17.9. Using 410 for Every Missing Resource

No. 410 conveys that the server knows the resource is permanently gone; 404 remains right for most cases.

### 17.10. Returning 503 for Every Database Error

Incorrect. 503 should mean “service temporarily unavailable”; data errors, code bugs, or internal server exceptions may be 500, while constraint conflicts may be 409.

### 17.11. Committed Responses Can Still Change Status

No. Once bytes/headers have gone out to the client, status cannot be retroactively changed. This is especially crucial with Servlet streaming, SSE, and WebFlux Flux.

### 17.12. Error Response Bodies Can Safely Include Any Throwable Message

Dangerous. Throwable messages can contain SQL, file paths, or secret values. Use safe messages and public error codes.

### 17.13. Catching Exception and Returning 400 Is Simpler

False. Catch-all 400 masks server bugs and corrupts metrics. Define handlers per error type and let unrecognized errors pass safely to 500 handling.

### 17.14. Testing Status Alone Is Enough for Public APIs

Insufficient if clients depend on error JSON. Test status, Content-Type, error codes, field presence, and version compatibility; meanwhile, avoid asserting default bodies not guaranteed by your contract.

## 18. Checklist for Choosing HTTP Statuses and Handling Errors

1. Does the client need to know the request succeeded, was accepted for processing, or failed? Choose 200/201/202/204 with accurate semantics.
2. Did the failure stem from syntax/invalid body, authentication, authorization, missing resource, conflict, or server failure?
3. Is `@ResponseStatus` attached to a method/exception whose status is genuinely fixed in all situations?
4. Does the annotation have a non-empty `reason` that triggers Servlet `sendError` and drops the body?
5. Is `ResponseStatusException` suitable for a dynamic status where no custom schema is needed?
6. When the API needs a stable body, are `ResponseEntity`/`@RestControllerAdvice`/`ProblemDetail` and tests in place?
7. Are domain exceptions overly coupled to Spring HTTP types?
8. Is there another higher-priority `@ExceptionHandler` or `@ControllerAdvice` altering the status mapping?
9. Does the HTTP status line match `ProblemDetail.status` and documentation?
10. Are clear policies defined for 400, 401, 403, 404, 409, 410, 412, 415, 422, 429, 500, and 503?
11. Are statuses/headers generated by the framework/Spring Security before the controller? Have you avoided accidentally overwriting `Allow`/`WWW-Authenticate`?
12. For 201, does `Location` point to the genuinely created resource with a valid public URL?
13. For 204/304, does the response accidentally carry a body?
14. When emitting 429/503, are `Retry-After` and retry policies sensible?
15. Are internal stack traces, SQL, or secrets leaked in `detail`/`reason`?
16. Is there a database unique constraint to prevent races when returning 409 for duplicate keys?
17. For streaming/async, does any code try to change status after the response commits?
18. Do unit/MockMvc tests check statuses, headers, and client-facing error representations?
19. Does monitoring distinguish expected 4xx from unexpected 5xx and account for gateway 502/504?
20. Do OpenAPI/API contracts document status codes and schemas per endpoint?

**Conclusion:** `@ResponseStatus` fits fixed statuses on methods or exceptions; `ResponseStatusException` fits choosing an HTTP status based on runtime conditions; `ResponseEntity` and `@RestControllerAdvice`/`@ExceptionHandler` give tighter control over statuses, headers, and error schemas. Choose **HTTP codes according to error semantics**, not the convenience of an exception type. Especially in Spring MVC, `@ResponseStatus(reason=...)` can trigger `sendError`, so do not rely on it to guarantee JSON errors. For a reliable API, align the status line, ProblemDetail/error codes, information security, and tests.

## References

- [Spring Framework 6.1 — @ResponseStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/ResponseStatus.html): status, reason, and `sendError` warning.
- [Spring Framework 6.1 — ResponseStatusException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/web/server/ResponseStatusException.html): constructors, `ErrorResponse`, and `ProblemDetail`.
- [Spring Framework 6.1 — ResponseStatusExceptionResolver Javadoc](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/servlet/mvc/annotation/ResponseStatusExceptionResolver.html): annotation/exception handling in Servlet MVC.
- [Spring Framework — MVC Exceptions](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html): `HandlerExceptionResolver` chain.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, `ResponseEntityExceptionHandler`.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.mvc.problemdetails.enabled`.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): error representation structure.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): definitions of HTTP status codes and related headers.