# Building Unified API Error Responses for Spring MVC or WebFlux

## 1. Practical Goal and Completion Criteria

A Spring API can raise errors at many stages: JSON parsing, type conversion, data binding, Bean Validation, method validation, authorization, business logic, and downstream system access. If every layer returns a different JSON structure, clients must write brittle branching logic while internal error details risk leaking out.

The goal is a consistent, testable **error response contract** using **`ProblemDetail` (RFC 9457)** on **Spring MVC** or **Spring WebFlux**:

1. Return the right **HTTP status** instead of turning every exception into 400 or 500.
2. Use the same format for **validation errors**, unreadable JSON, business errors, missing resources, and server errors.
3. Provide a stable **machine-readable `code`**; clients never have to match English/Vietnamese prose in messages.
4. Include an **`errorId`** for log lookup without returning stack traces or rejected values.
5. Include a **`violations`** list for field/parameter errors per the public DTO contract; an empty array for non-validation errors.
6. Populate **`instance`** as the request path URI alongside `type`, `title`, `status`, and `detail` per RFC 9457.
7. Separate **client input** errors (typically 4xx) from **server return-value** or internal failures (5xx).
8. Preserve standard headers such as `Allow` on 405 and `Retry-After` on 429/503 when present, instead of overwriting them arbitrarily.
9. Provide **MockMvc tests** for MVC and **WebTestClient tests** for WebFlux; never assume both stacks share identical exception classes and handler signatures.
10. Never use the error body as a substitute for HTTP status, and never leak exception classes, database SQL, tokens, raw bodies, or stack traces.

The example builds **a complete Spring MVC project** and then demonstrates **how to adapt it to WebFlux** in a separate project. Both options share the same schema, codes, and policies, while **never** putting both `spring-boot-starter-web` and `spring-boot-starter-webflux` in a single demo and guessing which runtime web stack Spring Boot picks.

## 2. Choosing RFC 9457 `ProblemDetail` Over Ad-Hoc Custom JSON

Spring Framework 6.x supports `ProblemDetail`, `ErrorResponse`, `ErrorResponseException`, and `ResponseEntityExceptionHandler` for both Servlet MVC and WebFlux. `ProblemDetail` holds five standard fields plus custom properties:

| Field | Required by example design? | Meaning |
| --- | --- | --- |
| `type` | Yes | Problem type; the example uses `about:blank`; if building machine-readable docs, use a stable error-type URI. |
| `title` | Yes | Short summary without sensitive data. |
| `status` | Yes | HTTP status code; **must match the HTTP status line**. |
| `detail` | Yes | Safe human-readable explanation; may be localized. |
| `instance` | Yes in example | URI of the occurrence/request path; never put tokens/query secrets here. |
| `code` | Custom, yes | Stable code for client handling. |
| `errorId` | Custom, yes | Identifier for an error occurrence; must correlate with real log/trace systems in production. |
| `violations` | Custom, yes | Allowlisted field/parameter errors and messages; empty when not a validation error. |

**Example response** (UUIDs are illustrative, not fixed output):

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "instance": "/api/items",
  "code": "VALIDATION_FAILED",
  "errorId": "a41e2813-7a60-41e3-8e0e-d775de7e28e6",
  "violations": [
    {"field": "name", "message": "Must not be blank"},
    {"field": "quantity", "message": "Must be at least the minimum"}
  ]
}
~~~

This is an **example JSON shape**; key ordering does not matter, `errorId` changes per request, and exact messages depend on policy. With Spring/Jackson, custom entries in `ProblemDetail.properties` serialize as **top-level JSON fields** rather than nested under a `properties` map.

### Do Not Abuse `type`

RFC 9457 `type` classifies the problem. `about:blank` means the status/title serves as the generic classification. If using a URI like `https://api.example.com/problems/validation`, use a URI that your application **actually manages and documents**, rather than inventing undocumented URIs. The runnable example chooses `about:blank` plus `code`; larger APIs can upgrade to a **type URI registry** later.

### `errorId` Differs from traceId

In the demo, `errorId` is generated via `UUID.randomUUID()` and returned to the client. On unexpected exceptions, the handler logs that same ID. In real systems, correlate with distributed tracing (`traceId`/`spanId` from OpenTelemetry or Micrometer), request logging, log retention, and access policies. **A UUID in JSON alone does not guarantee log searchability** unless it is logged alongside the server event.

Do not blindly read an `X-Request-ID` header from clients and treat it as trustworthy; if accepting external correlation IDs, validate format, bound length, and pair with a server-generated ID where appropriate.

## 3. Classifying Errors Before Writing Handlers

| Cause | Typical Spring MVC exception | Typical Spring WebFlux exception | Recommended status |
| --- | --- | --- | --- |
| Invalid `@Valid @RequestBody` DTO | `MethodArgumentNotValidException` | `WebExchangeBindException` | 400 |
| Invalid method parameters (e.g., `@RequestParam @Min(1)`) | `HandlerMethodValidationException` | `HandlerMethodValidationException` | 400 |
| **Controller method return value violates constraint** | `HandlerMethodValidationException` | `HandlerMethodValidationException` | **500** |
| Malformed/unreadable JSON | `HttpMessageNotReadableException` | `ServerWebInputException` or matching codec cause | 400 |
| Unconvertible query/path number | `TypeMismatchException`, `MethodArgumentTypeMismatchException` | `ServerWebInputException` / type conversion error | 400 |
| Missing required query/header/body | `MissingServletRequestParameterException` or subtype | `MissingRequestValueException` / `ServerWebInputException` | 400 |
| Unsupported request method | `HttpRequestMethodNotSupportedException` | `MethodNotAllowedException` | 405 |
| Unsupported `Content-Type` | `HttpMediaTypeNotSupportedException` | `UnsupportedMediaTypeStatusException` | 415 |
| Unnegotiable `Accept` | `HttpMediaTypeNotAcceptableException` | `NotAcceptableStatusException` | 406 |
| Domain resource not found | Dedicated domain exception | Dedicated domain exception | 404 |
| Business conflict (duplicate/version mismatch) | Dedicated domain exception | Dedicated domain exception | 409 |
| Unauthenticated user | Spring Security entry point | Reactive Security entry point | 401 |
| Authenticated but forbidden | Spring Security access denied handler | Reactive access denied handler | 403 |
| Payload too large, rate limited | Multipart/gateway/rate limiter exceptions | Codec/gateway/rate limiter exceptions | 413 / 429 per policy |
| Database/serialization/bug | Unhandled runtime exception | Unhandled reactive signal/exception | 500 |
| Downstream overloaded/unavailable | Classified service/gateway exception | Classified reactive downstream exception | 503/504 where appropriate |

**Do not lump everything into 400.** With controller method validation in Spring 6.1+, `HandlerMethodValidationException#getStatusCode()` returns **400 for input violations** and **500 for return-value violations**. With Bean Validation on **service AOP**, `ConstraintViolationException` does not inherently know the HTTP status of a request: it could come from internal system input or a server return value. Translate status at the boundary based on context.

