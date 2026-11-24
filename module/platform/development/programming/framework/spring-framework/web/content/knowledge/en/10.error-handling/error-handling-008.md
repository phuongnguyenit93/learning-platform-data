# Spring MVC — Hiding Sensitive Information, Correlation IDs, and Avoiding Stack Traces in User Responses

## 1. Objectives

When a request fails, an API must help the client understand **what to do next**, while helping operators locate the **technical root cause**. These two audiences require different levels of detail.

Dangerous response example:

~~~json
{
  "error": "SQLException: password for jdbc://db.internal:5432/app is secret123",
  "stackTrace": "at com.example.payment.internal.DatabaseAdapter.save(DatabaseAdapter.java:84)",
  "authorization": "Bearer eyJ..."
}
~~~

Safer response:

~~~json
{
  "code": "INTERNAL_ERROR",
  "message": "Unable to process the request. Please try again later.",
  "requestId": "6efdbf4c-55a5-4d3c-a04a-4f0f9abce235",
  "violations": []
}
~~~

The actual HTTP status remains 500. The correlation ID lets operations locate the matching event in controlled logs/tracing; clients do not need to see exception classes, source paths, SQL, or stack traces.

After this lesson, you will be able to:

- Distinguish **public information in HTTP responses** from **internal diagnostic data**.
- List common leak sources: exception messages, stack traces, error pages, URLs/queries, validation rejected values, logs, headers, framework defaults, and proxies.
- Design stable error codes (`code`) and per-request correlation IDs (`requestId` or `traceId`); understand how the two serve different purposes.
- Generate server-controlled request IDs, return them in `X-Request-ID` and error JSON, put them into MDC for log correlation, and clean up MDC with `finally` or `MDC.putCloseable`.
- Use `@RestControllerAdvice` and `ResponseEntityExceptionHandler` to return safe messages for classified errors while preserving required HTTP statuses.
- Configure Spring Boot to avoid emitting stack traces, exception messages, and binding errors in default error handling paths.
- Test that responses do not contain synthetic sensitive strings and that the `requestId` in the body matches the header.

**Context:** Spring MVC Servlet stack, Java 17+, Spring Boot 3.5.0 / Spring Framework 6.2. Some examples are standalone code in the complete Maven project in section 9; shorter snippets are marked "illustrative".

## 2. What Can Be Exposed When an API Returns Errors?

| Data | Risk if exposed in response | Mitigation |
| --- | --- | --- |
| Stack trace, source file, line number | Reveals app structure, libraries, execution flow | Write to appropriate internal diagnostics; omit from body |
| `exception.getMessage()` | May contain SQL, hosts, tokens, user info, or internal arguments | Use fixed/curated public messages |
| SQL and connection strings | Exposes schema, host, account, database topology | Never send to clients; scrub secrets in logs too |
| Passwords, API keys, bearer tokens, cookies | Credential theft | Never echo/log raw values; redact or strip |
| HTTP query/body | May contain emails, verification codes, tokens, personal data | Do not log in full by default; whitelist strictly needed metadata |
| Validation rejected value | May carry PII/secrets or oversized/malicious payloads | Return field name and safe error code; omit raw value |
| Internal exception class/package | Exposes implementation details clients do not need | Use stable API-level `code` |
| Internal trace/span metadata | May reveal architecture or internal identifiers | Return only correlation IDs vetted as safe |
| Response headers | Server versions, debug info, or tokens | Audit headers too, not only JSON bodies |
| HTML error pages | May display stack traces or details | Configure error handling for browser/HTML routes too |

**Principle:** the response is a **public interface**; every string from exceptions, requests, databases, and dependencies must be treated as untrusted before exposure. A 4xx error can leak information too, not only 5xx errors.

## 3. Distinguishing Error Code, Request ID, and Trace ID

Three identifiers that are frequently confused:

| Name | Meaning | Stability | Who uses it |
| --- | --- | --- | --- |
| HTTP status | HTTP result category/semantics | Per HTTP semantics | HTTP clients, proxies, monitors |
| `code` / error code | Business/technical error category in contract, e.g., `INVALID_INPUT`, `ACCOUNT_CONFLICT` | Stable across requests | Clients displaying/handling errors |
| `requestId` / correlation ID | Identifier for a single request execution | Varies per request | Support, log search |
| Distributed `traceId` | Identifier for a trace spanning multiple services | Shared across the distributed trace | Tracing/observability |

For example, two requests may both return `INTERNAL_ERROR` yet have two different `requestId`s. Users supply the request ID so support can find that exact failure; clients use the error code to automate handling. Do not use exception class names as public error codes.

A simple contract:

