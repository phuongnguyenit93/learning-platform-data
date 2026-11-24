# Testing Invalid Input, Problem Details, and Default Error Responses

## 1. Objective: An API Must Be Right Beyond Valid Data

In **Web runtime testing** of **Spring Boot - web-runtime**, an endpoint may work properly on the happy path yet still deliver a confusing or dangerous experience when clients send invalid data: malformed JSON, wrong data types, missing bodies, blank fields, out-of-range query parameters, wrong HTTP methods, incompatible `Content-Type`/`Accept`, or unexpected internal errors.

This lesson addresses three distinct questions:

1. **What data must be rejected?** Distinguish JSON syntax errors, type conversion errors, missing fields/queries, Jakarta Bean Validation constraint violations, domain rule errors, and unexpected server failures.
2. **What is the HTTP response contract?** Status 400/404/405/406/409/415/422/500; media type **`application/problem+json`**, RFC 9457 fields; and differences from Spring Boot's default JSON error payload.
3. **Which layer should be tested to trust the result?** Use **MockMvc/`@WebMvcTest`** for MVC validation and exception advice, and **`@SpringBootTest(RANDOM_PORT)`** for Servlet container error dispatch and **`BasicErrorController /error`**. Do not infer default error bodies from MockMvc if no real servlet container is running.

Target outcome: write repeatable negative tests, avoid asserting brittle internal messages, understand why Problem Details does not cover every error source, and prevent leaking stack traces, credentials, or user data.

Examples use **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1, Spring MVC/Servlet, Jakarta Validation, JUnit Jupiter, and MockMvc**. Spring WebFlux uses a different `WebTestClient`/reactive exception model; do not copy `spring.mvc` configuration verbatim to WebFlux.

## 2. Which Layers Does an Invalid Request Traverse?

~~~text
HTTP client
    |
    v
TCP / Reverse Proxy / Servlet Filters / Spring Security
    |
    v
DispatcherServlet
    |
    +--- Handler mapping: path, method, consumes, produces
    |
    +--- Parameter binding & type conversion
    |
    +--- HttpMessageConverter: read JSON body
    |
    +--- Jakarta Bean Validation: @Valid, @Min, @NotBlank...
    |
    +--- Controller -> service -> domain rule
    |
    v
Response / Exception
    |
    +--- @ExceptionHandler in @RestControllerAdvice
    |
    +--- MVC HandlerExceptionResolver / Boot Problem Details advice
    |
    +--- Servlet error dispatch -> Boot /error (BasicErrorController)
    |
    v
HTTP status + Content-Type + JSON/HTML body
~~~

The path **depends on the error type and configuration**. For example, a missing request body may be rejected **before the Controller is called**. A business exception can be converted by `@RestControllerAdvice` into a `ProblemDetail`. An unhandled unexpected runtime exception can be routed through the Servlet container's **`/error`** mechanism.

**There is no default rule that “every 4xx/5xx error shares the exact same JSON schema.”** To achieve a uniform contract, teams must intentionally design, test, and configure boundaries that lie outside the Controller as well.

## 3. Matrix of Invalid Inputs and Expected HTTP Statuses to Test

| Case | Typical Detection Point | Typically Appropriate Status |
| --- | --- | --- |
| Malformed JSON body | Jackson/`HttpMessageConverter` | 400 Bad Request |
| Valid JSON syntax yet `age` is a string that cannot convert to `Integer` | Jackson deserialization/type mismatch | 400 |
| Missing required body with `@RequestBody` | Request body resolver | 400 |
| `@NotBlank`, `@Email`, `@Min` violated on `@Valid` DTO | Bean Validation | 400 in default Spring MVC |
| Required `@RequestParam` query missing | Argument resolver | 400 |
| `@RequestParam`/`@PathVariable` cannot convert type | Type conversion/binding | 400 |
| Direct constraint `@Min`/`@Max` on method parameter | Method validation | 400 for input |
| Non-existent route | Handler mapping/static resource | 404 Not Found |
| Valid resource ID not found | Domain/service | 404 per API contract |
| Unsupported HTTP method | Handler mapping | 405 Method Not Allowed |
| Client requests unrepresentable `Accept` media type | Content negotiation | 406 Not Acceptable |
| Unsupported request `Content-Type` | `consumes` condition/converter | 415 Unsupported Media Type |
| Email already taken or state conflict | Domain rule | 409 Conflict |
| Syntactically valid payload unprocessable by domain rules | Custom API design | Can be 422 Unprocessable Content |
| Missing/invalid authentication credentials | Spring Security filter/entry point | 401 Unauthorized |
| Authenticated yet unauthorized | `AccessDeniedHandler`/method security | 403 Forbidden |
| Unmapped unexpected exception, bug, database unavailable | Server error | 500 or appropriate 5xx |
| Gateway timeout calling service | Reverse proxy | 504 Gateway Timeout |

**Do not assume every Bean Validation failure is 422.** In Spring MVC, `@Valid` request DTO failures normally return **400**. Only choose 422 if the API contract genuinely distinguishes “syntactically valid content that cannot be processed” and defines custom exception mapping.

**Do not turn every runtime error into HTTP 400.** Server bugs must be 5xx so clients do not think modifying their payload can fix them. Conversely, user input errors should not become 500 merely because an exception handler is missing.

### 3.1. HTTP Status and Body Are Two Independent Dimensions

A response can return **HTTP 400** while its body is Boot's default JSON, `ProblemDetail` JSON, HTML, or empty, depending on the stack and content negotiation. Tests must assert:
- Right status.
- Right `Content-Type` per API contract.
- Stable fields, especially **`status`, `type`, `code`** when present.
- No sensitive data present.
- Clients can distinguish fixable/retryable errors from non-retryable ones.

Do not write **`andExpect(status().isBadRequest())`** alone and assume the error payload is right too.

## 4. Jakarta Bean Validation: Using Annotations Correctly

To use Jakarta Bean Validation in Spring Boot 3.3, add the **`spring-boot-starter-validation`** dependency. Do not assume `starter-web` always includes full Hibernate Validator in every version.

Common annotations:
- **`@NotNull`:** value must not be null; allows empty strings.
- **`@NotBlank`:** `CharSequence` is not null and has at least one non-whitespace character; good for names/emails.
- **`@NotEmpty`:** not null/empty for `String`/`Collection`/`Map`/`Array`; differs from `NotBlank`.
- **`@Email`:** validates email format via validator; may permit null, so combine with `@NotBlank` when required.
- **`@Size(min,max)`:** `String` length/`Collection` size, not integer numeric bounds.
- **`@Min`/`@Max`:** numeric bounds; do not put them on `String` as a substitute for `@Size`.
- **`@Positive`/`@PositiveOrZero`:** numeric sign constraints.
- **`@Pattern`:** regex for `String`; validate policies and avoid complex regexes vulnerable to ReDoS.
- **`@Valid`:** triggers validation on an object/nested fields; `@Valid` itself is not a constraint.
- **`@Validated`:** supports validation groups and certain method validation setups; not always needed on an MVC Controller.