**Do not lump everything into 500.** A request with `quantity=0` that is valid JSON yet fails `@Min(1)` must return 400. A missing resource per contract must return 404, not 500.

## 4. Overall Flow and Layer Responsibilities

~~~text
HTTP request
    |
    +-- Servlet MVC stack ------------------------------+
    |    HttpMessageConverter / @ModelAttribute binding
    |    @Valid + method validation
    |    Handler / Controller -> service -> repository
    |    ExceptionHandlerExceptionResolver
    |    @RestControllerAdvice / ResponseEntityExceptionHandler
    |
    +-- Reactive WebFlux stack -------------------------+
         HttpMessageReader / reactive codec
         @Valid + method validation
         Annotated handler -> Mono/Flux service
         @ExceptionHandler / ResponseEntityExceptionHandler
         WebExceptionHandler fallback
    |
    v
Internal exception category + safe error metadata
    |
    v
ProblemDetail (RFC 9457)
    |
    +-- HTTP status, Content-Type, relevant headers
    +-- type/title/status/detail/instance
    +-- code/errorId/violations
    |
    v
API client
~~~

**Important:** `@RestControllerAdvice` is not a “catch-everything filter”:
- Errors from the **Servlet filter chain**, Spring Security authentication/authorization, the servlet container, or a proxy/gateway can arise **outside the MVC controller exception resolver**.
- In WebFlux, errors from `WebFilter`, functional handler routes, and already-committed responses may require a separate `WebExceptionHandler` or `ErrorWebExceptionHandler`.
- Once a response has started streaming/committed, you cannot reliably replace it with a new JSON `ProblemDetail`.
- Boot's default `/error`, static-resource fallbacks, or error dispatches may produce responses under their own policies; test end-to-end and integrate at the proper layer.

For true consistency in production, treat **controller advice**, **security handlers**, **fallback error infrastructure**, and **gateway** as distinct parts sharing one contract.

## 5. Designing Stable Error Codes

Example client-facing codes:

| `code` | HTTP | When clients act on it |
| --- | --- | --- |
| `VALIDATION_FAILED` | 400 | Highlight `violations.field` entries, prompt form fixes. |
| `MALFORMED_BODY` | 400 | Unreadable JSON/body, fix payload. |
| `BAD_REQUEST` | 400 | Other missing or invalid parameters/request structure. |
| `RESOURCE_NOT_FOUND` | 404 | Domain resource does not exist or policy hides existence. |
| `METHOD_NOT_ALLOWED` | 405 | Wrong HTTP method for route, switch HTTP verb. |
| `NOT_ACCEPTABLE` | 406 | Unsupported `Accept` header. |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Send the proper `Content-Type`/format. |
| `CONFLICT` | 409 | Conflict with current state, e.g., duplicate. |
| `INTERNAL_ERROR` | 500 | Show generic message and report `errorId`. |
| `SERVICE_UNAVAILABLE` | 503 | Retry per policy, check `Retry-After` if present. |

The `code` **must never change just because the locale changes**. `detail`, `title`, and `violations.message` can be localized via `MessageSource`/resource bundles, while clients must never branch on localized prose. If versioning is needed, maintain a code registry and deprecation policy; avoid putting internal Java exception class names into API error codes.

### `violations` and Field Paths

A field entry has the shape:

~~~json
{"field":"name","message":"Must not be blank"}
~~~

For object-level or cross-field errors, you can use a stable public marker field such as `"_object"`. Never return `BindingResult#getRejectedValue()`, raw JWTs, passwords, SQL parameters, or PII values. Field names should come only from the **public request DTO/schema**, never entity/repository internals.

The `violations` array can be empty for 404, 409, 415, or 500. Always keeping this field present gives clients a consistent schema. If capping the number of returned errors (e.g., 20), document truncation to prevent oversized payloads.

## 6. MVC: Runnable Project with Spring Boot 3.5.x and Java 17+

The sample uses Spring Boot **3.5.16** and Spring Framework 6.2.x to demonstrate verified APIs. The 3.5.x branch was an older branch at the time of writing; **production applications should run a supported Boot/Framework line with current security patches**, rather than copying demo version numbers as operational guidance. Imports/configs may need adjustments when targeting Boot 4.x/Spring 7.x.

Structure:

~~~text
pom.xml
src/main/java/com/example/problems/
  ProblemApplication.java
  CreateItemRequest.java
  ItemView.java
  ApiViolation.java
  ApiProblemFactory.java
  ItemNotFoundException.java
  DuplicateItemException.java
  ItemController.java
  MvcApiProblemAdvice.java
src/test/java/com/example/problems/
  MvcApiProblemTest.java
~~~

This is a **standalone MVC REST project**. Do not include `spring-boot-starter-webflux` in this POM.

### 6.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>api-problems-mvc</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

`spring-boot-starter-validation` provides the Bean Validation provider; `spring-boot-starter-web` alone does not guarantee a provider across all Boot versions/setups. The project defines its own `@RestControllerAdvice`, so it does not rely on `spring.mvc.problemdetails.enabled` to enable it. If Boot-generated `ProblemDetail` advice is already active in another application, check advice ordering and potential handler conflicts.

### 6.2. `ProblemApplication.java`

~~~java
package com.example.problems;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProblemApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProblemApplication.class, args);
    }
}
~~~

### 6.3. Input DTO `CreateItemRequest.java`

~~~java
package com.example.problems;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateItemRequest(
        @NotBlank String name,
        @Min(1) int quantity) {
}
~~~

**Why use a record?** The request schema has only two client-owned fields and never binds directly to a JPA entity. When `name=""` or `quantity=0`, Jakarta Bean Validation puts field errors into `MethodArgumentNotValidException`. When JSON is syntactically invalid or `quantity="oops"` cannot convert, Jackson/`HttpMessageConverter` fails **before Bean Validation** via `HttpMessageNotReadableException`.

### 6.4. Response DTO `ItemView.java`

~~~java
package com.example.problems;

public record ItemView(
        String id,
        String name,
        int quantity) {
}
~~~

Do not return entities or internal fields such as secrets/tenant/role merely for convenience; business data responses need their own DTO/contract.

### 6.5. Field Violation `ApiViolation.java`

~~~java
package com.example.problems;

public record ApiViolation(
        String field,
        String message) {
}
~~~

This type is serialized inside `violations`. It contains no `rejectedValue` or stack trace. When per-field codes are needed, extend with a public `reasonCode` under consistent versioning.

### 6.6. Shared Factory `ApiProblemFactory.java`

~~~java
package com.example.problems;

import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;

import java.net.URI;
import java.util.List;
import java.util.UUID;

public final class ApiProblemFactory {

    private ApiProblemFactory() {
    }