~~~json
{
  "code": "INVALID_INPUT",
  "message": "Invalid request data.",
  "requestId": "9e9912e6-f2c3-44c7-a6e2-118b6fbfcf4c",
  "violations": [
    {"field": "email", "code": "EMAIL_INVALID"}
  ]
}
~~~

In this example, `message` is a client-safe curated message; `violations` reports only the field and error category, **without echoing the invalid email address**. The HTTP status is carried in the HTTP response (400) and does not need to be duplicated in the body unless the API contract requires it.

### 3.1. Who Generates the Request ID?

Two common strategies:

1. **Server-generated:** the server creates a random UUID and uses it consistently throughout the request. Simple and ideal for demos.
2. **Trusted gateway-generated:** the gateway generates the ID, enforcing format/length/trusted origin, and forwards it to the backend; the backend may preserve it and put it in MDC.

Do not blindly take `X-Request-ID` from an untrusted client and write it straight into logs/headers. Client-controlled data can be overly long, contain control characters or newlines, or cause collisions/ID spoofing. If accepting an ID from upstream, restrict allowed sources, length, character set, and define a replacement policy when invalid.

**A request ID is not an authorization token.** It should be a random correlation identifier carrying no PII, secrets, user IDs, internal hosts, or predictable timestamps. Even so, an ID can reveal that two logs belong to the same request; decide an appropriate visibility scope and never allow looking up another user's logs solely by ID.

### 3.2. Cross-Service Correlation IDs

If A calls B and B calls C, you can propagate W3C trace context such as `traceparent` according to your tracing stack. A distributed trace's `traceId` is not necessarily a UUID or identical to a custom `requestId`; do not invent a competing ID system if Micrometer Tracing/OpenTelemetry is already in place.

One model:

~~~text
Browser ── request ──> Gateway ──> Service A ──> Service B
                            │           │              │
                        traceId       traceId        traceId
                        requestId     spanId         spanId
                            │
                public X-Request-ID response
~~~

A trace has many spans; meanwhile `requestId` can be scoped per request or edge request depending on policy. When linking logs to traces, configure log patterns/structured logging to read MDC/tracing context in each service rather than assuming automatic propagation.

## 4. How Much Information Should HTTP Errors Reveal?

| Scenario | HTTP | Example public `code` | Reasonable public message | Should not return |
| --- | --- | --- | --- | --- |
| Syntactically invalid JSON | 400 | `INVALID_JSON` | Unable to read JSON data | Parser stack trace, full body |
| DTO validation failure | 400 | `INVALID_INPUT` | Invalid request data | Raw rejected password/token |
| Resource not found | 404 | `RESOURCE_NOT_FOUND` | Resource not found | Internal DB table/key |
| Domain state conflict | 409 | `STATE_CONFLICT` | Operation invalid in current state | Internal service/method names |
| Insufficient permissions for resource | 403 or policy-specific 404 | `ACCESS_DENIED` | Permission denied | Secret account/role details |
| Rate limit | 429 | `RATE_LIMITED` | Limit exceeded, please try again later | Unnecessary internal config |
| DB or dependency temporarily down | 503 if appropriate | `SERVICE_UNAVAILABLE` | Service temporarily unavailable | DB host, credentials, raw driver error |
| Unexpected exception | 500 | `INTERNAL_ERROR` | Server error occurred | Stack trace, source path, runtime details |

Login and registration errors may also need **bounded detail** to prevent user/account enumeration. For instance, password reset requests should return a generic message when security policy requires hiding whether an email exists. That belongs to security flow design; hiding stack traces alone does not solve it.

Never convert system errors into HTTP 200 just to give clients a "pretty" JSON:

~~~java
// Anti-pattern: HTTP status does not reflect the outcome.
try {
    return service.update();
} catch (Exception ex) {
    return ResponseEntity.ok(Map.of(
            "success", false,
            "error", ex.getMessage()));
}
~~~

This snippet illustrates an anti-pattern only; it has both the wrong status and risks leaking the message. Separate exception semantics from proper HTTP mapping.

## 5. Spring Boot: Safe Default Error Configuration

With Spring Boot 3.5, in `src/main/resources/application.properties`:

~~~properties
server.error.include-stacktrace=never
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-exception=false
server.error.include-path=never
server.error.whitelabel.enabled=false
~~~

Meaning:

- `include-stacktrace=never`: prevents the default error path from adding trace attributes to responses, even if a request tries to trigger it via query parameter.
- `include-message=never`: excludes exception messages from default error bodies.
- `include-binding-errors=never`: excludes raw binding errors.
- `include-exception=false`: excludes the exception class name.
- `include-path=never`: avoids automatically adding request path (which could hold tokens/PII).
- `whitelabel.enabled=false`: disables Boot's default Whitelabel HTML error page; **does not mean no HTML error page can ever appear**, as the servlet container, proxy, or frontend may provide one.