In Spring Framework 6.1, there are two important validation paths:
1. **`MethodArgumentNotValidException`:** typically raised when **`@Valid @RequestBody` DTO** or `@ModelAttribute`/`@RequestPart` violates constraints without an immediate `BindingResult`/`Errors` parameter.
2. **`HandlerMethodValidationException`:** typically raised when constraints are **placed directly on method parameters** such as `@Min @RequestParam` or `@Min @PathVariable`; Spring MVC built-in method validation checks the method signature directly.

**Common pitfall:** putting **`@Validated` on the Controller class** can route validation through an AOP method-validation proxy instead of MVC 6.1's built-in mechanism. According to Spring Framework docs, to use MVC 6.1 built-in method validation, **omit class-level `@Validated`** when not needed. Actual exceptions may vary by configuration; test against the real project.

### 4.1. Failing Early at Deserialization

JSON like:

~~~json
{"fullName":"Ada","email":"ada@example.test","age":"not-a-number"}
~~~

can fail before Bean Validation, because Jackson cannot convert **`not-a-number`** into an `Integer`. Do not expect a `FieldError` from `@Min` in this case. HTTP message conversion throws **`HttpMessageNotReadableException`**, which requires its own test.

If the JSON body is missing altogether, `@RequestBody` defaults to **`required=true`** and also yields HTTP 400 before the Controller. If the JSON is valid with `age: null`, **`@NotNull`** catches it in Bean Validation.

### 4.2. BindingResult Can Alter Error Routing

A Controller accepting **`@Valid @RequestBody DTO dto, BindingResult errors`** immediately after the DTO handles errors itself rather than throwing `MethodArgumentNotValidException` as above. If used, you must check `errors.hasErrors()` and return the proper HTTP status/body yourself. Never add `BindingResult` and ignore errors, letting invalid payloads enter business logic.

## 5. What Is RFC 9457 Problem Details?

**Problem Details for HTTP APIs (RFC 9457)** provides a standard representation for HTTP errors. Spring Framework provides **`org.springframework.http.ProblemDetail`** and **`org.springframework.web.ErrorResponse`**.

An example of **`application/problem+json`**:

~~~json
{
  "type": "https://errors.example.test/problems/invalid-input",
  "title": "Invalid input",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "instance": "/api/accounts",
  "code": "VALIDATION_FAILED",
  "violations": [
    {"field":"age","constraint":"Min"},
    {"field":"email","constraint":"Email"}
  ]
}
~~~

Five standard members:
- **`type`:** URI identifying the problem type; defaults to **`about:blank`**. Custom type URIs should be stable, ideally backed by contract documentation.
- **`title`:** short human-readable summary of the *problem type*, not a stack trace.
- **`status`:** HTTP status code for this occurrence.
- **`detail`:** client-facing explanation, free of SQL, secrets, or internal exception details.
- **`instance`:** URI identifying the occurrence/path; Spring MVC can derive it from the request path when unset.

**`code`** and **`violations`** are **extension fields**, not among the five standard RFC fields. Spring supports **`ProblemDetail.setProperty(...)`** and Jackson includes a mixin to flatten these properties to top-level JSON. Clients should rely on **stable `type` or `code`**, rather than parsing `detail` prose.

**`application/problem+json`** differs from **`application/json`** in media type and semantics. When testing `ProblemDetail`, use **`contentTypeCompatibleWith(application/problem+json)`** instead of assuming fixed charsets or parameter ordering.

### 5.1. HTTP Status Must Match ProblemDetail.status

**`ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, ...)`** creates a body with status 400. When Spring MVC returns a `ProblemDetail` from `@ExceptionHandler`, the framework uses that status for the response when supported. Avoid returning a body saying status 400 inside a 500 response, which misleads clients, metrics, and caches.

### 5.2. Do Not Overuse Extension Fields

Helpful extension fields:
- **`code`:** machine-readable, e.g., `EMAIL_CONFLICT` or `INVALID_JSON`.
- **`violations`:** filtered, normalized list of field/constraint names, bounded in size.
- **`traceId`:** non-credential correlation ID, usable when policy permits.

Do not echo the user's **`rejectedValue`** by default in responses: passwords, refresh tokens, addresses, account numbers, or huge HTML/JSON payloads can leak via errors. Never return raw exception messages, class names, stack traces, or database diagnostics.

### 5.3. Do Not Assume 404/500 Are Always Problem Details

**`ProblemDetail`** is one error representation, not a guarantee that every error source in the app uses it. Responses produced by MVC exception resolvers may be `ProblemDetail`, whereas uncaught failures can route through **`BasicErrorController /error`** and return default JSON. The system may also return HTML when a client sends `Accept: text/html`.

To achieve one consistent schema across all boundaries (including security filters and proxy errors), dedicated architecture/error handlers and HTTP-level tests are needed.

## 6. Spring Boot 3.3: Enabling Problem Details and Distinguishing /error

In Spring Boot 3.3, the property:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

enables auto-configuration supporting RFC 9457 for many **Spring MVC `ErrorResponse` exceptions**. **The default value of `spring.mvc.problemdetails.enabled` in Spring Boot 3.3.13 is `false`.** Do not assume new projects enable Problem Details by default.

Spring Boot provides the default Servlet error mechanism:
- **`/error`** is the mapping used when the container dispatches an error.
- **`BasicErrorController`** typically returns JSON for machine clients and error HTML/whitelabel for browser clients.
- **`ErrorAttributes`** determines what data is placed in the body.
- **`server.error.*`** settings restrict message, binding errors, exception, and stack trace fields.

### 6.1. Example Default `/error` Response

When a request hits `BasicErrorController` with HTTP 404/500, JSON may look like:

~~~json
{
  "timestamp": "2026-01-01T00:00:00.000+00:00",
  "status": 404,
  "error": "Not Found",
  "path": "/does-not-exist"
}
~~~

This is an **illustrative sample**, not exact JSON output for every request. Timestamps vary; content negotiation, error properties, and Spring Boot versions can change the field set.

### 6.2. Controlling Sensitive Data in Default Errors

With Spring Boot 3.3:

~~~yaml
server:
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false
    include-path: always
~~~

The defaults in 3.3 correspond to **`include-message=never`**, **`include-binding-errors=never`**, **`include-stacktrace=never`**, **`include-exception=false`**, **`include-path=always`**; the lab declares them explicitly for clarity. **Never set `always` on message/stacktrace just for easier testing**, especially in production. If an environment leaks raw exceptions in JSON, that is a security flaw.

**`server.error.path`** defaults to **`/error`**. Do not call that endpoint directly expecting to reproduce a full Servlet error dispatch with error attributes; trigger a real error through the container.

### 6.3. Do Not Treat /error and @RestControllerAdvice as the Same Layer

**`@RestControllerAdvice`** handles exceptions passing through MVC exception resolution. **`BasicErrorController`** handles Servlet error dispatches or errors unhandled at the MVC level. An overly broad **`@ExceptionHandler(Exception.class)`** can shadow `/error` and force every error—including unexpected bugs—into one generic JSON response; written carelessly, it turns 500s into 400s.

**Spring Security** handles exceptions in its filter chain (`AuthenticationEntryPoint`, `AccessDeniedHandler`). `@RestControllerAdvice` does not automatically catch all filter-level 401/403 errors because many occur **before `DispatcherServlet`**.