    public static ProblemDetail create(
            HttpStatusCode status,
            String code,
            String detail,
            List<ApiViolation> violations,
            String path) {

        ProblemDetail problem = ProblemDetail.forStatus(status);
        problem.setType(URI.create("about:blank"));

        HttpStatus standard = HttpStatus.resolve(status.value());
        problem.setTitle(
                standard == null ? "HTTP Error"
                                 : standard.getReasonPhrase());

        problem.setDetail(detail);

        // Use path only; omit query strings that could carry tokens.
        if (path != null && path.startsWith("/")) {
            problem.setInstance(URI.create(path));
        }

        problem.setProperty("code", code);
        problem.setProperty(
                "errorId", UUID.randomUUID().toString());
        problem.setProperty("violations", violations);

        return problem;
    }

    public static String codeFor(HttpStatusCode status) {
        return switch (status.value()) {
            case 400 -> "BAD_REQUEST";
            case 404 -> "RESOURCE_NOT_FOUND";
            case 405 -> "METHOD_NOT_ALLOWED";
            case 406 -> "NOT_ACCEPTABLE";
            case 409 -> "CONFLICT";
            case 415 -> "UNSUPPORTED_MEDIA_TYPE";
            case 429 -> "RATE_LIMITED";
            case 503 -> "SERVICE_UNAVAILABLE";
            default -> status.is5xxServerError()
                    ? "INTERNAL_ERROR" : "HTTP_ERROR";
        };
    }

    public static String detailFor(HttpStatusCode status) {
        if (status.is5xxServerError()) {
            return "An internal error occurred.";
        }

        return switch (status.value()) {
            case 400 -> "The request is invalid.";
            case 404 -> "The requested resource was not found.";
            case 405 -> "This HTTP method is not supported.";
            case 406 -> "No acceptable response representation.";
            case 409 -> "The request conflicts with current state.";
            case 415 -> "Unsupported request media type.";
            case 429 -> "Too many requests.";
            default -> "The request could not be completed.";
        };
    }
}
~~~

**This file is shared between MVC and WebFlux**: it imports only `spring-web` classes, with no Servlet or Reactor dependencies. `ProblemDetail` stores `code/errorId/violations` in custom properties, which Spring's Jackson module serializes as sibling keys alongside `status`.

`errorId` changes on every `create` call. For 500 exceptions, the controller advice logs that exact ID. For 4xx errors, avoid logging the raw request body because users might submit sensitive data.

`URI.create(path)` assumes the servlet path has been validly encoded by the container; in hardened applications guarding against unusual paths, set `instance` to the route template or a sanitized URI. Never put raw query strings, `Authorization` headers, or request payloads into `instance`.

### 6.7. Domain Exception Classes

`ItemNotFoundException.java`:

~~~java
package com.example.problems;

public final class ItemNotFoundException
        extends RuntimeException {
}
~~~

`DuplicateItemException.java`:

~~~java
package com.example.problems;

public final class DuplicateItemException
        extends RuntimeException {
}
~~~

These are used **intentionally** at business boundaries. Do not map arbitrary `IllegalArgumentException`s to 400 or arbitrary `IllegalStateException`s to 409; generic exceptions may reflect backend bugs rather than client-fixable errors.

### 6.8. Controller `ItemController.java`

~~~java
package com.example.problems;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ItemView> create(
            @Valid @RequestBody CreateItemRequest request) {

        if ("conflict".equalsIgnoreCase(request.name())) {
            throw new DuplicateItemException();
        }

        ItemView view = new ItemView(
                "item-42", request.name(), request.quantity());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(view);
    }

    @GetMapping("/{id}")
    public ItemView get(@PathVariable String id) {
        if ("missing".equals(id)) {
            throw new ItemNotFoundException();
        }

        return new ItemView(id, "Sample", 2);
    }

    // Constraint directly on controller parameter:
    // Spring MVC 6.1+ uses built-in method validation.
    @GetMapping("/search")
    public List<ItemView> search(
            @RequestParam("limit") @Min(1) int limit) {
        return List.of(new ItemView("item-1", "Sample", limit));
    }

    // Intentionally violate return-value constraint to test HTTP 500.
    @NotBlank
    @GetMapping(path = "/invalid-output",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String invalidOutput() {
        return "";
    }

    // For testing only: exception text must never be exposed.
    @GetMapping("/explode")
    public String unexpectedFailure() {
        throw new IllegalStateException(
                "Sensitive database details must not leak");
    }
}
~~~

**Do not place class-level `@Validated` on this MVC controller.** Spring Framework 6.1+ provides built-in controller method validation; class-level `@Validated` can route method validation through an AOP proxy and alter the exception pipeline. `@Valid @RequestBody` produces `MethodArgumentNotValidException`, while `@Min` on a query parameter and `@NotBlank` on a controller return value produce `HandlerMethodValidationException`.

Do not expose `/explode` or `/invalid-output` as real endpoints. They are controlled test fixtures for verifying the 500 contract.

### 6.9. Advice `MvcApiProblemAdvice.java`

This is the centerpiece: Spring MVC's `ResponseEntityExceptionHandler` **from the Servlet MVC package**, providing handlers for framework exceptions. We override selected hooks to attach business codes while keeping one schema builder:

~~~java
package com.example.problems;