This configures **Boot's default error path**, and does not automatically scrub responses you build manually in `@ExceptionHandler` or `ResponseEntity`. If your code puts `ex.getMessage()` into JSON, these settings will not save you. Check proxies, framework error handlers, the Security filter chain, and exceptions during response serialization as well.

**Do not use** in production:

~~~properties
# Anti-pattern: increases information disclosure risk.
server.error.include-stacktrace=always
server.error.include-message=always
server.error.include-binding-errors=always
~~~

Depending on the version, `on_param` include settings allow clients to enable details via query parameters. Avoid that setting in public environments. Do not treat disabling `spring.mvc.problemdetails.enabled` as a security control; `ProblemDetail` can still be constructed manually with dangerous details.

## 6. Handling Exceptions Without Exposing Information

In Spring MVC:

- `@RestControllerAdvice` centralizes **exception → HTTP response** translation for controllers in scope.
- `@ExceptionHandler` handles domain/system exceptions explicitly defined by the application.
- `ResponseEntityExceptionHandler` provides handlers for many built-in Spring MVC errors (unreadable body, validation, 405/415...).
- RFC 9457 `ProblemDetail` is another error contract option; you do not have to use it alongside a custom DTO.
- `@ResponseStatus` can map exceptions to statuses, though advice is usually clearer when you need strict control over safe JSON.

Illustrative domain handler example:

~~~java
@ExceptionHandler(DuplicateUsernameException.class)
ResponseEntity<SafeError> duplicate(
        DuplicateUsernameException ex,
        HttpServletRequest request) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new SafeError(
                    "USERNAME_UNAVAILABLE",
                    "Unable to register this username.",
                    requestId(request),
                    List.of()));
}
~~~

Here `ex.getMessage()` is **not** concatenated into the body. This snippet is a method inside an advice, not a standalone file; the complete project is in section 9.

### 6.1. Should You Use a Catch-All Exception.class?

If `@ExceptionHandler(Exception.class)` returns 500 for every exception, it can accidentally **mask valid framework HTTP statuses** (405, 406, 415, or exceptions that already implement `ErrorResponse`). When extending `ResponseEntityExceptionHandler`, avoid declaring duplicate exception handlers for mappings already covered by the base class, as that can cause ambiguous mappings.

Choose one of these approaches:

- Extend `ResponseEntityExceptionHandler` and override the exact hooks, preserving original HTTP statuses while replacing bodies with safe DTOs.
- Define explicit handlers for known domain/system exceptions; let Boot/framework handle unexpected errors with detail-hiding config.
- If a unified public 500 catch-all is needed, design the fallback so it does not override HTTP exceptions that already have statuses, and test 400/404/405/406/415/422/500 thoroughly.

**Note:** exceptions thrown in servlet filters (especially the Spring Security filter chain) or after the response has committed do not necessarily pass through controller advice. Security 401/403 are usually handled by `AuthenticationEntryPoint` and `AccessDeniedHandler`; enforce the same safe error and correlation ID policy there.

## 7. Logging: Enough to Debug, Minimal Data Exposure

Internal logs may record details clients must never see, yet **logs are also sensitive storage**. Control access, retention, redaction, and transmission.

Structured log example:

~~~text
level=ERROR event=checkout_failed errorCode=INTERNAL_ERROR
requestId=6efdbf4c-55a5-4d3c-a04a-4f0f9abce235
route=/api/checkouts method=POST status=500
exceptionClass=PaymentAdapterException
~~~

Data in this example is illustrative. Internal stack traces are helpful, yet carry the risk of containing sensitive values in exception messages and stack context. Only log full exceptions where secret-handling policies, access controls, retention limits, and scrubbing are in place.

**Recommended to log:**

- Event name, stable error code, HTTP status, route template, method, duration, request ID / trace ID.
- Exception class and stack trace on protected channels (when needed, at an appropriate log level).
- **Whitelisted** dependency names, timeouts, retry counts, outcomes.

**Do not log by default:**

- `Authorization`, `Cookie`, `Set-Cookie`, API keys, passwords, OTPs, tokens; especially never log all HTTP headers blindly.
- Entire query strings or JSON bodies if they contain PII or payment data.
- JDBC URLs carrying passwords, SQL statements with sensitive values, raw third-party responses.
- User identifiers/IP addresses unnecessary for the case; if legally or operationally required, follow data-protection policies.

**Whitelisting beats blacklisting:** log explicitly defined metadata rather than logging every field and trying to mask secrets afterward. Secrets can show up in unexpected keys, nested JSON, exception causes, URLs, or even file paths.

### 7.1. Avoiding Log Injection and Cardinality Explosion