## 7. 404 Rules and Static Resources in Spring Boot 3.3

An important distinction when testing 404s: **Spring Boot normally maps static resources to `/**`**. For requests to non-existent routes, `HandlerMapping` may pick `ResourceHttpRequestHandler`, which then throws **`NoResourceFoundException`** rather than **`NoHandlerFoundException`**.

Per Boot 3.3 docs, if you want unmatched routes to go through **`NoHandlerFoundException`**, you can set:

~~~yaml
spring:
  web:
    resources:
      add-mappings: false
~~~

This configuration **disables automatic static resource serving**. Only use it if the application is a pure API serving no static files, as in the lab. If the app serves frontend assets, Swagger UI, or static content, do not toggle it carelessly just to change the exception class.

Test the **HTTP 404 status and error contract**, rather than locking every test to one exception type, because static mappings/configurations can change. Notably, **MockMvc does not execute servlet container error-page dispatch like a real server**.

## 8. Testing Strategy: Layers to Cover

| Test Type | Tools | Tests Well | Limitations to Remember |
| --- | --- | --- | --- |
| Unit validator/service | JUnit, Validator | Business rules, constraints | No HTTP status/body/mapping |
| MVC slice | `@WebMvcTest` + MockMvc | Routing, JSON parsing, validation, exception advice | Does not start embedded HTTP server |
| MVC mocked full context | `@SpringBootTest` + `@AutoConfigureMockMvc` | MVC pipeline with many real beans | Still no real servlet container network/error-page handling |
| HTTP integration | `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate` | Tomcat, serialization, `/error`, real status/headers | Slower than slices, uses random port |
| End-to-end | Real client through gateway | CORS, Security, ingress, proxy mapping | Environment dependent, requires test data isolation |
| Contract testing | Consumer/provider contract | Stable types/statuses/schemas across services | Requires agreement and versioning |

**Recommendation:** write plenty of MVC slice tests for input permutations; add a few integration tests verifying default **`/error`** and container behavior; add security tests if the project defines `AuthenticationEntryPoint`/`AccessDeniedHandler`; reserve full E2E for critical boundaries.

### 8.1. What to Test, What Not to Test?

Good:
- HTTP status, media type, and machine-readable `code`/`type`.
- Field violations for invalid input without leaking raw input values.
- Invalid input never invokes the service/save (with mocked collaborators).
- HTTP 500 leaks no message/stack trace.
- Missing routes, wrong methods, unsupported `Content-Type` and `Accept`.
- 401/403 handled at the right security boundary.
- Errors remain consistent across key environments/configurations.

Avoid:
- Asserting fixed timestamps.
- Asserting JSON field order or uncontracted ordering of field errors.
- Asserting raw prose of default exception `detail` that varies with locale/version.
- Using `@WebMvcTest` to claim full coverage of embedded servlet container `/error`.
- Setting `server.error.include-stacktrace=always` just to make snapshot tests “easier.”

## 9. Runnable Java 17 Maven Demo: One API and Two Error Paths

The demo intentionally includes:
- **`POST /api/accounts`** taking **`@Valid @RequestBody`**.
- **`GET /api/accounts/{id}`** with **`@Min`** on a path parameter, demonstrating `HandlerMethodValidationException`.
- **`GET /api/accounts/search?q=...&limit=...`** with required query param and `@Min`/`@Max`.
- Custom domain 404 and 409 returning **`ProblemDetail`** with stable codes.
- `@RestControllerAdvice` handling **`MethodArgumentNotValidException`** and **`HttpMessageNotReadableException`** into `ProblemDetail` without leaking input.
- **`GET /api/boom`** throwing an unexpected unhandled exception; tested over real HTTP to observe Spring Boot's **`/error`** mechanism.

No database is used so the exercise stays focused on the web runtime. No real accounts are created; id 42 and sample data exist purely to test the HTTP contract.

### 9.1. Directory Structure

~~~text
invalid-input-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/errorlab/
    │   │   └── ErrorLabApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/errorlab/
            ├── AccountMvcTest.java
            ├── DefaultErrorHttpTest.java
            └── LegacyDefaultErrorHttpTest.java
~~~

### 9.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>invalid-input-lab</artifactId>
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

**`spring-boot-starter-validation`** is required for `@NotBlank`/`@Email`/`@Min` constraints to work as expected. **`spring-boot-starter-test`** brings JUnit Jupiter, MockMvc/Spring Test, AssertJ, and Hamcrest under Boot dependency management.

### 9.3. application.yml

**src/main/resources/application.yml:**

~~~yaml
server:
  port: 8080
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false
    include-path: always

spring:
  mvc:
    problemdetails:
      enabled: true
  web:
    resources:
      add-mappings: false
~~~

This configuration selects **Problem Details for MVC framework exceptions** in the lab's main mode, keeps **`/error`** safe, and disables static mappings so missing routes follow one predictable path. This is a pure API lab with no static assets.

**To observe default mode when Problem Details is disabled**, the final test overrides **`spring.mvc.problemdetails.enabled=false`** on a separate test context. Do not edit `application.yml` for the other tests.

### 9.4. Single Java File Containing App, DTOs, Controllers, and Advice

**src/main/java/com/example/errorlab/ErrorLabApplication.java:**

~~~java
package com.example.errorlab;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class ErrorLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorLabApplication.class, args);
    }
}

record CreateAccountRequest(
        @NotBlank @Size(max = 40) String fullName,
        @NotBlank @Email String email,
        @NotNull @Min(18) Integer age
) {}

record AccountResponse(long id, String fullName, String email, int age) {}

class DuplicateEmailException extends RuntimeException {}

class AccountNotFoundException extends RuntimeException {}

@RestController
@RequestMapping("/api/accounts")
class AccountController {

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<AccountResponse> create(
            @Valid @RequestBody CreateAccountRequest request
    ) {
        if ("taken@example.test".equalsIgnoreCase(request.email())) {
            throw new DuplicateEmailException();
        }

        AccountResponse response = new AccountResponse(
                42L, request.fullName(), request.email(), request.age()
        );
        return ResponseEntity
                .created(URI.create("/api/accounts/42"))
                .body(response);
    }

    @GetMapping(
        path = "/search",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Map<String, Object> search(
            @RequestParam("q") String q,
            @RequestParam("limit") @Min(1) @Max(50) int limit
    ) {
        return Map.of("q", q, "limit", limit);
    }

    // Do not use class-level @Validated: MVC 6.1 has method validation.
    @GetMapping(
        path = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    AccountResponse get(@PathVariable("id") @Min(1) long id) {
        if (id != 42L) {
            throw new AccountNotFoundException();
        }
        return new AccountResponse(
                42L, "Ada", "ada@example.test", 23
        );
    }
}

@RestController
class UnhandledFailureController {
    @GetMapping("/api/boom")
    String boom() {
        throw new IllegalStateException("internal diagnostic - do not expose");
    }
}

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
class ApiProblemAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail onBodyValidation(MethodArgumentNotValidException ex) {
        ProblemDetail p = problem(
                HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED",
                "Invalid input",
                "One or more request fields are invalid.",
                "invalid-input"
        );

        List<Map<String, String>> issues =
                ex.getBindingResult().getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "constraint",
                            error.getCode() == null
                                ? "INVALID" : error.getCode()
                    ))
                    .sorted(Comparator.comparing(m -> m.get("field")))
                    .toList();