import jakarta.servlet.http.HttpServletRequest;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
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
import org.springframework.web.context.request.ServletWebRequest;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.util.List;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class MvcApiProblemAdvice
        extends ResponseEntityExceptionHandler {

    private static final Logger LOG =
            LoggerFactory.getLogger(MvcApiProblemAdvice.class);

    private static String path(WebRequest request) {
        if (request instanceof ServletWebRequest servlet) {
            return servlet.getRequest().getRequestURI();
        }
        return null;
    }

    private static String safeMessage(FieldError error) {
        return switch (String.valueOf(error.getCode())) {
            case "NotBlank" -> "Must not be blank";
            case "Min" -> "Must be at least the minimum";
            default -> "Invalid value";
        };
    }

    // Individual @Valid @RequestBody / @ModelAttribute:
    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<ApiViolation> violations =
                ex.getBindingResult().getFieldErrors()
                        .stream()
                        .map(err -> new ApiViolation(
                                err.getField(), safeMessage(err)))
                        .distinct()
                        .toList();

        ProblemDetail problem = ApiProblemFactory.create(
                status,
                "VALIDATION_FAILED",
                "One or more fields are invalid.",
                violations,
                path(request));

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    // Direct parameter constraints and return-value constraints:
    @Override
    protected ResponseEntity<Object>
    handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (ex.isForReturnValue()) {
            // Do not expose details of server-generated output.
            ProblemDetail problem = ApiProblemFactory.create(
                    status,
                    "INTERNAL_ERROR",
                    "An internal error occurred.",
                    List.of(),
                    path(request));

            return handleExceptionInternal(
                    ex, problem, headers, status, request);
        }

        ProblemDetail problem = ApiProblemFactory.create(
                status,
                "VALIDATION_FAILED",
                "One or more parameters are invalid.",
                List.of(new ApiViolation(
                        "parameter", "Invalid value")),
                path(request));

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    // JSON parse/converter errors:
    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ApiProblemFactory.create(
                status,
                "MALFORMED_BODY",
                "Request body is missing or cannot be read.",
                List.of(),
                path(request));

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    // Runs at the end of handling framework exceptions
    // caught by ResponseEntityExceptionHandler:
    @Override
    protected ResponseEntity<Object> createResponseEntity(
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem;

        if (body instanceof ProblemDetail pd
                && pd.getProperties() != null
                && pd.getProperties().containsKey("code")) {
            problem = pd;
        }
        else {
            // Also normalize non-overridden framework exceptions.
            // Never echo original body/message that could be sensitive.
            problem = ApiProblemFactory.create(
                    status,
                    ApiProblemFactory.codeFor(status),
                    ApiProblemFactory.detailFor(status),
                    List.of(),
                    path(request));
        }

        // Preserve framework-provided headers (Allow, ...).
        return super.createResponseEntity(
                problem, headers, status, request);
    }

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ItemNotFoundException ex,
            HttpServletRequest request) {

        ProblemDetail problem = ApiProblemFactory.create(
                HttpStatus.NOT_FOUND,
                "RESOURCE_NOT_FOUND",
                "The requested item was not found.",
                List.of(),
                request.getRequestURI());

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(problem);
    }

    @ExceptionHandler(DuplicateItemException.class)
    public ResponseEntity<ProblemDetail> conflict(
            DuplicateItemException ex,
            HttpServletRequest request) {

        ProblemDetail problem = ApiProblemFactory.create(
                HttpStatus.CONFLICT,
                "CONFLICT",
                "An item with this name already exists.",
                List.of(),
                request.getRequestURI());

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(problem);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ProblemDetail> unexpected(
            Exception ex,
            HttpServletRequest request) {

        ProblemDetail problem = ApiProblemFactory.create(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "An internal error occurred.",
                List.of(),
                request.getRequestURI());

        // ID returned to client matches the ID written to server logs:
        Object errorId = problem.getProperties().get("errorId");
        LOG.error("Unhandled API error, errorId={}", errorId, ex);

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
~~~

### 6.10. Why Does This Design Use the Right Spring Hooks?

- `ResponseEntityExceptionHandler` handles **Spring MVC framework exceptions** in one advice. Never define an `@ExceptionHandler(MethodArgumentNotValidException.class)` that **collides** with the handler already defined in the base class; override the protected `handleMethodArgumentNotValid` method instead.
- `handleHandlerMethodValidationException` preserves the **status passed in by Spring**, including **500** for return-value violations. Never force the status to 400.
- `handleHttpMessageNotReadable` emits only a generic public message, without exposing Jackson parse stack traces or sensitive offsets.
- `createResponseEntity` is the single exit point normalizing unoverridden Spring exceptions while preserving `HttpHeaders`. Using the same factory ensures every response carries `code`, `errorId`, and `violations`.
- `@ExceptionHandler(ItemNotFoundException.class)` and `@ExceptionHandler(DuplicateItemException.class)` are **explicit business mappings**; domain exception statuses should not be inferred from generic class names.
- `@ExceptionHandler(Exception.class)` is a fallback **inside the MVC exception resolver** and is not guaranteed to cover filters, Security, Boot fallbacks, streaming, or gateways.
- `@Order(HIGHEST_PRECEDENCE)` gives the custom advice deterministic ordering when other advices exist; it does not replace reviewing existing advices and Spring Boot Problem Details auto-configuration.
- Logging records `errorId` and the exception only in server logs. Never return `ex.getMessage()`, SQL, stack traces, or `BindingResult` to clients.
- Validation errors are restricted to public `FieldError#getField()` plus safe message mappings; rejected values are never sent.
- The `violations` array is **always present**. For method-level validation, the demo uses generic field `"parameter"` to avoid misinterpreting parameter names. An advanced version can iterate `ex.getAllValidationResults()`/a visitor to emit sanitized parameter names.

**Warning:** `@ExceptionHandler(Exception.class)` must never be used to convert configuration errors, authorization errors, or return-value errors into 400. It maps only **unexpected MVC failures → 500** with safe content; filter-layer security handlers must be configured separately.

## 7. Testing MVC with MockMvc

Create `src/test/java/com/example/problems/MvcApiProblemTest.java`:

~~~java
package com.example.problems;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class MvcApiProblemTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validItemReturns201WithoutProblemBody() throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Notebook","quantity":2}
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name")
                        .value("Notebook"))
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void blankNameReturnsUnifiedValidationProblem()
            throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","quantity":2}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.instance")
                        .value("/api/items"))
                .andExpect(jsonPath("$.errorId").isString())
                .andExpect(jsonPath("$.violations[0].field")
                        .value("name"));
    }

    @Test
    void lowQuantityAlsoUsesValidationCode()
            throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Notebook","quantity":0}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.violations[0].field")
                        .value("quantity"));
    }

    @Test
    void malformedJsonIsNotBeanValidationError()
            throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"))
                .andExpect(jsonPath("$.violations").isArray());
    }

    @Test
    void wrongJsonTypeIsMalformedBody() throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Notebook","quantity":"oops"}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));
    }

    @Test
    void directMethodConstraintCreates400()
            throws Exception {
        mvc.perform(get("/api/items/search")
                    .param("limit", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.violations").isArray());
    }

    @Test
    void controllerReturnConstraintCreates500()
            throws Exception {
        mvc.perform(get("/api/items/invalid-output"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.status").value(500))
                .andExpect(jsonPath("$.code")
                        .value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.violations").isArray());
    }

    @Test
    void domainNotFoundHas404Code() throws Exception {
        mvc.perform(get("/api/items/missing"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("RESOURCE_NOT_FOUND"))
                .andExpect(jsonPath("$.instance")
                        .value("/api/items/missing"));
    }

    @Test
    void duplicateItemHas409Code() throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"conflict","quantity":2}
                            """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("CONFLICT"));
    }

    @Test
    void wrongContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("not json"))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code")
                        .value("UNSUPPORTED_MEDIA_TYPE"));
    }

    @Test
    void unsupportedMethodReturns405() throws Exception {
        mvc.perform(put("/api/items/missing"))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(header().exists("Allow"))
                .andExpect(jsonPath("$.code")
                        .value("METHOD_NOT_ALLOWED"));
    }

    @Test
    void unexpectedExceptionHidesInternalMessage()
            throws Exception {
        mvc.perform(get("/api/items/explode"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.errorId").isString())
                .andExpect(content().string(
                        not(containsString(
                                "Sensitive database details"))));
    }

    @Test
    void missingRequiredQueryParamIs400()
            throws Exception {
        mvc.perform(get("/api/items/search"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BAD_REQUEST"));
    }
}
~~~

There are **13 MockMvc tests** verifying:

- Happy path is not wrapped into a `ProblemDetail`.
- DTO validation with 400 and fields; `quantity=0` and `name=""`.
- Malformed JSON and Jackson type mismatches are classified differently from `@Valid`.
- Controller parameter method validation → 400.
- **Controller return-value validation → 500**, avoiding misclassifying server bugs as client errors.
- Domain not found 404, conflict 409.
- Unsupported `Content-Type` 415, unsupported method 405 with the `Allow` header preserved.
- Internal exceptions hide sensitive messages and include `errorId`.
- Missing query parameter maps to 400 with a generic code.

Run commands:

~~~bash
mvn test
mvn spring-boot:run
~~~

Or if the Maven wrapper has been generated:

~~~bash
./mvnw test
./mvnw spring-boot:run
~~~

**Note:** the sample code and assertions target Spring Boot 3.5.x / Spring Framework 6.2.x; this is **not evidence that Maven/JUnit was executed**. For Boot 4.x/Spring 7.x or custom `@ControllerAdvice`, adjust APIs/imports/expectations to the actual version. If Spring Security is present, test requests need appropriate auth/CSRF setup.

### 7.1. Do Not Assert a Fixed UUID

`errorId` changes every time an error is created. Tests should assert only its presence and string/UUID shape if strictness is desired; never compare the entire JSON response verbatim against a sample UUID. Timestamps should be tested similarly if added to the schema.

### 7.2. Do Not Assert `violations` Order When Multiple Fields Fail

When input triggers multiple violations, the order of field errors can vary by validation provider and traversal order. Unless the contract promises ordering, test the **set of field names** or JSONPath predicates rather than brittle list indices.

### 7.3. Testing `instance` Accurately

The demo reads `HttpServletRequest#getRequestURI()`, so `instance` is the **request path** excluding the query string. If the app sits behind a reverse proxy, context path, or path rewriting, document internal vs external URIs and apply a trusted forwarded-header policy; never accept unvalidated `Forwarded` headers into error links.

### 7.4. Verifying with curl

After starting the application:

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Notebook","quantity":2}'

curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":"","quantity":0}'

curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":'

curl -i http://localhost:8080/api/items/missing

curl -i "http://localhost:8080/api/items/search?limit=0"

curl -i http://localhost:8080/api/items/invalid-output
~~~

Expected statuses in order are **201, 400, 400, 404, 400, 500**. The success body is `ItemView`; error bodies use `ProblemDetail` with the corresponding error codes. **Do not treat any JSON snippet below as Java stdout**; these are HTTP responses, and `errorId` is non-deterministic.

## 8. WebFlux Version: Same Schema, Different Classes and Callback Signatures

If an application actually uses **Spring WebFlux**, there are two major differences:

1. `ResponseEntityExceptionHandler` resides in package **`org.springframework.web.reactive.result.method.annotation`**, not the MVC Servlet package.
2. Overriding `handleExceptionInternal` / `createResponseEntity` takes **`ServerWebExchange`** and returns **`Mono<ResponseEntity<Object>>`**, instead of `WebRequest`/`ResponseEntity<Object>`.

In addition:
- Request bodies are read via `HttpMessageReader`/reactive codecs, not Servlet `HttpMessageConverter`s.
- Invalid DTOs typically produce **`WebExchangeBindException`**, not `MethodArgumentNotValidException`.
- Other parse/missing/conversion errors may raise `ServerWebInputException`.
- Method-level validation in Spring WebFlux 6.1+ can produce `HandlerMethodValidationException`.
- Fallback handlers outside annotated controllers may be `ErrorWebExceptionHandler` / `WebExceptionHandler`.
- `WebTestClient` is the proper test client for WebFlux, distinct from MVC's `MockMvc`.

**Never copy MVC advice verbatim into WebFlux and merely swap imports**, because method signatures and return types differ.

### 8.1. Creating a Separate WebFlux Project

Create a standalone Maven project. In `pom.xml`, replace:

~~~xml
<artifactId>api-problems-mvc</artifactId>
~~~

with:

~~~xml
<artifactId>api-problems-webflux</artifactId>
~~~

and replace **only** the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

with:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Keep `spring-boot-starter-validation` and `spring-boot-starter-test`; keep all remaining dependencies and Java version as in the MVC project. Do not leave `spring-boot-starter-web` in the WebFlux project so Spring Boot does not pick the Servlet web stack when both starters are present.

**Reuse verbatim** the stack-independent classes: `CreateItemRequest.java`, `ItemView.java`, `ApiViolation.java`, `ApiProblemFactory.java`, `ItemNotFoundException.java`, and `DuplicateItemException.java` in package `com.example.problems`. Keep `ProblemApplication.java` as the Spring Boot entrypoint; **do not copy** `ItemController.java`/`MvcApiProblemAdvice.java`/`MvcApiProblemTest.java` into the WebFlux project. Replace them with the following classes.

### 8.2. `ReactiveItemController.java`

~~~java
package com.example.problems;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ReactiveItemController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemView>> create(
            @Valid @RequestBody CreateItemRequest input) {

        if ("conflict".equalsIgnoreCase(input.name())) {
            return Mono.error(new DuplicateItemException());
        }

        ItemView view = new ItemView(
                "item-42", input.name(), input.quantity());

        return Mono.just(ResponseEntity
                .status(HttpStatus.CREATED).body(view));
    }

    @GetMapping("/{id}")
    public Mono<ItemView> get(@PathVariable String id) {
        if ("missing".equals(id)) {
            return Mono.error(new ItemNotFoundException());
        }

        return Mono.just(new ItemView(id, "Sample", 2));
    }

    @GetMapping("/search")
    public Mono<ItemView> search(
            @RequestParam("limit") @Min(1) int limit) {
        return Mono.just(
                new ItemView("item-1", "Sample", limit));
    }

    @GetMapping("/explode")
    public Mono<ItemView> explode() {
        return Mono.error(new IllegalStateException(
                "Sensitive internal failure details"));
    }
}
~~~

`Mono.error(...)` emits an error signal in the reactive pipeline. `@Valid @RequestBody CreateItemRequest` illustrates an annotated controller receiving a body DTO. If an endpoint receives `Mono<CreateItemRequest>` instead of the DTO directly, test the exact reactive body validation path and do not blindly mix `Mono<@Valid Dto>` syntax without checking behavior on your chosen Spring version.

### 8.3. `ReactiveApiProblemAdvice.java`

In the WebFlux project, create a file in the same package using **Reactive `ResponseEntityExceptionHandler`**:

~~~java
package com.example.problems;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

import java.util.List;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ReactiveApiProblemAdvice
        extends ResponseEntityExceptionHandler {

    private static final Logger LOG =
            LoggerFactory.getLogger(ReactiveApiProblemAdvice.class);

    private static String path(ServerWebExchange exchange) {
        return exchange.getRequest()
                .getPath().pathWithinApplication().value();
    }

    // Spring WebFlux's protected handler is REACTIVE:
    @Override
    protected Mono<ResponseEntity<Object>> handleExceptionInternal(
            Exception ex,
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            ServerWebExchange exchange) {

        ProblemDetail problem;

        if (ex instanceof WebExchangeBindException bind) {
            List<ApiViolation> violations =
                    bind.getFieldErrors()
                            .stream()
                            .map(FieldError::getField)
                            .distinct()
                            .map(field -> new ApiViolation(
                                    field, "Invalid value"))
                            .toList();

            problem = ApiProblemFactory.create(
                    status, "VALIDATION_FAILED",
                    "One or more fields are invalid.",
                    violations, path(exchange));
        }
        else if (ex instanceof HandlerMethodValidationException method
                && !method.isForReturnValue()) {

            problem = ApiProblemFactory.create(
                    status, "VALIDATION_FAILED",
                    "One or more parameters are invalid.",
                    List.of(new ApiViolation(
                            "parameter", "Invalid value")),
                    path(exchange));
        }
        else {
            // Includes return-value validation (status 500)
            // and all other framework exceptions.
            problem = ApiProblemFactory.create(
                    status,
                    ApiProblemFactory.codeFor(status),
                    ApiProblemFactory.detailFor(status),
                    List.of(),
                    path(exchange));
        }

        // Preserve status and headers chosen by the framework.
        return super.handleExceptionInternal(
                ex, problem, headers, status, exchange);
    }

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ItemNotFoundException ex,
            ServerWebExchange exchange) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(ApiProblemFactory.create(
                        HttpStatus.NOT_FOUND,
                        "RESOURCE_NOT_FOUND",
                        "The requested item was not found.",
                        List.of(),
                        path(exchange)));
    }

    @ExceptionHandler(DuplicateItemException.class)
    public ResponseEntity<ProblemDetail> conflict(
            DuplicateItemException ex,
            ServerWebExchange exchange) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ApiProblemFactory.create(
                        HttpStatus.CONFLICT,
                        "CONFLICT",
                        "An item with this name already exists.",
                        List.of(),
                        path(exchange)));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ProblemDetail> unexpected(
            Exception ex,
            ServerWebExchange exchange) {

        ProblemDetail problem = ApiProblemFactory.create(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "An internal error occurred.",
                List.of(),
                path(exchange));

        Object errorId = problem.getProperties().get("errorId");
        LOG.error("Unexpected reactive API error, errorId={}",
                errorId, ex);

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
~~~

**Notable points:**

- WebFlux's `handleExceptionInternal` method returns **`Mono<ResponseEntity<Object>>`**. In MVC, the counterpart returns `ResponseEntity<Object>` and takes `WebRequest`.
- `WebExchangeBindException#getFieldErrors()` supplies field errors, yet the example returns only safe field name + message without exposing rejected values.
- `HandlerMethodValidationException` for inputs yields 400/`VALIDATION_FAILED`; **return-value** violations branch to status 500/`INTERNAL_ERROR` without exposing internal output.
- Other framework exceptions still pass through `ResponseEntityExceptionHandler`, keeping framework-chosen statuses/headers; the factory supplies the unified contract.
- `@ExceptionHandler` methods for domain/fallback errors can return `ResponseEntity<ProblemDetail>` in annotated WebFlux controllers; not every exception handler must return `Mono` when the response is ready synchronously.
- Uses the same `ApiProblemFactory`, but with **a different pipeline and handler method signatures**.
- Code never blocks the Reactor event loop with JDBC or blocking HTTP calls; if adding logging/enrichment in production, avoid blocking operations inside the reactive chain.
- If errors occur outside annotated controllers or after a response is committed/streaming, `@RestControllerAdvice` still does not cover every case; add a dedicated reactive fallback layer.

### 8.4. Testing WebFlux with `WebTestClient`

Still in the WebFlux project, create `src/test/java/com/example/problems/ReactiveApiProblemTest.java`:

~~~java
package com.example.problems;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveApiProblemTest {

    @Autowired
    WebTestClient client;

    @Test
    void validReactiveCreateReturns201() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"name":"Book","quantity":1}
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Book");
    }

    @Test
    void invalidDtoHasUnifiedValidationCode() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"name":"","quantity":0}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("VALIDATION_FAILED")
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.errorId").isNotEmpty()
                .jsonPath("$.violations").isArray();
    }

    @Test
    void missingItemIs404() {
        client.get()
                .uri("/api/items/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("RESOURCE_NOT_FOUND");
    }

    @Test
    void duplicateItemIs409() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"name":"conflict","quantity":1}
                        """)
                .exchange()
                .expectStatus().isEqualTo(409)
                .expectBody()
                .jsonPath("$.code").isEqualTo("CONFLICT");
    }

    @Test
    void invalidMethodParameterIs400() {
        client.get()
                .uri("/api/items/search?limit=0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("VALIDATION_FAILED");
    }

    @Test
    void unexpectedFailureIsSanitized500() {
        client.get()
                .uri("/api/items/explode")
                .exchange()
                .expectStatus().is5xxServerError()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INTERNAL_ERROR")
                .jsonPath("$.errorId").isNotEmpty();
    }
}
~~~

There are **6 WebTestClient tests**. Run `mvn test` in the separate WebFlux project; they verify the same **public contract**, without reusing `MockMvc` or Servlet-only exception classes. On different WebFlux/Boot versions, verify exact handler invocation and problem JSON against your running server before productionizing.

**Technical note:** JSON bodies passed via `bodyValue(String)` with `Content-Type: application/json` are normally transmitted as a string; in some test configurations, codecs may encode strings through a different converter. If a test environment behaves differently, pass raw JSON bytes:
 
~~~java
.bodyValue(
        "{\"name\":\"Book\",\"quantity\":1}"
                .getBytes(StandardCharsets.UTF_8))
~~~

This snippet requires importing `java.nio.charset.StandardCharsets` and does not change the API contract. Distinguish test-client encoder selection errors from Spring controller errors.

## 9. Preserving HTTP Status and Header Semantics

### 9.1. Header Status and JSON Status Must Match

If the HTTP status line is 400 while the JSON `status` is 500, clients, proxies, and metrics conflict. All sample code creates `ProblemDetail.forStatus(status)` and returns `ResponseEntity` with the **exact same status**.

When using `@ResponseStatus`, `ResponseStatusException`, or `ErrorResponseException`, note that Spring may already have chosen the status and headers. When writing custom handlers, never overwrite them with a generic 500 just because “we are handling an exception”.

### 9.2. 401 and 403 from Spring Security

Spring Security typically handles these in the **filter chain** (Servlet `AuthenticationEntryPoint`/`AccessDeniedHandler`; Reactive `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`), which may **not** reach MVC/WebFlux `@RestControllerAdvice`.

To keep 401/403 uniform, reuse `ApiProblemFactory` or shared serializer logic inside the security handlers, while:
- 401 should include `WWW-Authenticate` per authentication scheme when required.
- 403 preserves lack-of-permission semantics.
- Do not reveal whether a resource exists if policy dictates returning 404 to prevent enumeration.
- Never leak authentication tokens, passwords, or security context into JSON.
- Never strip `WWW-Authenticate` / `Retry-After` just to force a uniform schema.

Obtain `HttpServletRequest#getRequestURI()` / `ServerWebExchange#getRequest().getURI().getPath()` under the same sanitization policy. Never trust unvalidated client-sent `Forwarded`/`X-Forwarded-*` headers.

### 9.3. 405, 406, 415

When a request method is not allowed, the 405 response should preserve the `Allow` header. For an incompatible `Accept` header, 406 may struggle to render a `ProblemDetail` JSON body if the `Accept` header itself disallowed JSON; **do not promise a problem JSON body for every content-negotiation failure**. For 415, preserve the `Content-Type` contract and advertise supported formats. Tests should assert **status first**, and body/schema when the framework can serialize it.

### 9.4. 429 and 503, Retry-After

If the API uses rate limiting or circuit breakers:
- 429: `RATE_LIMITED`, optionally with `Retry-After`.
- 503: `SERVICE_UNAVAILABLE`, also optionally with `Retry-After`.
- 504: gateway timeout at the proxy/gateway layer, not necessarily reaching controller advice.

Never emit `Retry-After` arbitrarily or promise safe retries for **non-idempotent** operations. Document retry semantics and idempotency keys for state-mutating APIs.

## 10. Avoiding Data and Internal Detail Leaks

### Never Return Raw Exception Messages

Wrong:

~~~java
@ExceptionHandler(Exception.class)
ResponseEntity<?> handle(Exception ex) {
    return ResponseEntity.status(500)
            .body(java.util.Map.of(
                    "error", ex.getMessage()));
}
~~~

This is an **anti-pattern** snippet; never use it in production. Exception messages can contain internal URLs, stack fragments, SQL, connection strings, user emails, rejected values, tokens, or column/entity names.

Right: generic 5xx message:

~~~json
{
  "status": 500,
  "code": "INTERNAL_ERROR",
  "detail": "An internal error occurred.",
  "errorId": "59ce42b5-32c9-471e-9c4e-1f4577c6d458",
  "violations": []
}
~~~

This is an abbreviated JSON example showing only custom fields; full `ProblemDetail` also includes `type/title/instance`.

### Never Return Rejected Values

`FieldError#getRejectedValue()` or `ConstraintViolation#getInvalidValue()` may contain secrets. Never serialize raw `BindingResult` or `ConstraintViolationException`. For `@Email`, there is no need to echo the email in the error message; the client already knows what it submitted.

### Field Identifiers Must Belong to the Public Schema

If a request DTO has nested paths such as `address.postalCode`, returning that field name is fine if documented in the API contract. Never expose internal JPA property names or SQL column names. For mass-assignment extra inputs, consider a generic `BAD_REQUEST` code rather than enumerating all server-only field names.

### Server Return-Value Validation Failures

If a controller or service returns output violating a constraint, that is **not a request for the user to fix their form**. Spring MVC's `HandlerMethodValidationException#isForReturnValue()` specifically helps choose 500. Return `violations: []` instead of reflecting the invalid return value.

### Logging and Tracing

- Log full exceptions **only to server logs** with proper access controls and retention.
- Attach `errorId`/trace IDs to logs and metrics, while never embedding secrets or user IDs inside `errorId`.
- Do not log raw JSON request bodies by default to “debug 400 errors”.
- For high-volume 400 validation errors, use aggregate counters/metrics instead of per-request stack traces to prevent log flooding.
- Before logging 5xx errors, consider redacting exception messages in telemetry pipelines if underlying libraries might include PII.

## 11. WebFlux and Reactive-Specific Pitfalls

**`@RestControllerAdvice` applies only to annotated controllers.** For WebFlux functional endpoints (`RouterFunction`/`HandlerFunction`), the same exception resolver path does not apply in all cases. If an application relies heavily on functional routes, consider `WebExceptionHandler`/Boot's `ErrorWebExceptionHandler` or a unified filter/operator policy.

**`onErrorResume` in a service does not fully replace a global handler.** If a service swallows every `Throwable` into `Mono.empty()`, failures can vanish or the API can return misleading 200/404 statuses. Recover only well-defined business exceptions; let other failures propagate to the error layer.

**Never block inside reactive advice.** Avoid blocking JDBC calls, heavy synchronous logging, or blocking remote HTTP requests on the event loop. Trace/error enrichment must be fast and non-blocking.

**Committed responses:** With SSE/Flux streaming, if data has already been emitted before an error occurs, you cannot turn an already-committed response into a fresh `ProblemDetail` with status 500. Design an **in-stream error event contract** or terminate the stream cleanly, and test streaming failure behavior separately.

**Backpressure and payload limits:** A unified error body does not protect the app from oversized request bodies. Configure codec memory limits, gateway limits, upload limits, and collection size validation appropriately.

**Method validation vs argument validation:** WebFlux has both `WebExchangeBindException` and `HandlerMethodValidationException`, depending on method signatures. Class-level `@Validated` on a controller can switch to AOP-based validation; Spring 6.1+ docs recommend removing it when built-in method validation is intended. Never collapse both blindly into one 400 branch.

## 12. Roadmap to a Production Error Contract

A production system needs the following additions beyond the example:

1. **Error code registry** with namespacing/versioning: `VALIDATION_FAILED`, `RESOURCE_NOT_FOUND`, `CONFLICT`, etc., plus public documentation.
2. **`MessageSource`/i18n** for `title`, `detail`, and `violations.message`; keep `code` invariant across locales.
3. **Structured logging** integrating trace IDs, `errorId`, log sampling, and privacy redaction.
4. **Security handlers** for 401/403 in the Servlet filter chain or reactive filter chain.
5. **Boot fallbacks** for errors bypassing advice (Servlet `/error` / `ErrorAttributes` or reactive `ErrorWebExceptionHandler`), sharing the same schema where possible.
6. **CORS headers** on client-visible errors: never let an error handler strip required CORS headers for browser requests.
7. **Rate limiting / gateway** error policies aligning 429/503/504 and `Retry-After`.
8. **Framework-independent contract tests**: assert status, content-type, `code`, `errorId`, `violations` array, `instance`, and absence of secrets.
9. **OpenAPI error schemas**: document `application/problem+json` and statuses per operation; version code fields cleanly.
10. **Observability**: latency, error rates, status distribution, exception categories, and correlation; alert on 5xx, not legitimate 400s.
11. **Client compatibility**: clients handle unknown `code` values by falling back to HTTP status and do not crash when the server adds extension fields.
12. **Authentication/authorization**: never put stack traces or security internals into `ProblemDetail`, and never mask 401/403 as 500.
13. **Proxy/timeout testing**: ensure statuses and bodies are not unexpectedly rewritten in transit.
14. **Data minimization**: 500 responses and validation outputs leak zero secrets/PII, including inside localized messages.
15. **Transactions**: a 500 caused by a return-value violation does not automatically guarantee rollback; test side effects and idempotency.

### Two Ways to Organize Code When Microservices Use Both MVC and WebFlux

- **Contract/framework-neutral module**: `ApiViolation` record, `ApiProblemFactory`, error codes, and conventions using Spring's `ProblemDetail` from `spring-web` or a standalone DTO if needed.
- **MVC adapter**: Servlet `ResponseEntityExceptionHandler`, `WebRequest`, `MockMvc`, Servlet security entry points.
- **WebFlux adapter**: Reactive `ResponseEntityExceptionHandler`, `ServerWebExchange`, `Mono<ResponseEntity<?>>`, `WebTestClient`, reactive security entry points.
- **Shared contract tests**: each adapter must emit the identical JSON shape and code mapping.
- **Do not share a single exception-handler class** between Servlet and Reactive, as their signatures differ.

## 13. Common Mistakes, Symptoms, and Fixes

| Anti-pattern | Symptom | Proper fix |
| --- | --- | --- |
| Each controller returns ad-hoc `Map.of("error", ...)` | Inconsistent response shapes | Use `ProblemDetail` and global advice. |
| Catch `Exception.class` and return 400 | DB/return-value errors look like client errors | Classify business/validation separately, fallback 500. |
| Catch all errors and return 500 | Invalid JSON input returns 500 | Use framework exception handler and map 400/415/405,... |
| Put `ex.getMessage()` in public `detail` | Leaks SQL/tokens/internal URLs | Return safe detail, log exception internally. |
| Return `FieldError#getRejectedValue()` | Leaks PII/passwords | Return only field + public message/code. |
| Client branches on localized `detail` | Clients break when translations change | Keep `code` stable, localize messages separately. |
| `ProblemDetail.status` differs from HTTP status | Proxies/clients behave inconsistently | Construct from the same `HttpStatusCode` and assert both. |
| Override Spring handler with duplicate `@ExceptionHandler` | Ambiguous mapping or misconfiguration | Override protected methods on `ResponseEntityExceptionHandler`. |
| Port MVC handler to WebFlux by swapping only imports | Compile/signature errors, broken reactive behavior | Write a dedicated adapter with `ServerWebExchange` and `Mono`. |
| Use `MockMvc` to test WebFlux controllers | Wrong web stack | Use `WebTestClient`. |
| Include both `web` and `webflux` starters in demo | Spring Boot may pick the MVC stack | Pick one stack explicitly or configure intentionally. |
| Add `@Validated` on controller ignoring method validation | Exception pipeline shifts | With Spring 6.1+, use built-in method validation as designed. |
| Map every `ConstraintViolationException` to 400 | Server return-value error becomes 400 | Distinguish boundaries and input vs return status. |
| Overwrite all `HttpHeaders` with empty headers | Drops `Allow`, `WWW-Authenticate`, `Retry-After` | Preserve original headers and add deliberately. |
| Confuse domain 404 with static/gateway 404 | Inconsistent schema across paths | Test `/error`/gateway fallbacks separately. |
| Assume advice catches all Servlet filter/Security errors | 401/403 returns different JSON | Integrate security exception handlers. |
| Mutate error body after response committed | Cannot change streaming status/body | Design a streaming error protocol. |
| Emit random UUID without logging it | Cannot trace incidents | Log alongside `errorId` or wire real trace IDs. |
| Log full requests on every validation error | Leaks private user data | Redact, emit structured events, sample. |
| Error body with huge `violations` array | Bloated responses, DoS/log flood | Cap and document error list length. |
| Skip contract-testing 406/415/405 | Broken content negotiation/headers | Test status/headers, and body when serializable. |

## 14. Acceptance Checklist

- [ ] Error API uses RFC 9457 `ProblemDetail` with media type `application/problem+json` when negotiable.
- [ ] HTTP status matches `ProblemDetail.status`.
- [ ] `type/title/status/detail/instance` are meaningful and contain no secrets.
- [ ] Extension `code` is present and stable, independent of locale.
- [ ] Extension `errorId` is unique/correlatable and logged with 5xx errors.
- [ ] `violations` is an array leaking no rejected values; fields come only from the public input contract.
- [ ] Individual DTO validation maps to 400/`VALIDATION_FAILED`.
- [ ] Direct method input validation maps to 400; return-value violations map to 500.
- [ ] Malformed JSON/body maps to 400 with a safe message.
- [ ] Type mismatches and missing query/header/body map to 400 per contract.
- [ ] Domain not found maps to 404, conflict to 409; avoid catching generic exceptions arbitrarily.
- [ ] Unsupported method returns 405 with `Allow` header preserved.
- [ ] Unsupported media type returns 415; `Accept` mismatch 406 is tested within content-negotiation limits.
- [ ] Unexpected backend exceptions map to 500 without exposing stack traces/messages in JSON.
- [ ] Only **one** runtime web stack is selected per app: MVC or WebFlux.
- [ ] MVC advice extends Servlet `ResponseEntityExceptionHandler`; WebFlux uses its Reactive counterpart.
- [ ] Unit/MockMvc or WebTestClient tests exercise real error branches.
- [ ] 401/403 from Spring Security are handled at the proper filter layer.
- [ ] Fallback `/error`/`ErrorWebExceptionHandler`/gateway share a consistent contract as far as possible.
- [ ] Logs and metrics use trace/error IDs with privacy controls and never log raw payloads.
- [ ] An i18n plan exists for `detail` and messages if the product requires multiple languages.
- [ ] `ProblemDetail` is not guaranteed for already-committed/in-flight streaming responses.
- [ ] Spring Boot/Framework dependencies stay on supported branches with security advisories applied.
- [ ] API docs/OpenAPI document errors, media types, codes, fields, and retry behavior.
- [ ] Negative contract tests are re-run whenever validation annotations or error handlers change.

**Conclusion:** A solid error contract is far more than “every error has a `message` field”. Use **RFC 9457 `ProblemDetail`** with consistent **`code`**, **`errorId`**, and **`violations`**, preserve HTTP statuses and headers, and build dedicated adapters for **Spring MVC** and **Spring WebFlux**. Unit/HTTP tests must prove input validation returns 400, return-value violations return 500, domain errors return 404/409, parse errors return 400, media type errors return 415, and unexpected failures return 500. In real systems, integrate Spring Security, fallback handlers, tracing, and gateways to achieve true consistency across the entire request lifecycle.

## References

- Spring Framework 6.2 Reference — **MVC Error Responses, RFC 9457, `ProblemDetail`/`ResponseEntityExceptionHandler`**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 Reference — **WebFlux Error Responses**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.2 Reference — **MVC Handler Method Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 Reference — **WebFlux Handler Method Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2 Javadoc — **MVC ResponseEntityExceptionHandler**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.2 Javadoc — **WebFlux ResponseEntityExceptionHandler**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.2 Javadoc — **HandlerMethodValidationException**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- RFC 9457 — **Problem Details for HTTP APIs**: https://www.rfc-editor.org/rfc/rfc9457.html
- Spring Boot Reference — **Error Handling, Problem Details**: https://docs.spring.io/spring-boot/reference/web/servlet.html