When logging untrusted data (if truly necessary), use structured logging and sanitize control characters so a value containing newlines cannot forge extra log entries. Never use raw URLs/queries as metric labels (distinct IDs cause high cardinality). Use route templates such as `/api/orders/{id}`.

If logging correlation IDs, enforce a reasonable max length; this example generates its own UUID so it never processes arbitrary client strings.

## 8. MDC and Request-Scoped Correlation IDs

SLF4J's MDC (Mapped Diagnostic Context) stores key/value pairs bound to the **current thread**. In synchronous Servlet MVC, a filter can attach `requestId` so log statements on the same thread can read it:

~~~java
try (MDC.MDCCloseable ignored =
        MDC.putCloseable("requestId", requestId)) {
    filterChain.doFilter(request, response);
}
~~~

`MDC.putCloseable` removes the entry automatically on scope exit, even on exceptions. If using `MDC.put(...)`, you must have `finally { MDC.remove("requestId"); }` to prevent context leaking across thread pool reuse.

Log pattern example:

~~~properties
logging.pattern.level=%5p [rid:%X{requestId}]
~~~

This only illustrates putting MDC into a console pattern; if using structured JSON logging, configure the corresponding field. With Spring Boot + Micrometer Tracing, log patterns and MDC may already include `traceId`/`spanId`; avoid overwriting tracing keys managed by the framework.

### 8.1. Important Limitations of MDC

MDC typically relies on `ThreadLocal`; it **does not automatically propagate safely across** `@Async`, `CompletableFuture`, thread pools, scheduled tasks, virtual threads, or reactor contexts. When a request hops threads, use the context propagation mechanism suited to your stack (Micrometer Context Propagation, executor task decorators, OpenTelemetry context), and clean up in the right scope.

Having one request ID for a request flow does not mean every async task sees that MDC entry automatically. If a servlet request enters a new `ERROR` or `ASYNC` dispatch, inspect `OncePerRequestFilter` flags `shouldNotFilterErrorDispatch()` / `shouldNotFilterAsyncDispatch()` and dispatcher registrations; the demo in section 9 targets ordinary synchronous MVC handlers.

### 8.2. When to Return the ID to Clients?

- An HTTP response header, such as `X-Request-ID: <uuid>`, lets support check DevTools and client logs.
- An error body field `requestId` matching **the exact ID in the header**; automated tests should assert both match.
- Successful responses can also include the header to aid investigation on any call; do not force clients to trigger errors just to obtain an ID.
- When using W3C Trace Context, consider publishing an allowed `traceId`, keeping it distinct from internal span IDs and observability policies.

In browsers, if JavaScript needs to read `X-Request-ID` across CORS, the server must configure `Access-Control-Expose-Headers: X-Request-ID` with an appropriate origin policy. Do not open CORS indiscriminately or use `*` with credentials inappropriately.

## 9. Runnable Spring Boot Java 17 Project

The complete project demonstrates **server-generated correlation IDs**, **safe error responses**, **validation and JSON parse errors**, **domain conflicts**, a simulated 500 error, and tests verifying no stack traces leak.

Structure:

~~~text
safe-error-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/SafeErrorApplication.java
    │   └── resources/application.properties
    └── test/java/demo/SafeErrorApiTest.java
~~~

### 9.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>safe-error-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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

### 9.2. application.properties

~~~properties
server.error.include-stacktrace=never
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-exception=false
server.error.include-path=never
server.error.whitelabel.enabled=false

logging.pattern.level=%5p [rid:%X{requestId}]
~~~

### 9.3. SafeErrorApplication.java

Place all of the following code in **one file** `src/main/java/demo/SafeErrorApplication.java`. There is only one top-level `public class`, with the remaining types package-private.

~~~java
package demo;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.stereotype.Component;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@SpringBootApplication
public class SafeErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeErrorApplication.class, args);
    }
}

@Component
class RequestIdFilter extends OncePerRequestFilter {
    static final String ATTRIBUTE = RequestIdFilter.class.getName() + ".requestId";
    static final String HEADER = "X-Request-ID";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Do not trust client-supplied X-Request-ID.
        String requestId = UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE, requestId);
        response.setHeader(HEADER, requestId);

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("requestId", requestId)) {
            chain.doFilter(request, response);
        }
    }
}

record RegistrationRequest(
        @NotBlank String username,
        @NotBlank @Email String email) {
}

record FieldIssue(String field, String code) {
}

record SafeError(
        String code,
        String message,
        String requestId,
        List<FieldIssue> violations) {
}

class UsernameUnavailableException extends RuntimeException {
    UsernameUnavailableException() {
        super("Username is unavailable");
    }
}

class InternalDemoException extends RuntimeException {
    InternalDemoException() {
        // Synthetic placeholder value solely to test leak prevention.
        super("SYNTHETIC_DEMO_SECRET: connection failed at db.internal");
    }
}