        // Only expose field and constraint; never echo rejectedValue.
        p.setProperty("violations", issues);
        return p;
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ProblemDetail onUnreadableJson(
            HttpMessageNotReadableException ex
    ) {
        return problem(
                HttpStatus.BAD_REQUEST,
                "INVALID_JSON",
                "Invalid JSON",
                "Request body is missing or cannot be read as JSON.",
                "invalid-json"
        );
    }

    @ExceptionHandler(DuplicateEmailException.class)
    ProblemDetail onDuplicate(DuplicateEmailException ex) {
        return problem(
                HttpStatus.CONFLICT,
                "EMAIL_CONFLICT",
                "Email conflict",
                "An account with this email already exists.",
                "email-conflict"
        );
    }

    @ExceptionHandler(AccountNotFoundException.class)
    ProblemDetail onMissing(AccountNotFoundException ex) {
        return problem(
                HttpStatus.NOT_FOUND,
                "ACCOUNT_NOT_FOUND",
                "Account not found",
                "The requested account is not available.",
                "account-not-found"
        );
    }

    private static ProblemDetail problem(
            HttpStatus status,
            String code,
            String title,
            String detail,
            String typeSlug
    ) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(status, detail);
        p.setTitle(title);
        p.setType(URI.create(
                "https://errors.example.test/problems/" + typeSlug
        ));
        p.setProperty("code", code);
        return p;
    }
}
~~~

### 9.5. Explaining Key Parts of the Code

1. **`CreateAccountRequest`** is a Java record whose three fields `fullName`/`email`/`age` carry Jakarta Validation constraints. **`@Valid @RequestBody`** triggers MVC validation after JSON deserializes into the DTO.
2. **`age` is `Integer` + `@NotNull @Min(18)`**: null/missing fields are caught by validation; strings that cannot parse into `Integer` are handled earlier by Jackson and follow the JSON error path.
3. **`@Email`** does not verify the address actually exists and may permit null per validator rules; `@NotBlank` makes email required.
4. **`@Min`/`@Max`** directly on `search` `limit` and path `id` trigger **MVC 6.1 method validation**; invalid inputs can throw **`HandlerMethodValidationException`** handled by Boot's Problem Details resolver when enabled.
5. **`POST /api/accounts`** returns 201 and `Location /api/accounts/42` when valid; this is a lab with no database and creates no persistent records.
6. **Email `taken@example.test`** triggers business conflict error 409. Other valid emails return 201 in the lab.
7. **`GET /api/accounts/42`** succeeds; GET any other positive ID returns a domain 404 `ProblemDetail`; `GET /api/accounts/abc` yields a 400 type conversion error.
8. **`GET /api/accounts/search`** requires `q` and `limit`; `limit=0` or `51` triggers method constraints.
9. **`@RestControllerAdvice @Order(HIGHEST_PRECEDENCE)`** prioritizes explicitly defined exception handlers over Boot's Problem Details advice for built-in MVC exceptions. It does not catch `Exception.class`, so unexpected runtime errors still route to `/error`.
10. **`onBodyValidation`** returns only field/constraint codes, **without echoing `rejectedValue`**. The list is sorted by field name for predictable contract checks; depending on annotations and Hibernate Validator, one field can produce multiple violations.
11. **`onUnreadableJson`** does not return raw Jackson exceptions, failing byte offsets, or fields holding secrets.
12. **`ProblemDetail.setProperty("code", ...)`** adds a machine-readable extension. Type URIs use the **`example.test`** domain purely for illustration, not a real production address.
13. **`UnhandledFailureController`** intentionally throws `IllegalStateException` to test default error handling and `/error` security. Never copy `/api/boom` into a real app.
14. Spring Security is omitted from `pom.xml` to avoid altering negative test semantics; when adding security later, test filter 401/403 separately.

**Security:** do not place `fullName`/`email` inside default exception messages or public logs; values returned in the happy path response are illustrative only. Production requires input size limits, redaction, auditing, masking, and data protection.

## 10. MockMvc Slice Test: Checking Invalid Inputs and Problem Details

**src/test/java/com/example/errorlab/AccountMvcTest.java:**

~~~java
package com.example.errorlab;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(
        controllers = AccountController.class,
        properties = "spring.mvc.problemdetails.enabled=true"
)
class AccountMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validPostCreatesResource() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"fullName":"Ada",
                     "email":"ada@example.test",
                     "age":23}
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    "Location", "/api/accounts/42"
            ))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.fullName").value("Ada"));
    }

    @Test
    void invalidFieldsUseSafeProblemDetail() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json"))
                .content("""
                    {"fullName":" ",
                     "email":"not-an-email",
                     "age":16}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.valueOf("application/problem+json")
            ))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[*].field",
                    hasItems("fullName", "email", "age")));
    }

    @Test
    void malformedJsonIsNotBeanValidation() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json"))
                .content("{broken"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"))
            .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void missingRequiredBodyIsAlsoAClientError() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void jsonTypeMismatchIsNotAFieldConstraintError()
            throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json"))
                .content("""
                    {"fullName":"Ada",
                     "email":"ada@example.test",
                     "age":"not-a-number"}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void duplicateEmailHasBusinessConflictCode() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json"))
                .content("""
                    {"fullName":"Ada",
                     "email":"taken@example.test",
                     "age":23}
                    """))
            .andExpect(status().isConflict())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.valueOf("application/problem+json")
            ))
            .andExpect(jsonPath("$.status").value(409))
            .andExpect(jsonPath("$.code").value("EMAIL_CONFLICT"));
    }

    @Test
    void unknownAccountReturnsDomainNotFound() throws Exception {
        mvc.perform(get("/api/accounts/99")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code")
                    .value("ACCOUNT_NOT_FOUND"));
    }

    @Test
    void pathVariableTypeMismatchReturns400() throws Exception {
        mvc.perform(get("/api/accounts/not-a-number")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void pathConstraintReturns400() throws Exception {
        mvc.perform(get("/api/accounts/0")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredQueryReturns400() throws Exception {
        mvc.perform(get("/api/accounts/search")
                .param("limit", "10")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void queryConstraintReturns400() throws Exception {
        mvc.perform(get("/api/accounts/search")
                .param("q", "ada")
                .param("limit", "0")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unsupportedRequestContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.TEXT_PLAIN)
                .content("not JSON"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void wrongHttpMethodReturns405() throws Exception {
        mvc.perform(put("/api/accounts/42"))
            .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void unrepresentableAcceptReturns406() throws Exception {
        mvc.perform(get("/api/accounts/42")
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
    }
}
~~~

### 10.1. What Are the Tests Verifying?

- **`201 validPost`**: baseline showing the Controller, Jackson, and DTO work properly. If the happy path breaks, negative tests are hard to trust.
- **`400 invalidFields`**: `MethodArgumentNotValidException` is converted by advice into a `ProblemDetail` with **`VALIDATION_FAILED`** and top-level field violations without exposing rejected values.
- **`400 malformed/missing/type mismatch`**: HTTP message conversion errors are handled distinctly from Bean Validation; clients know to fix JSON/body syntax rather than business rules.
- **`409 conflict`**: domain error with a code distinct from 400 and not 500.
- **`404 domain not found`**: valid ID yet missing resource; distinct from a non-existent route.
- **`400 path type/constraint`**: type conversion vs direct validation on the method signature.
- **`400 missing query/limit=0`**: tests required `@RequestParam` and `@Min`.
- **`415`**: request `Content-Type` does not match `consumes`.
- **`405`**: path has a route yet the HTTP method is disallowed.
- **`406`**: `Accept` has no representation supported by the endpoint.

**Do not assert exact default Spring `detail` sentences** on 405/406/param errors. Translations, message sources, Java runtimes, and Spring minor versions may differ; these tests prioritize stable statuses. For app-defined errors, `code` is the API contract and is asserted explicitly.

### 10.2. Why Use contentTypeCompatibleWith?

The media type of `ProblemDetail` is **`application/problem+json`**; it may carry parameters and depends on content negotiation. **`contentTypeCompatibleWith`** checks compatible media types without locking down unnecessary serialization details. Do not compare raw JSON strings because property order, whitespace, and `instance` URI can vary.

### 10.3. What Does @WebMvcTest Include Automatically?

Spring Boot 3.3 **`@WebMvcTest(AccountController.class)`** builds only the MVC slice, including MVC infrastructure, Jackson/validation support, and relevant **`@ControllerAdvice`** beans; it does not build all repositories, external clients, or services outside the slice. Because the lab's Controller has no service dependency, no `@MockBean` is needed.

In real projects, if `AccountController` injects `AccountService`, use **`@MockBean AccountService`** per Boot 3.3 or compatible collaborator config. When the security starter is present, `@WebMvcTest` normally loads security filters into the context; tests may get 401/403 before reaching the Controller. Use Spring Security Test `@WithMockUser`/`csrf()` when policy requires, rather than disabling filters casually.

### 10.4. Invalid Body Tests Should Verify the Service Is Never Called

For a Controller with a mocked service, assert after an invalid request:

~~~java
// Fragment inside @WebMvcTest with @MockBean AccountService service.
// Requires Mockito.verifyNoInteractions and an injected mock.
mvc.perform(post("/api/accounts")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{broken"))
    .andExpect(status().isBadRequest());

verifyNoInteractions(service);
~~~

This is a **fragment**, not a standalone program. It proves the Controller does not pass invalid payloads down to the service. If authentication filters exist, supply valid auth/CSRF so the negative test genuinely reaches the validation layer.

## 11. Real HTTP Integration Test: The /error Path on Unhandled Exceptions

According to Spring Boot docs, **MockMvc does not run an embedded Servlet container**, so it does not directly reproduce all error-page dispatch behaviors. To verify bodies produced by **`BasicErrorController /error`**, use a real HTTP server with **`@SpringBootTest(webEnvironment=RANDOM_PORT)`**.

**src/test/java/com/example/errorlab/DefaultErrorHttpTest.java:**

~~~java
package com.example.errorlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class DefaultErrorHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void unexpectedFailureUsesSafeDefaultError() {
        ResponseEntity<Map> response =
                http.getForEntity("/api/boom", Map.class);

        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR,
                response.getStatusCode());

        Map<?, ?> body = response.getBody();
        assertNotNull(body);
        assertEquals(500, ((Number) body.get("status")).intValue());
        assertEquals("/api/boom", body.get("path"));

        // Do not leak IllegalStateException error detail.
        assertFalse(body.containsKey("trace"));
        assertFalse(body.containsKey("exception"));
        assertFalse(body.containsKey("message"));
        assertFalse(body.toString().contains(
                "internal diagnostic - do not expose"
        ));
    }
}
~~~

### 11.1. Why Does HTTP 500 Still Return Default JSON Even with Problem Details Enabled?

In the demo mode, custom advice **has no handler for `IllegalStateException`**, while Spring Boot's Problem Details auto-handler mainly handles **MVC `ErrorResponse` exceptions**. Unexpected uncaught runtime exceptions can flow through the container `/error` dispatch and be rendered by `BasicErrorController` as JSON with **`timestamp`/`status`/`error`/`path`**.

That proves **enabling `spring.mvc.problemdetails.enabled=true` is not a “switch turning every 500 error into `problem+json`.”**

The test does not assert timestamps or class names. It verifies **HTTP 500**, **`status` 500**, **`path`**, and **no leaks** of `trace`/`exception`/`message`. Run against a real server to trust `/error` behavior.

### 11.2. Real Server Does Not Equal Full Production Environment

`RANDOM_PORT` opens a local embedded HTTP server, yet bypasses production's reverse proxy, gateway, authentication provider, and WAF. This is an **integration test**, not E2E. When deploying, also test proxy rewrites, error page mappings, and security-specific failures.

## 12. Testing Default Boot Mode with Problem Details Disabled

To compare **default `/error`** against **`ProblemDetail`**, create a test with a separate context disabling the property.

**src/test/java/com/example/errorlab/LegacyDefaultErrorHttpTest.java:**

~~~java
package com.example.errorlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.mvc.problemdetails.enabled=false"
)
class LegacyDefaultErrorHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void unmatchedRouteUsesBootDefaultErrorJson() {
        ResponseEntity<Map> response =
                http.getForEntity("/does-not-exist", Map.class);

        assertEquals(HttpStatus.NOT_FOUND,
                response.getStatusCode());
        assertTrue(MediaType.APPLICATION_JSON.isCompatibleWith(
                response.getHeaders().getContentType()
        ));

        Map<?, ?> body = response.getBody();
        assertNotNull(body);
        assertEquals(404, ((Number) body.get("status")).intValue());
        assertEquals("/does-not-exist", body.get("path"));
    }
}
~~~

**Differences:**
- This test disables **`spring.mvc.problemdetails.enabled`**; **`spring.web.resources.add-mappings=false`** is still read from `application.yml`.
- When GET hits a non-existent route, MVC/container can dispatch the error to **`/error`**, receiving basic JSON with **`status`/`path`** instead of default `problem+json`.
- **`AccountMvcTest`** in Problem Details mode tests errors handled by advice and Boot MVC.
- **`DefaultErrorHttpTest`** in `enabled=true` mode proves an unhandled 500 can still fall into `/error`.

Do not rely on calling **`GET /error`** directly, because Servlet error attributes in that case differ from a genuine error dispatch.

### 12.1. Why Not Assert That Default JSON Contains a `message` Field?

Spring Boot 3.3 property **`server.error.include-message=never`** keeps the `message` field **excluded by default**. Some external articles describe `/error` returning the exception message, yet configuration and modern versions govern the actual field set. Asserting `status`/`path` is safer and protects sensitive info.

### 12.2. What Happens When Tests Run Under Other Environments?

Local/test profiles can override:
- `spring.mvc.problemdetails.enabled`.
- `server.error.include-*`.
- `spring.web.resources.add-mappings`.
- security filters or custom `ControllerAdvice`.
- custom `ErrorController` and error page resolvers.

In CI, run tests with pinned config or explicit property overrides to guarantee the contract is tested in the intended mode. When a test compares two modes, separate contexts/classes as in the demo; do not mutate a JVM-wide System property between tests and introduce order dependency.

## 13. Running the Application and Executing curl Negative Tests

At the **`invalid-input-lab`** root, with JDK 17+, Maven, and port 8080 free:

~~~bash
mvn test
mvn package
java -jar target/invalid-input-lab-1.0.0.jar
~~~

JUnit tests cover one MVC slice and two real server contexts. If a test fails due to a differing context/security/profile, read the stack trace/test report and fix the root cause instead of switching to `@AutoConfigureMockMvc(addFilters=false)` just to turn the test green.

In another terminal:

**Valid request:**

~~~bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"fullName":"Ada","email":"ada@example.test","age":23}'
~~~

Expect status **201 Created**, Location **`/api/accounts/42`**, body with `id=42`.

**`@Valid` DTO violation:**

~~~bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H "Content-Type: application/json" \
  -H "Accept: application/problem+json" \
  -d '{"fullName":" ","email":"not-an-email","age":16}'
~~~

Expect status **400**, content type **`application/problem+json`**, code **`VALIDATION_FAILED`**, and violations containing fields **`fullName`, `email`, `age`**. Violations are sorted by field in the advice, though JSON key order remains unpinned.

**Malformed JSON:**

~~~bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H "Content-Type: application/json" \
  -H "Accept: application/problem+json" \
  -d '{broken'
~~~

Expect status **400**, code **`INVALID_JSON`**.

**Duplicate email business error:**

~~~bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H "Content-Type: application/json" \
  -H "Accept: application/problem+json" \
  -d '{"fullName":"Ada","email":"taken@example.test","age":23}'
~~~

Expect **409 Conflict**, code **`EMAIL_CONFLICT`**.

**Method/Media Type:**

~~~bash
curl -i -X PUT http://localhost:8080/api/accounts/42
curl -i -X POST http://localhost:8080/api/accounts \
  -H "Content-Type: text/plain" -d "wrong"
curl -i -H "Accept: application/xml" \
  http://localhost:8080/api/accounts/42
~~~

Expect **405**, **415**, **406** respectively. Bodies may be empty or `ProblemDetail` depending on content negotiation/exception resolvers; do not expect all three to return identical JSON.

**Unexpected 500:**

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/boom
~~~

Expect status **500**. In the demo's safe config, the response does not contain **`internal diagnostic - do not expose`** or a Java stack trace; the format can be default JSON from `/error`.

### 13.1. The Commands Above Suit Bash/Linux/macOS

On Windows PowerShell, use **`curl.exe`** instead of the `curl` alias to avoid syntax confusion. JSON quoting differs between PowerShell and Bash; verify HTTP status and content-type rather than copying a single-quoted Bash command verbatim into another shell and mistaking quoting issues for Spring bugs.

A simple PowerShell approach:

~~~powershell
$payload = @{ fullName = "Ada"; email = "ada@example.test"; age = 23 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/accounts" -ContentType "application/json" -Body $payload
~~~

The command above illustrates the happy path; for 4xx/5xx, PowerShell `Invoke-RestMethod` may throw an exception, requiring reading the exception's HTTP response rather than expecting the body to print automatically.

## 14. Comprehensive Invalid-Input Testing Matrix for Real Projects

The tests from the example are a foundation; production APIs should also cover these dimensions:

| Test Group | Representative Input | What to Assert |
| --- | --- | --- |
| Missing body | Empty body with required `@RequestBody` | 400 + proper code |
| Malformed JSON | Missing brace, invalid JSON | 400, no leaked parser details |
| Wrong JSON type | `Age="abc"`, object instead of scalar | 400, service not called |
| Missing fields | `age=null` or omitted | 400, field violations |
| Blank strings | `fullName="   "` | 400 `@NotBlank` |
| Numeric boundaries | `age=17` / `age=18` | 400 vs 201 |
| Upper bound | `@Size(max=40)` with 40/41 chars | Clear boundary distinction |
| Nested DTO | `@Valid` on child object | Nested violations |
| Collection size | Lists of hundreds/thousands of elements | No OOM, clear policy |
| Unknown JSON fields | Unrecognized fields | Depends on Jackson config/API contract |
| Duplicate/conflict | Already existing data | 409 domain code |
| Missing query | `q` absent | 400 |
| Empty query | `q=` | Is direct `@NotBlank` needed? |
| Invalid path variable | `/accounts/abc`, `/accounts/0` | 400 per conversion/constraint |
| Method not allowed | PUT on GET-only path | 405 |
| Unsupported content type | `text/plain` to JSON endpoint | 415 |
| Unacceptable response | `Accept: application/xml` when JSON-only | 406 |
| Missing route | `/does-not-exist` | 404, default vs custom schema |
| Not found resource | `/accounts/999` | 404 domain code |
| Unexpected server exception | Throw `IllegalStateException` | 500, no stack trace/message |
| Unauthorized | Missing credentials/expired token | 401 at security filter |
| Forbidden | User lacks permissions | 403 at security boundary |
| Oversized payload | JSON body exceeding server/proxy limit | 413 or connection-level failure per stack |
| Unicode | Vietnamese, emoji, combining marks | UTF-8 intact without corruption |
| Injection strings | HTML/SQL fragments inside fields | Not executed, not echoed unsafely |
| Locale | `Accept-Language: vi/en` | Status/code stable, detail may change |
| Negotiation | `Accept */*`, `problem+json`, `text/html` | Media type/body matches contract |
| HEAD/OPTIONS | Special methods | Check response per framework/security |
| CORS preflight | `Origin` + `Access-Control-Request-Method` | Check CORS config/filter behavior |

Notably, **unknown JSON fields** may be ignored or rejected by Jackson depending on deserializer configuration; do not assume a universal default when the API contract wants strictness. **`@NotBlank` on `String q`** must be declared if a present-but-whitespace query parameter should be invalid; **`@RequestParam(required=true)`** only ensures the parameter is present in the resolver, not non-blank checks.

### 14.1. Boundary Testing Is Better Than Arbitrary Far-Off Invalid Values

For `@Min(18)`, testing **17, 18, 19** catches off-by-one comparison bugs; for `@Size(max=40)`, test **40 and 41** characters per real length rules; for `@Max(50)`, test **50 and 51**. With Unicode surrogate characters, Java `String` length can differ from user-perceived grapheme count; define the contract explicitly.

### 14.2. Invalid Test Datasets Must Be Safe

Never put production passwords/tokens or real user info into fixtures. For invalid inputs containing HTML injection or secrets, assert the response was sanitized/not echoed. If tests save snapshots in CI logs, avoid PII there too. Fake data using **`example.test`** is an illustrative domain, not a real endpoint.

## 15. When to Use a Custom ResponseEntityExceptionHandler?

Spring Framework provides **`ResponseEntityExceptionHandler`** as a base class to centralize MVC exceptions into `ErrorResponse`/`ProblemDetail`. There are two approaches:

**Approach A — Spring Boot auto-enables Problem Details:** set **`spring.mvc.problemdetails.enabled=true`**, then write **`@RestControllerAdvice`** solely for custom exceptions and built-in exceptions needing overrides. As in the demo, set **`@Order`** higher than Boot's auto-configured advice (order 0) to intercept customized built-ins.

**Approach B — Own all MVC exception mapping yourself:** create **`@ControllerAdvice extends ResponseEntityExceptionHandler`**, overriding version-matching protected methods such as **`handleMethodArgumentNotValid`**, **`handleHttpMessageNotReadable`**, and **`handleHandlerMethodValidationException`**. You must preserve behavior for 405/415/406, headers, and statuses, and re-test on Spring upgrades.

Do not simultaneously enable Boot's auto advice and write a custom advice at the same precedence handling the same exception types expecting random ordering to work out. If multiple `@ControllerAdvice` classes exist, define clear ordering and test live routing.

### 15.1. Override Example — Fragment Only

~~~java
// Fragment inside a class extending ResponseEntityExceptionHandler.
// Requires @Override with a signature matching Spring Framework 6.1.
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request
) {
    ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "Request validation failed."
    );
    body.setProperty("code", "VALIDATION_FAILED");
    return handleExceptionInternal(
            ex, body, headers, status, request
    );
}
~~~

This snippet is not a standalone runnable Java file; it lacks the enclosing class/imports. When **uniformity across all built-in errors** is required, overriding can be effective, but you own statuses/headers and bodies. Do not copy verbatim without checking the Spring Framework 6.1 API in use.

## 16. Common Misconceptions About HTTP Error Handling

### 16.1. “@RestControllerAdvice Alone Catches Every 401/403”

False. Spring Security filters can block requests before `DispatcherServlet`. **`AuthenticationEntryPoint`** handles unauthenticated requests; **`AccessDeniedHandler`** handles denied access depending on authentication state. Form login may redirect, while stateless APIs may return 401/403 without a body or per configured entry point. Spring Security tests should use **`spring-security-test`, `@WithMockUser`, `csrf()`**, and integration with the real filter chain.

**Do not disable security filters during validation tests and call that security testing.** To isolate validation, keep separate tests; to verify production behavior, keep filters active.

### 16.2. “HTTP 400 Means @Valid Ran”

No. Jackson can fail before Bean Validation; missing required queries, type conversions, or bad `Content-Type` can also yield 4xx. Verify stable codes and error classes/mechanisms rather than guessing from status alone.

### 16.3. “Enabling Problem Details Makes Every Error application/problem+json”

No. Unhandled exceptions may fall through `/error`, security filters have separate handlers, proxies have separate error pages, and content negotiation also applies. A uniform public API contract requires designing and testing across all these boundaries.

### 16.4. “MockMvc Thoroughly Tests Default Container Errors”

No. **MockMvc** does not start an embedded server. Error page registration and dispatching to `/error` are Servlet container behaviors; Spring Boot recommends real-server tests for those parts. MockMvc excels at testing exception resolution, content negotiation, and validation inside the MVC pipeline.

### 16.5. “Asserting the Entire Message Makes Tests Stronger”

Often creates brittle tests. Default `detail` and validation messages vary by locale, message source, or library upgrades. Assert machine-readable `code`, `status`, `field`/`path`, or messages explicitly guaranteed by the API contract. For app-defined errors, keep error codes stable and versioned.

### 16.6. “Returning Exception Details to Clients Speeds Up Debugging”

Can inadvertently leak SQL queries, stack traces, internal service names, tokens, or enable account enumeration. Return a safe error code and correlation ID; write redacted diagnostics to protected logs/traces instead of copying raw stacktraces into response bodies.

## 17. Troubleshooting Failing Negative Tests

| Symptom | Common Cause | How to Verify |
| --- | --- | --- |
| `@NotBlank` does not run | Missing `starter-validation` or `@Valid` | Check dependency and method signature |
| JSON `age="abc"` yields no violations | Jackson failed before validation | Test `HttpMessageNotReadableException` |
| Query `@Min` behaves unexpectedly | Method validation setup/class `@Validated` differs | Spring MVC 6.1 built-in, annotation placement |
| `@WebMvcTest` fails to start context | Service/repository dependency excluded from slice | `@MockBean` or `@Import` needed bean |
| Test gets 401 instead of 400 | Spring Security filter blocks before Controller | Add Authentication/CSRF in test |
| POST test gets 403 | CSRF filter in cookie-auth app | `csrf()` and proper policy |
| Expected `ProblemDetail` yet got `/error` JSON | Wrong property, exception bypassed advice | Check `spring.mvc.problemdetails.enabled` and path |
| Custom `@ExceptionHandler` not called | Boot advice takes precedence or different exception type | `@Order`, `HandlerMethodValidationException` vs `MethodArgumentNotValidException` |
| 404 is `NoResourceFoundException` | Default `/**` static mapping | `spring.web.resources.add-mappings` |
| MockMvc 404 body differs from real Tomcat | Missing Servlet error dispatch | `RANDOM_PORT` integration test |
| 406 does not return `problem+json` body | `Accept` asks for different representation | Assert status; do not force invalid media type |
| Wrong `Content-Type` yields 415 | Mapping `consumes` mismatch | Check `consumes` and message converters |
| 500 leaks raw exception message | `server.error.include-message` or faulty custom handler | Lock safe defaults, add redaction tests |
| JSON fields change order across runs | `Map`/JSON writer makes no ordering promise | `jsonPath` instead of raw string |
| Validation error list changes order | Multiple constraints, group/validator order | Sort by field if part of contract |
| Test error message switches to Vietnamese | Locale/`MessageSource` | Assert stable code/status |
| Real server test collides on port 8080 | Used `DEFINED_PORT` | `RANDOM_PORT` and `TestRestTemplate` |
| `RestTemplate` fails parsing body | Server returned HTML due to `Accept` | Set proper `Accept`, inspect `Content-Type` |
| CI fails while local passes | Different profile, JDK, or dependency | Lock Boot version and test properties |

### 17.1. Focused Debugging Steps

1. Confirm actual HTTP request **method, path, query, `Content-Type`, `Accept`**, and body.
2. Identify whether the request stopped at a filter, handler mapping, converter, validation, Controller, or `/error`.
3. Inspect **status and `Content-Type`** before the body.
4. Check the framework exception type via safe logs; never expose types to clients.
5. Check `@ControllerAdvice` ordering and active Problem Details property.
6. If related to default `/error`, use a real embedded server test.
7. Compare responses against the stable API contract rather than an overly detailed snapshot.
8. Add a regression test for the exact bug discovered.

## 18. Suggestions for Long-Term Error Contract Design

A reliable API can standardize:
- **`type`** stable URI for business errors and validation groups.
- **`code`** machine-readable, invariant across locales.
- **`title`/`detail`** safe, clear, localizable.
- **`status`** matching HTTP status and error meaning.
- **`instance`** path or occurrence URI, without tokens/secrets.
- **`violations`** listing only necessary field/constraint codes.
- **`traceId`** correlation from tracing infrastructure when permitted.
- **`Retry-After`** for overload/maintenance when appropriate, never for validation errors.

Avoid treating an arbitrary full JSON object as the contract: many fields may be automatic operational metadata. Pick a **stable field subset** and verify via consumer/provider tests. When modifying the error schema, plan compatibility or versioning.

### 18.1. Frontend/Backend Contract Test Scenario

Frontend sends an invalid field; backend returns 400 + `VALIDATION_FAILED` + `violations`. Frontend binds errors to the right input fields without parsing English prose. When the backend changes wording or locale, the frontend keeps working. A duplicate request returns 409 + `EMAIL_CONFLICT`; frontend suggests logging in or changing email. An unhandled 500 returns a generic error + correlation ID without leaking exceptions; frontend shows “Try again later” instead of rendering a stack trace.

This is why **intentional negative tests** are necessary, not just verifying a Java method throws the right exception.

## 19. Self-Check Exercises

**1.** In Spring Boot 3.3, does `spring.mvc.problemdetails.enabled` default to `true`?  
**Answer:** No, it defaults to `false`; set `true` to enable automatic RFC 9457 support for MVC errors.

**2.** Do invalid JSON syntax and valid JSON violating `@NotBlank` throw the same exception?  
**Answer:** No. JSON parsing is usually `HttpMessageNotReadableException`; `@Valid` DTO validation is usually `MethodArgumentNotValidException`.

**3.** Which exception does `@Min` directly on `@RequestParam` in Spring MVC 6.1 typically raise?  
**Answer:** `HandlerMethodValidationException` from built-in method validation when configured under the new model.

**4.** Why should you not place class-level `@Validated` arbitrarily on a Controller?  
**Answer:** It can trigger AOP method validation and alter the exception/handling path; MVC 6.1 built-in validation does not need this class-level annotation.

**5.** Does HTTP 400 always carry an `application/problem+json` body?  
**Answer:** No. It depends on Problem Details config, exception handlers, content negotiation, and which boundary failed.

**6.** Does `@WebMvcTest` start real Tomcat and `/error` error-page dispatch?  
**Answer:** No. Use `@SpringBootTest(RANDOM_PORT)` for Servlet container error-page mechanics.

**7.** Does `BasicErrorController`'s default error JSON necessarily include `message`/`trace`?  
**Answer:** No. Spring Boot 3.3 excludes those fields by default; avoid setting `always` in production.

**8.** What are the five core fields of `ProblemDetail`?  
**Answer:** `type`, `title`, `status`, `detail`, `instance`; `code`/`violations` are extensions.

**9.** Why not test by comparing raw JSON strings literally?  
**Answer:** Field ordering, timestamps, locales, and dynamic values can change; assert `JSONPath`/status/media type instead.

**10.** How do HTTP 415 and 406 tests differ?  
**Answer:** 415 concerns the request's `Content-Type`; 406 concerns `Accept`/response representation.

**11.** If a user submits an already-registered email, must it always return 400 or can it return 409?  
**Answer:** 409 fits when the API contract models it as a conflict with current state; do not force every business error into 400.

**12.** When adding Spring Security, why might `@WebMvcTest` tests suddenly receive 401/403?  
**Answer:** Security filters run before the Controller, requiring proper authentication/CSRF in tests.

**13.** Why might URI `/does-not-exist` involve `NoResourceFoundException` instead of `NoHandlerFoundException`?  
**Answer:** Default static mapping `/**` can match the route first and report the missing resource.

**14.** When `@ExceptionHandler` catches `Exception.class` and always returns HTTP 400, what goes wrong?  
**Answer:** Server/security/logic bugs get misreported as client errors, breaking metrics and retry behavior.

**15.** Why not echo `rejectedValue` inside `violations`?  
**Answer:** It can expose passwords, tokens, personal data, or huge inputs and cause XSS/log leaks.

**16.** Which test verifies `server.error.include-stacktrace=never` works on a real HTTP 500?  
**Answer:** Real server integration `GET /api/boom`, asserting 500 and that the body has no `trace`/`exception`/`message`.

**17.** When should syntactically valid invalid-data errors use 422?  
**Answer:** When the API explicitly defines unprocessable-content semantics and custom mapping, not by assuming `@Valid` returns 422 automatically.

**18.** Is reading status alone enough to ensure the frontend displays field errors properly?  
**Answer:** No. You must assert `code`, `violations` schema, field names, content type, and a stable contract.

## 20. QA Checklist for Every API

- [ ] Happy-path tests exist as a baseline.
- [ ] Tests exist for malformed JSON, missing body, wrong types, and `@Valid` DTOs.
- [ ] Tests exist for null/blank/boundary constraints, `@Min`/`@Max`/`@Size`.
- [ ] Tests exist for required/malformed query and path variables.
- [ ] Tests exist for method/content negotiation 404/405/406/415.
- [ ] Tests exist for domain 404/409, distinct from built-in errors.
- [ ] Tests exist for 401/403 at security filters if the app uses Spring Security.
- [ ] Problem Details enabled with the MVC stack property, not confused with WebFlux.
- [ ] `ProblemDetail` tests check HTTP status, `application/problem+json`, and stable `code`/`type`.
- [ ] Violations are filtered, never echoing `rejectedValue` or secrets.
- [ ] `server.error.include-message`/`stacktrace`/`binding-errors` are locked down securely.
- [ ] Real HTTP integration tests verify `/error` and default responses.
- [ ] MockMvc is not used to claim container error-page behavior is tested.
- [ ] Assertions do not depend on timestamps, locales, or uncontracted JSON order.
- [ ] `@WebMvcTest` does not disable security filters to mask real errors.
- [ ] Tests verify services are not called when requests fail before the Controller.
- [ ] Negative tests guard against leaking SQL, stack traces, tokens, or internal class names.
- [ ] All tests run via Maven CI, with behavior reviewed upon Spring Boot upgrades.

## 21. Conclusion

**Web runtime testing must verify invalid-input paths as rigorously as happy paths.** In Spring Boot MVC, failures can occur at **routing, JSON conversion, Bean Validation, method validation, domain services, Spring Security filters, or Servlet `/error`**. Each layer has its own exceptions, statuses, and error bodies.

**RFC 9457 Problem Details** provides a standard error vocabulary via **`ProblemDetail`** and **`application/problem+json`**, yet in Spring Boot 3.3 you must enable **`spring.mvc.problemdetails.enabled=true`** and never assume every 500/security/proxy failure switches to that same schema automatically. **MockMvc/`@WebMvcTest`** works well for testing validation and `ControllerAdvice`; **real-port `@SpringBootTest`** is necessary to verify default `/error`. A resilient error contract requires accurate statuses, stable codes/types, and zero leakage of sensitive information.

## Official References

- Spring Boot 3.3.13 — Servlet Web Applications, Error Handling, and RFC 9457: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Common Application Properties, `spring.mvc.problemdetails.enabled` and `server.error.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Boot 3.3 — Testing Spring Boot Applications, `@WebMvcTest`, MockMvc, and servlet container caveats: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Error Responses, `ProblemDetail`, and `ResponseEntityExceptionHandler`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework — MockMvc integration tests: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Security — Servlet `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler`: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- RFC 9110 — HTTP status semantics (400/404/405/406/409/415/422/500): https://www.rfc-editor.org/rfc/rfc9110.html