@RestController
@RequestMapping("/api/demo")
class RegistrationController {
    // In-memory store, for demo use only.
    private final Set<String> usedNames = ConcurrentHashMap.newKeySet();

    RegistrationController() {
        usedNames.add("taken");
    }

    @PostMapping(path = "/register",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Map<String, String>> register(
            @Valid @RequestBody RegistrationRequest request) {

        String key = request.username().toLowerCase(Locale.ROOT);
        if (!usedNames.add(key)) {
            throw new UsernameUnavailableException();
        }
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "created"));
    }

    @GetMapping(path = "/unexpected",
                produces = MediaType.APPLICATION_JSON_VALUE)
    Map<String, String> unexpected() {
        throw new InternalDemoException();
    }

    @GetMapping(path = "/ping",
                produces = MediaType.APPLICATION_JSON_VALUE)
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}

@RestControllerAdvice
class SafeErrorAdvice extends ResponseEntityExceptionHandler {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeErrorAdvice.class);

    private static String requestId(HttpServletRequest request) {
        Object id = request.getAttribute(RequestIdFilter.ATTRIBUTE);
        return id instanceof String s ? s : "unavailable";
    }

    private static String requestId(WebRequest request) {
        Object id = request.getAttribute(
                RequestIdFilter.ATTRIBUTE, WebRequest.SCOPE_REQUEST);
        return id instanceof String s ? s : "unavailable";
    }

    private static SafeError error(
            String code, String message, String id, List<FieldIssue> issues) {
        return new SafeError(code, message, id, issues);
    }

    @ExceptionHandler(UsernameUnavailableException.class)
    ResponseEntity<SafeError> usernameUnavailable(
            UsernameUnavailableException ex, HttpServletRequest request) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(error(
                        "USERNAME_UNAVAILABLE",
                        "Unable to register this username.",
                        requestId(request), List.of()));
    }

    @ExceptionHandler(InternalDemoException.class)
    ResponseEntity<SafeError> unexpected(
            InternalDemoException ex, HttpServletRequest request) {
        String id = requestId(request);

        // Log internally per policy; never return ex.getMessage() to clients.
        LOG.error("Unexpected internal error requestId={}", id, ex);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(error("INTERNAL_ERROR",
                        "Unable to process the request. Please try again later.",
                        id, List.of()));
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {
        SafeError body = error(
                "INVALID_JSON",
                "Unable to read JSON data.",
                requestId(request),
                List.of());
        return super.handleExceptionInternal(
                ex, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<FieldIssue> issues = ex.getBindingResult()
                .getFieldErrors().stream()
                .map(SafeErrorAdvice::fieldIssue)
                .distinct()
                .toList();

        SafeError body = error(
                "INVALID_INPUT",
                "Invalid request data.",
                requestId(request),
                issues);

        return super.handleExceptionInternal(
                ex, body, headers, status, request);
    }

    private static FieldIssue fieldIssue(FieldError error) {
        // Whitelist constraint codes; never return rejectedValue or raw message.
        String code = switch (error.getCode() == null
                ? "" : error.getCode()) {
            case "NotBlank" -> "REQUIRED_TEXT";
            case "Email" -> "INVALID_EMAIL";
            default -> "INVALID_VALUE";
        };
        return new FieldIssue(error.getField(), code);
    }

    @Override
    protected ResponseEntity<Object> handleExceptionInternal(
            Exception ex,
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        // For uncustomized MVC errors: preserve HTTP status/headers.
        // Do not reuse body/error details supplied by the exception.
        SafeError safe = error(
                status.is5xxServerError()
                        ? "INTERNAL_ERROR" : "REQUEST_ERROR",
                status.is5xxServerError()
                        ? "Unable to process the request."
                        : "Request was not accepted.",
                requestId(request),
                List.of());

        return super.handleExceptionInternal(
                ex, safe, headers, status, request);
    }
}
~~~

**Technical notes when reading the code:**

- `handleMethodArgumentNotValid` and `handleHttpMessageNotReadable` call `super.handleExceptionInternal(...)` directly, preserving their chosen safe bodies without being replaced by the generic `handleExceptionInternal` override.
- Overriding `handleExceptionInternal` covers other MVC errors routed through the base class, preserving **framework status and headers** (such as `Allow` on 405) while replacing the body with a neutral message. Depending on content negotiation, some errors such as 406 may have no response body; status remains primary.
- Avoid declaring a broad `@ExceptionHandler(Exception.class)` that forces framework statuses into 500.
- The internal error example deliberately includes `SYNTHETIC_DEMO_SECRET` solely to verify that the string **never appears in the HTTP response**. It is not a real credential.
- The Filter generates a fresh UUID, ignoring client-supplied headers to reduce spoofing/log injection; `MDC.putCloseable` cleans up context on exit.
- The in-memory `Set` updates atomically for the demo; production systems need persistence uniqueness constraints/transactions and security rules against username enumeration.

### 9.4. Running and Testing with curl

Run in the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Test success:

~~~bash
curl -i 'http://localhost:8080/api/demo/ping'
~~~

HTTP 200, equivalent body:

~~~json
{"status":"ok"}
~~~

In addition to the body, the `X-Request-ID` header contains a server-generated UUID.

Test valid JSON body:

~~~bash
curl -i -X POST 'http://localhost:8080/api/demo/register' \
  -H 'Content-Type: application/json' \
  --data '{"username":"lan","email":"lan@example.com"}'
~~~

HTTP 201, body `{"status":"created"}`. If called again with the same username (case-insensitive), HTTP 409, equivalent response:

~~~json
{
  "code":"USERNAME_UNAVAILABLE",
  "message":"Unable to register this username.",
  "requestId":"6efdbf4c-55a5-4d3c-a04a-4f0f9abce235",
  "violations":[]
}
~~~

The UUID here is only a **format example**; at runtime a fresh UUID is generated per request. The request ID in the header and body of **the same request** must match exactly.

Test syntactically invalid JSON:

~~~bash
curl -i -X POST 'http://localhost:8080/api/demo/register' \
  -H 'Content-Type: application/json' \
  --data '{"username":"lan","email":'
~~~

HTTP 400 with `code=INVALID_JSON`, safe message, and `requestId`; the response does not echo the raw JSON fragment sent by the client.

Test validation with invalid email:

~~~bash
curl -i -X POST 'http://localhost:8080/api/demo/register' \
  -H 'Content-Type: application/json' \
  --data '{"username":"","email":"not-an-email"}'
~~~

HTTP 400, `code=INVALID_INPUT`, and equivalent violations:

~~~json
[
  {"field":"username","code":"REQUIRED_TEXT"},
  {"field":"email","code":"INVALID_EMAIL"}
]
~~~

Error order is not guaranteed. Crucially, `"not-an-email"` does not appear in the body, avoiding echoing client-submitted values.

Test simulated system error:

~~~bash
curl -i 'http://localhost:8080/api/demo/unexpected'
~~~

HTTP **500**, public body has `code=INTERNAL_ERROR` and a neutral message; **none of** `SYNTHETIC_DEMO_SECRET`, `db.internal`, class names, or Java stack traces appear. Protected server consoles/logs receive the exception stack trace together with `requestId` for diagnostics.

The commands above use Bash syntax. On Windows PowerShell, use `curl.exe` and replace `\` line continuations with appropriate syntax or put the command on one line.

### 9.5. MockMvc Tests: Matching Header/Body ID and No Exception Leaks

File `src/test/java/demo/SafeErrorApiTest.java`:

~~~java
package demo;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeErrorApiTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    private JsonNode assertCorrelation(MvcResult result) throws Exception {
        String header = result.getResponse().getHeader("X-Request-ID");
        assertNotNull(header);
        UUID.fromString(header); // Throws if not a valid UUID.

        JsonNode body = mapper.readTree(
                result.getResponse().getContentAsString());
        assertEquals(header, body.path("requestId").asText());
        return body;
    }

    @Test
    void malformedJsonReturnsSafe400() throws Exception {
        MvcResult result = mvc.perform(post("/api/demo/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"lan\",\"email\":"))
            .andExpect(status().isBadRequest())
            .andReturn();

        JsonNode body = assertCorrelation(result);
        assertEquals("INVALID_JSON", body.path("code").asText());
        assertFalse(result.getResponse().getContentAsString()
                .contains("HttpMessageNotReadableException"));
    }

    @Test
    void validationDoesNotEchoRejectedValues() throws Exception {
        MvcResult result = mvc.perform(post("/api/demo/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"","email":"private-input@example.invalid!"}
                    """))
            .andExpect(status().isBadRequest())
            .andReturn();

        JsonNode body = assertCorrelation(result);
        assertEquals("INVALID_INPUT", body.path("code").asText());
        assertFalse(result.getResponse().getContentAsString()
                .contains("private-input@example.invalid!"));
    }

    @Test
    void internalErrorHidesStacktraceAndExceptionMessage() throws Exception {
        MvcResult result = mvc.perform(get("/api/demo/unexpected"))
            .andExpect(status().isInternalServerError())
            .andReturn();

        JsonNode body = assertCorrelation(result);
        assertEquals("INTERNAL_ERROR", body.path("code").asText());

        String serialized = result.getResponse().getContentAsString();
        assertFalse(serialized.contains("SYNTHETIC_DEMO_SECRET"));
        assertFalse(serialized.contains("db.internal"));
        assertFalse(serialized.contains("InternalDemoException"));
        assertFalse(serialized.contains("SafeErrorApplication.java"));
        assertFalse(serialized.contains("stackTrace"));
        assertFalse(serialized.contains("\"trace\""));
    }

    @Test
    void clientCannotChooseCorrelationId() throws Exception {
        MvcResult result = mvc.perform(get("/api/demo/unexpected")
                .header("X-Request-ID", "attacker-controlled"))
            .andExpect(status().isInternalServerError())
            .andReturn();

        JsonNode body = assertCorrelation(result);
        assertFalse("attacker-controlled".equals(
                body.path("requestId").asText()));
    }

    @Test
    void successAlsoHasRequestIdHeader() throws Exception {
        MvcResult result = mvc.perform(get("/api/demo/ping"))
            .andExpect(status().isOk())
            .andReturn();
        String header = result.getResponse().getHeader("X-Request-ID");
        assertNotNull(header);
        UUID.fromString(header);
        assertEquals("{\"status\":\"ok\"}",
                result.getResponse().getContentAsString());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The tests verify **HTTP behavior** without relying on fixed UUIDs. JSON assertions check the `code` and ID fields; only the success endpoint body has a single `status` field so it can be compared directly. In real APIs, use JSON trees/JSONPath and check all response headers.

**Limitations of the test suite:** The demo covers synchronous MVC handlers in `MockMvc`. It does not verify container error dispatch, filter chains with Spring Security, async thread contexts, gateway reverse proxies, partially committed responses, or actuator errors. For real applications, add integration tests running an embedded server + security/proxy, checking JSON, HTML errors, headers, and logs.

## 10. What Can Still Leak Despite Having @RestControllerAdvice?

### 10.1. Errors Before Entering DispatcherServlet

Authentication failures occurring in Spring Security filters can bypass controller advice. For consistent JSON responses, configure `AuthenticationEntryPoint` for 401 and `AccessDeniedHandler` for 403, applying the same safe error codes and request IDs. The security layer must decide which error details may be disclosed; never return stack traces or password-verification failure specifics.

### 10.2. Errors in the Serializer After the Handler Returns

A controller returns an object, yet Jackson fails to serialize it due to circular object graphs or a throwing getter. If output was already written or headers committed, an exception handler cannot reliably replace it with a 500 JSON error. Therefore, avoid serializing uncontrolled entity graphs; use response DTOs and test all content types. For streaming responses/file downloads/SSE, error reporting differs from ordinary JSON bodies.

### 10.3. Proxies, CDNs, and Container Error Pages

Nginx, API gateways, load balancers, or servlet containers can generate their own HTTP error pages when a backend dies or times out. Spring Boot error settings **do not control all of those layers**. Inspect 502/503/504 responses from the gateway; ensure HTML pages do not disclose upstream hosts, debug info, or exception details.

### 10.4. Error Details in Observability and Alerting

- APM/tracing may automatically capture request attributes and exception events; configure stripping/scrubbing of PII, bearer tokens, and passwords.
- Log aggregation and third-party alerting are data transmission sinks with their own access controls and retention.
- Alert messages should carry error codes/trace IDs and dashboard links rather than copying full request payloads.
- During incident analysis, never paste logs containing real user data into public issues; redact before sharing.

### 10.5. Correlation IDs and Security

Never treat `X-Request-ID` as a "password" for a public log-lookup endpoint. Only authorized personnel may query matching logs; rate-limit support endpoints if any exist. If exposing IDs could enable enumeration, use high-entropy random IDs like UUIDv4 rather than sequential IDs or raw user IDs.

## 11. Before/After Scenarios

### Wrong: Returning Dependency Data Straight to Clients

~~~java
try {
    database.save(entity);
} catch (Exception ex) {
    return ResponseEntity.status(500).body(Map.of(
            "error", ex.getMessage(),
            "trace", Arrays.toString(ex.getStackTrace())));
}
~~~

This illustrative snippet leaves `database` and `entity` undefined; it is an anti-pattern. It leaks stack traces and exception details.

### Right: Safe Message + Lookup ID

~~~java
try {
    database.save(entity);
} catch (KnownDatabaseOutage ex) {
    String requestId = currentRequestId();
    safeLogger.error("Database operation unavailable; rid={}",
            requestId, ex);
    throw new DependencyUnavailableException();
}
~~~

This is pseudocode inside a service/adapter (helpers and exceptions are illustrative), showing the adapter classifying **known failures** and keeping the cause in internal channels. Web advice maps it to an appropriate status and safe body without printing dependency messages over HTTP. For unexpected errors, do not blindly convert everything into `DependencyUnavailableException`; preserve the cause so operations spots bugs.

**Caution:** logging `ex` can include sensitive data in its message or cause. Only log full exceptions where secret-masking policies, restricted access, retention limits, and proper logging middleware are enforced. If a dependency puts secrets into an exception, sanitize/redact in the adapter before pushing to shared logs.

## 12. Production API Checklist

1. **Error contract:** accurate 4xx/5xx semantics, stable `code`, safe `message`, consistent request/trace ID, field errors never echoing raw values.
2. **Default error safety:** set Boot `include-stacktrace/message/binding-errors` to `never` and `include-exception=false`; verify HTML and proxy errors too.
3. **Explicit handlers:** never pass `ex.getMessage()`, `Throwable.toString()`, `StackTraceElement[]`, or raw SQL into response bodies.
4. **Correlation:** generate sufficiently random IDs or accept only from trusted gateways; assert header/body match and log searchability.
5. **MDC lifecycle:** clean up MDC immediately on exit; verify context propagation with async/virtual threads/tracing.
6. **Logs:** whitelist metadata; redact secrets/PII; protect access controls, retention, transport, and backups.
7. **Security:** 401/403 filter chain produces safe error responses; avoid revealing account existence when policy forbids it.
8. **Validation:** distinguish JSON parsing from Bean Validation; never return raw `rejectedValue` or entire bodies.
9. **Integration:** test success, 400, 404, 405, 415, 409, 500, pre-controller errors, serialization errors, and gateway errors; do not ignore response headers.
10. **Review:** treat the error contract as public API, document error codes clearly, and run a security review before deployment.

## 13. Exercises

**Exercise 1 — Response Audit:** Identify data that should be hidden in:

~~~json
{
  "message": "org.postgresql.util.PSQLException: password authentication failed for service-account",
  "path": "/reset?token=abc123",
  "debug": "at com.acme.account.ResetService.reset(ResetService.java:77)"
}
~~~

Design a safe 500 body containing `code` and `requestId`.

**Exercise 2 — Correlation:** A browser sends two HTTP requests that both fail with 500. Explain why they should have two distinct request IDs while potentially sharing the same error code; write a test asserting body `requestId` = response header.

**Exercise 3 — MDC:** Given a request using a servlet thread pool, what happens if you forget `MDC.remove("requestId")` in `finally`? Write a version using `MDC.putCloseable`.

**Exercise 4 — Async:** A `CompletableFuture.supplyAsync(...)` handler logs without `requestId`. Explain why `ThreadLocal` MDC does not automatically cross executors; propose suitable context propagation.

**Exercise 5 — Validation:** A request has a `password` failing a constraint. Propose a JSON errors payload naming only field `password` and a suitable error code without echoing the password. Verify with a test checking the rejected value is absent.

**Exercise 6 — Framework:** Compare the behavior of `@RestControllerAdvice` on `HttpMessageNotReadableException` vs. authentication failures in a Spring Security filter. Identify the proper handler for each path.

**Exercise 7 — Observability:** Design a log event for a database timeout containing error code, `requestId`, route template, status, and duration; point out where SQL arguments or authorization headers must not be recorded.

**Exercise 8 — Production integration:** Using an embedded server, test GET on a nonexistent path, wrong HTTP method, wrong `Content-Type`, and dependency failure; verify every response from web/proxy layers contains no stack traces and includes a correlation ID if required by contract.

## 14. Summary

- Client-facing errors must be **clear yet minimal**; deep technical details belong in protected internal observability channels.
- **Error code** identifies the error category; **`requestId`/`traceId`** pinpoints the execution for correlation; these identifiers never replace authentication/authorization.
- `@RestControllerAdvice` and `ResponseEntityExceptionHandler` standardize MVC errors, yet do not automatically cover Spring Security filters, proxies, async tasks, or already-committed responses.
- Spring Boot provides settings preventing default emission of `trace`, exception messages, and binding details. Custom handlers must still enforce safety rules themselves.
- Never return `exception.getMessage()`/stack traces to clients; even internally, apply redaction and log access controls.
- Test **against leaking sensitive data** using synthetic strings while verifying request ID consistency between headers and bodies.

## 15. References

- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `server.error.include-*` and `server.error.whitelabel.enabled` properties.
- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): Spring MVC error handling, `ErrorResponse`, `ProblemDetail`.
- [Spring Framework 6.2 — ResponseEntityExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): exact override signatures for exception hooks.
- [Spring Framework 6.2 — OncePerRequestFilter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): request, error, and async dispatches.
- [SLF4J — MDC](https://www.slf4j.org/manual.html): mapped diagnostic context, `putCloseable`, and logging.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent` and distributed tracing.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standard error response format.
