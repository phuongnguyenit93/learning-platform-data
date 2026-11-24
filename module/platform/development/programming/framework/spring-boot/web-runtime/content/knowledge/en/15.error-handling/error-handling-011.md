# Unifying Error Structure, Business Codes, and Correlation IDs in Spring Boot

## 1. The Problem: One Error Must Be Understood by Client, Server, and Monitoring

A Spring Boot application can emit errors from many places: controllers, Bean Validation, Spring Security, the service/domain layer, missing data, HTTP clients calling other services, filters, the Servlet container, or the reactive web server. If each place returns a different JSON shape, clients must write many branching handlers and operations teams struggle to tie a user's error message to the corresponding logs.

Examples of inconsistent responses:

~~~json
{"message":"Bad request"}
~~~

~~~json
{"error":"No stock","status":409,"time":"..."}
~~~

~~~json
{"success":false,"errorCode":1012,"reason":"Database unavailable"}
~~~

These three responses share no common error-identifying fields, may use different HTTP statuses and internal codes, and carry no link back to server logs. For errors spanning multiple microservices, diagnosis becomes especially difficult.

A **unified error contract** must answer:

- Which HTTP category does the error belong to? Is the actual HTTP status accurate?
- What is the business error, expressed via a **stable machine-readable code** independent of message language?
- What should the user or client do to recover?
- For support, which **correlation ID** locates the same request in logs?
- If distributed tracing is active, how do trace ID/span ID link to the request?
- Which details are safe to expose publicly, and which must stay inside logs?
- Do errors from `@Valid`, `@RequestParam`, services, HTTP 404, 500, or WebFlux converge onto the same schema?
- Is the result easy to test, document, and evolve without breaking older clients?

Spring Framework 6.x has built-in support for **ProblemDetail** per **RFC 9457 – Problem Details for HTTP APIs** (replacing RFC 7807). This provides a solid foundation for HTTP errors, while business error codes and correlation IDs can be added as extension fields.

The goal is not to force every exception into HTTP 200 or HTTP 400, but to **preserve accurate HTTP semantics** while providing structured error content usable by both clients and operators.

## 2. Distinguishing Three Codes: HTTP Status, Business Error Code, and Correlation ID

| Component | Example | Purpose | Stability |
|---|---|---|---|
| HTTP status | 400, 404, 409, 429, 500, 503 | Tells HTTP clients, proxies, gateways, and monitoring the outcome class | Defined by HTTP specification; must be accurate |
| Business error code | `PRODUCT_NOT_FOUND`, `INSUFFICIENT_STOCK` | Lets clients branch on specific business failure scenarios | Must be part of contract; kept stable |
| Correlation ID | `req-8f32a62e`, UUID | Finds all logs or requests tied to one transaction | Typically changes per request/interaction |
| Trace ID | 32 hex chars in W3C `traceparent` | Finds the full distributed trace across multiple services | Changes per trace |
| Span ID | 16 hex chars | Identifies a single unit of work inside a trace | Changes per span |
| Problem type URI | `https://api.example.com/problems/insufficient-stock` | Describes the problem category and remediation docs | Stable per problem type |

**HTTP status** answers “did this request succeed or fail at the protocol level?”. **Business code** answers “which product/domain error occurred?”. **Correlation ID** answers “which specific execution should we look up in logs?”. The three roles cannot substitute for one another.

For example, suppose 10,000 order POST calls fail due to insufficient stock. They can share HTTP 409 and business code `INSUFFICIENT_STOCK`, while each has a distinct correlation ID. Never use a correlation ID as a business code, and never use a business code as a request ID.

### 2.1. Do Not Return HTTP 200 with an Error Body

The following is poor design for standard REST APIs:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"success":false,"code":"PRODUCT_NOT_FOUND"}
~~~

HTTP 200 leads proxies, retries, caches, client SDKs, SLOs, and monitoring to treat the request as successful. If a resource does not exist, use the corresponding HTTP 404. If an API uses a custom protocol tunneled over HTTP with different conventions, document it clearly rather than applying this pattern arbitrarily to REST APIs.

### 2.2. Do Not Branch Logic on Error Messages

Clients should never write `if (message.equals("Product not found."))` or search substrings inside `detail`. Messages can be translated into another language, reworded, or include per-request data.

Use `code` or `type` URI instead:

~~~text
if (error.code == "PRODUCT_NOT_FOUND"):
    show product-unavailable state
else if (error.code == "INSUFFICIENT_STOCK"):
    suggest reducing order quantity
else:
    show generic error and correlationId
~~~

This is pseudocode, not complete JavaScript. Uppercase codes are only an illustrative convention; you can use namespaced strings like `INVENTORY.INSUFFICIENT_STOCK` if managed via a shared company catalog.

## 3. RFC 9457 and application/problem+json

RFC 9457 defines the Problem Details structure for HTTP APIs. Spring Framework uses `org.springframework.http.ProblemDetail` alongside the `ErrorResponse` and `ErrorResponseException` abstractions.

Example response:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Correlation-ID: req-8f32a62e

{
  "type": "https://api.example.com/problems/insufficient-stock",
  "title": "Conflict",
  "status": 409,
  "detail": "Requested quantity exceeds available stock.",
  "instance": "urn:uuid:3a82b5af-8a9e-434a-ab68-ae96d51ce4b7",
  "code": "INSUFFICIENT_STOCK",
  "correlationId": "req-8f32a62e"
}
~~~

This sample response illustrates the contract, not output guaranteed out of the box from every project. `api.example.com` is a documentation placeholder; replace it with a domain your project controls and publishes problem types under.

### 3.1. Five Standard Fields

| RFC 9457 Field | Meaning | Notes |
|---|---|---|
| `type` | URI reference identifying the **problem type** | Prefer a stable, documented URI; defaults to `about:blank` when omitted |
| `title` | Short description of the **problem type** | Should stay stable across occurrences of the same `type`, aside from localization |
| `status` | HTTP status code of the response | When present, must match the actual HTTP status; informational |
| `detail` | Explanation for this specific error occurrence, aimed at users/clients | Must omit stack traces, SQL, secrets, or machine-parsed syntax |
| `instance` | URI reference identifying the **specific occurrence** | Can be an opaque non-dereferenceable URI; avoid leaking personal data |

Do not treat `instance` as a field required to contain the request path. RFC 9457 defines `instance` as a reference to the **error occurrence**; some earlier Spring versions auto-populated the current request path if missing, though newer versions may differ. To uniquely identify an occurrence, explicitly assign a UUID URN or an application-managed error-occurrence URI.

Never place query strings containing emails, tokens, passwords, or sensitive search terms into `instance` just for debugging convenience.

### 3.2. Extension Fields for Business Codes and Correlation

RFC 9457 allows extending Problem Details with additional members. With Spring `ProblemDetail`:

~~~java
ProblemDetail problem =
        ProblemDetail.forStatus(HttpStatus.CONFLICT);

problem.setTitle("Conflict");
problem.setDetail("Requested quantity exceeds available stock.");
problem.setProperty("code", "INSUFFICIENT_STOCK");
problem.setProperty("correlationId", "req-8f32a62e");
~~~

This snippet requires importing `ProblemDetail` and `HttpStatus` inside an appropriate Java class or method. With Jackson and standard Spring configuration, entries in `ProblemDetail.properties` are promoted to top-level JSON fields rather than nested inside a `"properties"` object.

Useful extensions include:

- `code`: stable business error code.
- `correlationId`: ID clients can pass to support.
- `errors`: list of validation violations, each with `field` and `rule`.
- `retryable`: optional if contractually well-defined; should not replace HTTP `Retry-After`.
- `documentation`: URL to error docs if the `type` URI does not serve that role.

Do not clutter every response with every extension needlessly. A 500 error may only need a generic code, safe message, and `correlationId`; never expose stack traces or database names.

### 3.3. Content-Type

When using `ProblemDetail`/`ErrorResponse` properly in Spring MVC/WebFlux, the framework prefers **`application/problem+json`** with Jackson. Never manually return a raw JSON String and attach an arbitrary `Content-Type`, as that risks mismatching status/body or breaking content negotiation.

If a client sends an incompatible `Accept` header, the system may respond with 406 or negotiate accordingly. Test media types and headers with realistic clients.

## 4. Designing a Business Error Code Catalog

A good catalog has stable names, clear meanings, consistent status mappings, safe returned data, and clear client recovery actions.

| Business Code | HTTP Status | Meaning | Handling Guidance |
|---|---:|---|---|
| `VALIDATION_FAILED` | 400 | Input data violates schema/constraints | Client fixes fields per `errors` |
| `MALFORMED_REQUEST` | 400 | Body/query malformed, unparseable | Fix request syntax |
| `AUTHENTICATION_REQUIRED` | 401 | Missing or invalid authentication | Log in or refresh token per flow |
| `ACCESS_DENIED` | 403 | Principal identified, lacks permission | Do not retry identically expecting access |
| `PRODUCT_NOT_FOUND` | 404 | Product resource missing or hidden | Verify ID or render empty UI state |
| `INSUFFICIENT_STOCK` | 409 | Inventory state conflicts with request | Reduce quantity / fetch fresh stock |
| `RESOURCE_VERSION_CONFLICT` | 409 | Update attempted on stale version | Refresh and resolve conflict |
| `PRECONDITION_FAILED` | 412 | `If-Match` or precondition not satisfied | Fetch new version, check ETag |
| `RATE_LIMITED` | 429 | Quota/rate limit exceeded | Back off per `Retry-After` when present |
| `DEPENDENCY_UNAVAILABLE` | 503 | Critical dependency temporarily unresponsive | Bounded retry when safe |
| `INTERNAL_ERROR` | 500 | Unexpected failure, cannot expose details | Show generic error and correlation ID |

This table is an **example design**, not a mandate that every project use these exact names. For example, inventory checks could use 422 if the contract treats invalid quantities as semantic unprocessable input, whereas 409 fits when conflicting with current resource state. Pick a consistent convention, document it in OpenAPI, and keep it stable.

### 4.1. One HTTP Status Can Map to Many Business Codes

HTTP 404 can correspond to `PRODUCT_NOT_FOUND`, `ORDER_NOT_FOUND`, or `CUSTOMER_NOT_FOUND`. HTTP 409 can correspond to `INSUFFICIENT_STOCK` or `RESOURCE_VERSION_CONFLICT`. Business codes supply finer granularity while HTTP status preserves standard protocol semantics for HTTP infrastructure.

Conversely, never reuse the same business code for two completely unrelated behaviors unless intentionally contracted. For a code like `ORDER_NOT_FOUND`, clearly define its status, safe detail, and allowed fields.

### 4.2. Avoid Arbitrary Uncatalogued Numeric Codes

Numeric codes like 1001, 1002, 1003 can work, provided there is a registry and namespace preventing collisions. Symbolic namespaced codes (e.g., `INVENTORY.INSUFFICIENT_STOCK`) are usually easier to read when debugging. If an API has already published numeric codes, never swap them for string codes as a breaking change without versioning and a migration plan.

Never embed sensitive data into codes: business codes must have bounded cardinality and never contain emails, usernames, product IDs, or tokens.

### 4.3. Messages and Localization

You can keep `code=INSUFFICIENT_STOCK` fixed while returning localized `detail`:

~~~json
{
  "code": "INSUFFICIENT_STOCK",
  "detail": "Số lượng yêu cầu vượt tồn kho khả dụng."
}
~~~

Or for `Accept-Language="en"`:

~~~json
{
  "code": "INSUFFICIENT_STOCK",
  "detail": "Requested quantity exceeds available stock."
}
~~~

These snippets illustrate the fields. Spring `ErrorResponse` supports `MessageSource` message codes for `type`/`title`/`detail`, or apps can resolve resource bundles directly. **Clients must never parse `detail` to drive logic.** Across translations, `code` and HTTP status remain unchanged.

## 5. Correlation ID vs. W3C Trace Context

A system may carry both `X-Correlation-ID` and `traceparent`. They are related, not identical.

**Correlation ID** is an application-contract identifier used to locate a request or business operation across logs. The header may be `X-Correlation-ID` or `X-Request-ID`; there is no single mandatory header name across all REST APIs.

**Trace ID** is part of distributed tracing, propagated via W3C Trace Context. Version 00 of the `traceparent` header has the structure:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Where:
- `00` is the version.
- `4bf92f3577b34da6a3ce929d0e0e4736` is the 32-hex-character trace-id (not all zeros).
- `00f067aa0ba902b7` is the 16-hex-character parent-id/span-id (not all zeros).
- `01` is trace flags, carrying the sampled bit per spec.

Clients should not randomly edit `traceparent` without understanding the spec; prefer OpenTelemetry, Micrometer Tracing, or standard instrumentation libraries. `tracestate` can carry vendor context and requires size and security validation.

### 5.1. Can Trace ID Serve as the Correlation ID?

You can **intentionally** choose `traceId` as your lookup identifier if the entire system shares unified tracing, sampling rules, and log correlation. Just never assume they are automatically identical.

A correlation ID may originate from an API Gateway or a user request. A trace can span multiple requests or spans, and a request may join an existing trace. If tracing is disabled, lacks context, or resets IDs, an independent correlation ID remains valuable.

Never treat arbitrary `X-Correlation-ID` header values as valid W3C trace IDs; their formats and semantics differ.

### 5.2. Should Business Error Codes and Correlation IDs Appear in Both Headers and Body?

A practical convention:

- Server returns `X-Correlation-ID` in the HTTP response header, even on success.
- On error responses, also include `correlationId` inside `ProblemDetail` so clients can display it or send it to support.
- Logs include a matching `correlationId` field.
- When tracing is enabled, logs also record `traceId`/`spanId` from instrumentation; exposing all internal span metadata in public responses is unnecessary.

Clients can record response status, business code, `correlationId`, timestamp, and endpoint (never storing secrets). Log systems query by `correlationId` consistently.

## 6. Rules for Generating, Accepting, and Propagating Correlation IDs

A simple, explicit policy:

1. At a trusted ingress/gateway, inspect the incoming correlation header.
2. If missing or invalid, generate a new ID.
3. Enforce length, character set, and header count limits; reject CR/LF or log-injection characters.
4. Store the ID in the request context and attach it to the logging context.
5. Echo it in the response header and error body.
6. When making downstream HTTP calls, propagate the correlation ID per system policy.
7. Downstream services must not overwrite the ID mid-transaction if the contract requires preserving it.
8. Across trust boundaries, never blindly trust external client headers as internal identifiers or security keys.

Example format: `[A-Za-z0-9._-]{8,64}`, or strictly UUIDs if the system controls all IDs. This is an illustrative policy, not a universal standard. Accepting a syntactically valid ID **does not prove it is trustworthy**: external clients could intentionally reuse someone else's ID. For public Internet APIs, a safer choice is always issuing gateway/server-owned IDs and recording untrusted inbound IDs in a separate field if truly needed.

Never use emails, access tokens, account numbers, IP addresses, or usernames as correlation IDs. IDs must be opaque identifiers with adequate entropy and zero sensitive data.

### 6.1. Correlation ID Is Not an Idempotency Key

In payment or order-creation APIs, a correlation ID only supports tracing. **`Idempotency-Key`** is designed to prevent duplicate execution on retries, backed by durable storage and deduplication rules. Never substitute a correlation ID for `Idempotency-Key` unless the system explicitly contracts and enforces its semantics, TTL, principal scoping, and payload matching.

A retried request may receive a new correlation ID or keep the existing one per tracing policy, yet deduplication must never depend on that choice.

## 7. Integrating in Spring Boot MVC with Java 17+

The illustrative example runs on **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+, Spring MVC/Servlet, and embedded Tomcat**. It uses:
- RFC 9457 `ProblemDetail`.
- `ErrorCode` enum as the business code catalog.
- `BusinessException` carrying only the business error code.
- `OncePerRequestFilter` generating or validating the correlation ID and writing it to SLF4J MDC.
- `@RestControllerAdvice` extending `ResponseEntityExceptionHandler` to standardize most errors from annotated MVC controllers.
- `MockMvc` verifying the contract and correlation IDs.

Newer versions may change some hooks or default behaviors; check the exact Spring Framework Javadoc managed by your project. Especially, do not assume enabling Problem Details forces Servlet containers, `/error`, gateways, and security filters to automatically share the exact same schema.

### 7.1. Dependencies and Project Structure

In a Gradle project configured with the Spring Boot plugin and Maven Central (such as one generated by Spring Initializr), dependencies are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

These cover MVC, JSON/Jackson, SLF4J, and Bean Validation in a typical Boot 3.3 demo. Do not add `spring-boot-starter-webflux` to this project just to use `WebClient`; a separate reactive example appears later.

File layout:

~~~text
src/main/java/dev/example/errors/
    ErrorDemoApplication.java
    ErrorCode.java
    BusinessException.java
    CorrelationIdFilter.java
    ApiErrorAdvice.java
    ProductController.java
src/main/resources/application.yml
src/test/java/dev/example/errors/
    ErrorContractTest.java
~~~

### 7.2. Main Class

File `src/main/java/dev/example/errors/ErrorDemoApplication.java`:

~~~java
package dev.example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorDemoApplication.class, args);
    }
}
~~~

The remaining classes live in the same `dev.example.errors` package so component scanning detects them.

### 7.3. Business Error Code Catalog

File `src/main/java/dev/example/errors/ErrorCode.java`:

~~~java
package dev.example.errors;

import org.springframework.http.HttpStatus;

public enum ErrorCode {

    PRODUCT_NOT_FOUND(
            HttpStatus.NOT_FOUND,
            "Product not found."),

    INSUFFICIENT_STOCK(
            HttpStatus.CONFLICT,
            "Requested quantity exceeds available stock.");

    private final HttpStatus status;
    private final String safeDetail;

    ErrorCode(HttpStatus status, String safeDetail) {
        this.status = status;
        this.safeDetail = safeDetail;
    }

    public HttpStatus status() {
        return status;
    }

    public String safeDetail() {
        return safeDetail;
    }
}
~~~

`ErrorCode` maps business codes to HTTP statuses and safe messages. Real projects can add i18n message keys, documentation URIs, retry policies, and versioning policies. Never put raw database technical exception messages directly into `safeDetail`.

### 7.4. BusinessException

File `src/main/java/dev/example/errors/BusinessException.java`:

~~~java
package dev.example.errors;

public final class BusinessException extends RuntimeException {

    private final ErrorCode errorCode;

    public BusinessException(ErrorCode errorCode) {
        super(errorCode.safeDetail());
        this.errorCode = errorCode;
    }

    public ErrorCode errorCode() {
        return errorCode;
    }
}
~~~

This exception represents intentional domain/catalog errors, distinct from `NullPointerException`, `SQLException`, or unforeseen programming bugs. Carrying a stable code lets controller advice decide status and response without parsing exception message strings.

### 7.5. CorrelationIdFilter for Servlet MVC

File `src/main/java/dev/example/errors/CorrelationIdFilter.java`:

~~~java
package dev.example.errors;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Correlation-ID";
    public static final String ATTRIBUTE = "correlationId";

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{8,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String proposed = request.getHeader(HEADER);
        String correlationId = proposed != null
                && SAFE_ID.matcher(proposed).matches()
                ? proposed
                : UUID.randomUUID().toString();

        request.setAttribute(ATTRIBUTE, correlationId);
        response.setHeader(HEADER, correlationId);

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable(ATTRIBUTE, correlationId)) {
            chain.doFilter(request, response);
        }
    }
}
~~~

This is a valid class for the Servlet stack with Spring Boot 3.x/Jakarta Servlet. The filter places the ID into the Servlet request attribute and response header **before** MVC processes the request, allowing controller advice to read the same ID. `MDC.putCloseable` clears the thread context after the request so it does not leak onto other tasks in the thread pool.

**Important limitation:** this snippet accepts incoming IDs that match the format; that works in a demo or behind a trusted ingress that validates/replaces headers. On public endpoints, consider always generating an internal correlation ID or trusting headers only from trusted proxies. The filter does not verify header origin itself.

Servlet async dispatches and error dispatches may execute on different threads/dispatches from the initial request. `OncePerRequestFilter` has default rules around async/error dispatches; MDC stays bound only within the `try` block and **does not automatically cross `CompletableFuture`, thread pools, or reactive pipelines**. Production requires context-propagation/observability integration and testing of async/error flows. Setting the response header early ensures the ID appears on many error paths, yet does not guarantee errors outside Servlet MVC share the same JSON body.

### 7.6. RestControllerAdvice Standardizing ProblemDetail

File `src/main/java/dev/example/errors/ApiErrorAdvice.java`:

~~~java
package dev.example.errors;

import java.net.URI;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.ServletWebRequest;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    public record FieldIssue(String field, String rule) {}

    @ExceptionHandler(BusinessException.class)
    protected ResponseEntity<Object> handleBusiness(
            BusinessException ex, WebRequest request) {

        ProblemDetail problem =
                ProblemDetail.forStatus(ex.errorCode().status());

        problem.setDetail(ex.errorCode().safeDetail());
        problem.setProperty("code", ex.errorCode().name());

        return handleExceptionInternal(
                ex, problem, new HttpHeaders(),
                ex.errorCode().status(), request);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatus(status);
        problem.setDetail("Submitted data is invalid.");
        problem.setProperty("code", "VALIDATION_FAILED");

        List<FieldIssue> issues = ex.getBindingResult()
                .getFieldErrors().stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        error.getCode() == null
                                ? "Invalid"
                                : error.getCode()))
                .toList();

        problem.setProperty("errors", issues);

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    @ExceptionHandler(Exception.class)
    protected ResponseEntity<Object> handleUnexpected(
            Exception ex, WebRequest request) {

        logger.error("Unhandled request exception", ex);

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);

        problem.setDetail(
                "The system could not process the request. "
                + "Please provide the correlation ID when contacting support.");
        problem.setProperty("code", "INTERNAL_ERROR");

        return handleExceptionInternal(
                ex, problem, new HttpHeaders(),
                HttpStatus.INTERNAL_SERVER_ERROR, request);
    }

    @Override
    protected ResponseEntity<Object> createResponseEntity(
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = body instanceof ProblemDetail pd
                ? pd
                : ProblemDetail.forStatus(status);

        if (problem.getProperties() == null
                || !problem.getProperties().containsKey("code")) {
            problem.setProperty(
                    "code",
                    status.is5xxServerError()
                            ? "INTERNAL_ERROR"
                            : "HTTP_" + status.value());
        }

        if (status.is5xxServerError()) {
            problem.setDetail(
                    "The system could not process the request. "
                    + "Please provide the correlation ID when contacting support.");
        }

        String correlationId = UUID.randomUUID().toString();

        if (request instanceof ServletWebRequest servletRequest) {
            Object value = servletRequest.getRequest()
                    .getAttribute(CorrelationIdFilter.ATTRIBUTE);

            if (value instanceof String saved) {
                correlationId = saved;
            }
        }

        problem.setProperty("correlationId", correlationId);
        headers.set(CorrelationIdFilter.HEADER, correlationId);

        // Instance identifies a single error occurrence, never using raw query.
        problem.setInstance(
                URI.create("urn:uuid:" + UUID.randomUUID()));

        if ("about:blank".equals(problem.getType().toString())) {
            String code = (String) problem.getProperties().get("code");
            problem.setType(URI.create(
                    "https://api.example.com/problems/"
                    + code.toLowerCase(Locale.ROOT)
                          .replace('_', '-')));
        }

        return super.createResponseEntity(
                problem, headers, status, request);
    }
}
~~~

This example focuses on **one error contract**, not every possible exception in a system. The class extends `ResponseEntityExceptionHandler` to standardize supported framework errors; `@ExceptionHandler(BusinessException.class)` handles domain errors; `@ExceptionHandler(Exception.class)` acts as a fallback for unhandled exceptions inside MVC controllers.

Key points:

1. `ProblemDetail.forStatus(...)` creates the appropriate status; the actual returned HTTP status comes from `ResponseEntity`. Never set `body.status=400` while returning HTTP 200.
2. `createResponseEntity` is a hook in `ResponseEntityExceptionHandler` used to attach `code`, `correlationId`, and `instance` across errors flowing through MVC exception handling.
3. If a business code is already set, it is not overwritten by generic `HTTP_400`.
4. Validation errors contain only `field` and `rule`; **never return `rejectedValue`** (which may contain passwords, tokens, or personal data).
5. 5xx errors receive a generic detail without revealing exception details.
6. `correlationId` comes from the filter-set request attribute, so header and body carry the same ID on normal paths.
7. `instance` uses a fresh UUID URN per occurrence instead of copying a request URL with sensitive queries.
8. The `type` URI uses placeholder domain `api.example.com`; in production replace it with a stable domain you own and publish problem-type documentation. Never advertise placeholders as live endpoints.

**Caution on fallbacks:** a `@RestControllerAdvice` does not automatically catch errors from Servlet Filters before `DispatcherServlet`, container error dispatches, API Gateways, or already-committed responses. To unify responses system-wide, add corresponding mechanisms at each boundary and test them as covered in Section 11.

**Caution on logging:** `logger.error(..., ex)` helps investigation, yet requires policies for masking sensitive data, retention, and access control. Never print raw request bodies, `Authorization` headers, session cookies, or personal information into exception logs.

### 7.7. Controller Demonstrating Domain and Validation Errors

File `src/main/java/dev/example/errors/ProductController.java`:

~~~java
package dev.example.errors;

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
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    public record Product(long id, String name) {}

    public record ReserveRequest(
            @NotBlank String sku,
            @NotNull @Min(1) Integer quantity) {}

    public record Reservation(String sku, int quantity) {}

    @GetMapping("/{id}")
    public Product find(@PathVariable long id) {
        if (id != 1L) {
            throw new BusinessException(ErrorCode.PRODUCT_NOT_FOUND);
        }

        return new Product(1L, "Mechanical keyboard");
    }

    @PostMapping("/reserve")
    public ResponseEntity<Reservation> reserve(
            @Valid @RequestBody ReserveRequest request) {

        if (request.quantity() > 5) {
            throw new BusinessException(
                    ErrorCode.INSUFFICIENT_STOCK);
        }

        Reservation reservation = new Reservation(
                request.sku(), request.quantity());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(reservation);
    }
}
~~~

In the demo, product `ID=1` is treated as existing with a max stock of 5 units. This is simulated logic to demonstrate HTTP status and business code, not a production inventory algorithm. In real systems, checking and reserving stock requires proper concurrency control, transactions, and idempotency.

### 7.8. application.yml

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  mvc:
    problemdetails:
      enabled: false

logging:
  pattern:
    level: "%5p [corr:%X{correlationId:-}]"
~~~

Here the project **explicitly** provides `ApiErrorAdvice extends ResponseEntityExceptionHandler`, so `spring.mvc.problemdetails.enabled=false` avoids also relying on Boot's auto-configured `ResponseEntityExceptionHandler`. If you only want the framework to return `ProblemDetail` for web exceptions by default, set `spring.mvc.problemdetails.enabled=true` and add a properly ordered advice for business errors.

The Logback/SLF4J pattern illustrates the MDC `correlationId` field. In production, prefer structured JSON logs with dedicated fields for `code`, `status`, `correlationId`, `traceId`, `spanId`, `serviceName`, `environment`, and `timestamp` rather than parsing arbitrary text strings.

When tracing auto-configuration is active, avoid building two separate trace-ID generators. If the system already logs `traceId`, treat `correlationId` as an additional API-contract field.

## 8. Running the Demo and Verifying Each Case

From the project directory with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 8.1. Success Response with Header

~~~bash
curl -i http://localhost:8080/api/products/1
~~~

HTTP 200 with simulated JSON body:

~~~json
{"id":1,"name":"Mechanical keyboard"}
~~~

The `X-Correlation-ID` response header carries the ID generated or accepted by the filter. Do not include error codes in successful response bodies; a success response is not a problem response.

### 8.2. Business Error 404

~~~bash
curl -i -H "X-Correlation-ID: req-product12345" \
  http://localhost:8080/api/products/9
~~~

What to verify: HTTP 404, `Content-Type` compatible with `application/problem+json`, `X-Correlation-ID=req-product12345`, body containing:

~~~json
{
  "status": 404,
  "code": "PRODUCT_NOT_FOUND",
  "correlationId": "req-product12345",
  "detail": "Product not found."
}
~~~

This JSON shows only the key fields to observe; the full `ProblemDetail` response also includes `type`/`title`/`instance` and any framework-populated fields. The ID in the example falls within the filter's allowed character set.

### 8.3. Business Error 409

~~~bash
curl -i -X POST \
  http://localhost:8080/api/products/reserve \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: req-order987654" \
  -d '{"sku":"KB-001","quantity":9}'
~~~

What to verify: HTTP 409, body `code=INSUFFICIENT_STOCK`, `status=409`, and `correlationId=req-order987654`; response header `X-Correlation-ID` carries the same ID.

### 8.4. Validation Error 400

~~~bash
curl -i -X POST \
  http://localhost:8080/api/products/reserve \
  -H "Content-Type: application/json" \
  -d '{"sku":"","quantity":0}'
~~~

Result: HTTP 400, `code=VALIDATION_FAILED`. The `errors` extension contains entries for `sku` (`NotBlank`) and `quantity` (`Min`). Clients should not assume field error ordering is invariant.

### 8.5. Malformed JSON and Framework Errors

~~~bash
curl -i -X POST \
  http://localhost:8080/api/products/reserve \
  -H "Content-Type: application/json" \
  -d '{"sku":'
~~~

The request has invalid syntax; Spring can return HTTP 400 from the HTTP message reader. In the demo, it passes through `ResponseEntityExceptionHandler` and receives the `ProblemDetail` schema with `correlationId` and generic code `HTTP_400` unless a dedicated mapping is added.

Not every 400 error should carry `code=VALIDATION_FAILED`. **Malformed JSON** differs from a **Bean Validation failure**; you can assign a dedicated `MALFORMED_REQUEST` code if clients need to distinguish them, updated centrally and covered by tests.

## 9. Contract Testing with MockMvc

When standardizing error structure, tests must check more than status codes: check `Content-Type`, `code`, `correlationId` in both header and body, field violations, and absence of unsafe data leaks.

File `src/test/java/dev/example/errors/ErrorContractTest.java`:

~~~java
package dev.example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void notFoundHasBusinessCodeAndCorrelationId()
            throws Exception {

        mvc.perform(get("/api/products/9")
                .header("X-Correlation-ID", "req-product12345"))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.valueOf("application/problem+json")))
                .andExpect(header().string(
                        "X-Correlation-ID", "req-product12345"))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"))
                .andExpect(jsonPath("$.correlationId").value(
                        "req-product12345"));
    }

    @Test
    void inventoryConflictUses409AndStableCode()
            throws Exception {

        mvc.perform(post("/api/products/reserve")
                .header("X-Correlation-ID", "req-order987654")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"KB-001\",\"quantity\":9}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value(
                        "INSUFFICIENT_STOCK"))
                .andExpect(jsonPath("$.correlationId").value(
                        "req-order987654"));
    }

    @Test
    void invalidBodyProvidesFieldIssuesWithoutValues()
            throws Exception {

        mvc.perform(post("/api/products/reserve")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"\",\"quantity\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(
                        "VALIDATION_FAILED"))
                .andExpect(jsonPath("$.errors").isArray());
    }

    @Test
    void unsafeIncomingHeaderIsReplaced()
            throws Exception {

        mvc.perform(get("/api/products/9")
                .header("X-Correlation-ID", "bad id with spaces"))
                .andExpect(status().isNotFound())
                .andExpect(header().exists("X-Correlation-ID"))
                .andExpect(jsonPath("$.correlationId").exists());
    }

    @Test
    void successStillCarriesCorrelationHeader()
            throws Exception {

        mvc.perform(get("/api/products/1"))
                .andExpect(status().isOk())
                .andExpect(header().exists("X-Correlation-ID"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

In this example, tests verify the contract at the MVC and filter layers using `MockMvc`. They do not automatically prove API Gateways, proxies, Servlet container error dispatch, or cloud tracing work properly; add integration tests against a real server or staging environment.

**Schema testing note:** dynamic fields like `instance` and UUIDs must not be asserted against fixed literal strings. Assert format and uniqueness across calls if required by your contract. In production tests, also verify `body.status` matches HTTP status, header `correlationId` matches body, and 500 errors leak no SQL/stack traces.

## 10. HTTP Status and Retry Semantics

A unified error contract must tell clients whether to retry and how. Never rely solely on a business code to conclude “retry every error”.

| Status | Example | Typical Retry Behavior |
|---|---|---|
| 400 | Malformed JSON, validation failed | Do not retry identically; fix the request |
| 401 | Unauthenticated | Run auth flow; avoid infinite retries |
| 403 | Forbidden | Do not retry identically hoping for permissions |
| 404 | Resource not found | Depends on use case; typically do not retry immediately |
| 409 | Stock/version conflict | May need to refresh state and modify payload |
| 412 | ETag/precondition failed | Fetch latest version and resolve conflict |
| 422 | Payload understood, violates rules | Fix data or workflow |
| 429 | Rate limit | Back off, check `Retry-After` |
| 500 | Unexpected internal error | Retry only if operation is safe/idempotent and bounded |
| 502/503/504 | Gateway/upstream unresponsive | Can retry with backoff/jitter when safe |

If a 429/503 response includes `Retry-After`, clients should honor it within contract limits; a `retryable` body field if present is a business hint rather than a replacement for HTTP semantics. A POST request with side effects needs an `Idempotency-Key` or deduplication mechanism before automated retries.

Error codes help classify outcomes; they do not magically make a non-idempotent operation safe to retry.

## 11. Actual Coverage Scope: ControllerAdvice Does Not Catch Every Error

A unified error design can fail if you assume `@RestControllerAdvice` covers the entire HTTP stack. In Spring Boot MVC, requests can be rejected or fail **before** reaching `DispatcherServlet`.

Areas requiring separate verification:

| Origin | Guaranteed to Pass Through @RestControllerAdvice? | Extension Point |
|---|---|---|
| Exception inside annotated controller | Usually yes while MVC can write response | `@ExceptionHandler` / `ResponseEntityExceptionHandler` |
| Bean Validation `@Valid @RequestBody` | Usually yes | `handleMethodArgumentNotValid` |
| Spring 6.1+ method validation | Usually yes | `handleHandlerMethodValidationException` |
| Spring Security authentication/authorization | Not guaranteed | `AuthenticationEntryPoint`, `AccessDeniedHandler` |
| Servlet Filter throwing before MVC | Not guaranteed | Filter error handling, container `/error` |
| Servlet container error dispatch | Not guaranteed | `ErrorController` / `ErrorAttributes` |
| Default `BasicErrorController` | Can emit legacy JSON | Customize Boot error handling |
| Reverse proxy/load balancer/gateway | No | Configure error mapping at the gateway |
| Closed connection / committed response | Cannot always rewrite body | Logs/metrics/client-side handling |
| WebFlux `WebFilter`/`WebExceptionHandler` | Different from Servlet MVC | Appropriate reactive error handlers |

### 11.1. /error and BasicErrorController

In Spring Boot MVC, errors unhandled by controller advice may route through error dispatch and `BasicErrorController` using `DefaultErrorAttributes`. Depending on version and configuration, the response may use legacy structure like `timestamp`/`status`/`error`/`path` rather than RFC 9457.

**Enabling `spring.mvc.problemdetails.enabled` is not an absolute guarantee** that every `BasicErrorController` response, container 404, or proxy error turns into `ProblemDetail`. If the contract requires every response to share one schema, plan and design further:

- How to transform `ErrorAttributes` or replace `ErrorController` safely.
- Mapping status, error code, and `correlationId` inside `/error`.
- Handling HTML error pages, content negotiation, and client `Accept` headers.
- Error dispatch interaction with filters/security: verifying headers and request attributes survive.
- Integration tests for pre-MVC failures, static resources, unknown routes, and security.

Do not replace `BasicErrorController` with a `@RequestMapping("/error")` controller without understanding the container lifecycle; doing so can alter statuses/headers, cause loops, or emit unexpected HTML/JSON errors.

### 11.2. Spring Security Requires Dedicated Configuration

A 401 from a Security filter normally bypasses MVC controller advice. On the Servlet stack, `AuthenticationEntryPoint` and `AccessDeniedHandler` can build safe `ProblemDetail` bodies with `code` and `correlationId`. To avoid duplicate code, extract a shared **`ErrorResponseFactory`** for both MVC advice and security handlers while ensuring classes do not over-couple to one request abstraction.

Never expose details such as “username already exists”, “who signed the token”, or “exactly how JWT verification failed” if doing so aids attackers or account enumeration. A generic `AUTHENTICATION_REQUIRED` code works best externally, while protected logs retain technical details.

### 11.3. Inspecting Error Bodies from Downstream and Gateways

When a service calls downstream and receives a `ProblemDetail`, do not automatically forward that raw body to clients. It can contain internal service names, object IDs, or error codes outside your public API contract.

At the BFF/gateway boundary, map downstream codes to stable public codes while keeping trace/correlation links in logs. Never expose service topology or access tokens accidentally returned by a downstream service.

## 12. Spring WebFlux: Using WebFilter and Reactive Error Handling

A Spring WebFlux reactive server uses `DispatcherHandler`/`WebHandler`, `WebFilter`, and `WebExceptionHandler` instead of Servlet `DispatcherServlet`/`OncePerRequestFilter`. Final payloads can still use `ProblemDetail`, **yet never copy MVC `ResponseEntityExceptionHandler` method signatures verbatim** to WebFlux: WebFlux uses reactive methods and accepts `ServerWebExchange`.

### 12.1. WebFilter Placing correlationId in Exchange and Reactor Context

File `ReactiveCorrelationFilter.java` in a separate Spring Boot WebFlux project:

~~~java
package dev.example.reactiveerrors;

import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class ReactiveCorrelationFilter implements WebFilter {

    public static final String KEY = "correlationId";
    public static final String HEADER = "X-Correlation-ID";

    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{8,64}");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String candidate = exchange.getRequest()
                .getHeaders().getFirst(HEADER);

        String id = candidate != null && SAFE.matcher(candidate).matches()
                ? candidate
                : UUID.randomUUID().toString();

        exchange.getAttributes().put(KEY, id);
        exchange.getResponse().getHeaders().set(HEADER, id);

        return chain.filter(exchange)
                .contextWrite(context -> context.put(KEY, id));
    }
}
~~~

This is a runnable class for Spring WebFlux/Reactor in a Java 17+ project with `starter-webflux`. Exchange attributes let error handlers read the ID; Reactor Context carries metadata across the **reactive subscription chain**. Never call `MDC.put(...)` around a `Mono`-returning call expecting MDC to persist across event-loop threads: traditional MDC is `ThreadLocal` and needs a context-propagation bridge for full log correlation.

**The trust boundary still applies:** this class checks syntax, not trustworthiness of incoming headers. On public APIs, consider generating a fresh ID at ingress.

### 12.2. Reactive @RestControllerAdvice for Business Errors

Snippet requiring compatible `BusinessException` and `ErrorCode` in the WebFlux project without Servlet imports:

~~~java
@RestControllerAdvice
public class ReactiveBusinessErrorAdvice {

    @ExceptionHandler(BusinessException.class)
    public Mono<ResponseEntity<ProblemDetail>> onBusiness(
            BusinessException ex,
            ServerWebExchange exchange) {

        ProblemDetail problem =
                ProblemDetail.forStatus(ex.errorCode().status());

        problem.setDetail(ex.errorCode().safeDetail());
        problem.setProperty("code", ex.errorCode().name());

        String id = exchange.getAttribute(
                ReactiveCorrelationFilter.KEY);

        if (id != null) {
            problem.setProperty("correlationId", id);
        }

        problem.setInstance(
                URI.create("urn:uuid:" + UUID.randomUUID()));

        return Mono.just(ResponseEntity
                .status(ex.errorCode().status())
                .body(problem));
    }
}
~~~

This is a **snippet**: add package/imports and the project's `BusinessException`/`ErrorCode` classes. It illustrates constructing `ProblemDetail` without calling `block()`. To standardize framework errors in WebFlux, extend **WebFlux's** `ResponseEntityExceptionHandler` or design an `ErrorWebExceptionHandler` at the `WebHandler` boundary.

### 12.3. Propagating IDs Downstream to WebClient via Reactor Context

When `WebClient` sends downstream requests, use an `ExchangeFilterFunction` reading Reactor Context:

~~~java
@Bean
WebClient downstreamClient(WebClient.Builder builder) {
    return builder.filter((request, next) ->
            Mono.deferContextual(context -> {
                String id = context.getOrDefault(
                        "correlationId", "");

                ClientRequest.Builder changed =
                        ClientRequest.from(request);

                if (!id.isBlank()) {
                    changed.headers(headers ->
                            headers.set("X-Correlation-ID", id));
                }

                return next.exchange(changed.build());
            }))
            .build();
}
~~~

This is a `@Bean` method snippet requiring `WebClient`, `ClientRequest`, `Mono`, `Bean`, and a `@Configuration` class. It assumes the reactive flow chains normally within a request and the context was populated by `WebFilter`. If an app subscribes to detached publishers, runs standalone jobs, or bridges into thread-local code without propagation, metadata may be missing.

Likewise, when using Micrometer Tracing/OpenTelemetry, **let instrumentation manage `traceparent`/`tracestate`** rather than writing a custom filter fabricating non-standard trace IDs. An application correlation header is a separate contract from standard trace propagation.

### 12.4. ErrorWebExceptionHandler and Committed Responses

In WebFlux, exceptions unhandled by annotated advice can reach `WebExceptionHandler` or Spring Boot's error handler. If a response has already committed due to streaming a `Flux` or sending headers, a late error cannot be converted into a fresh JSON `ProblemDetail`. Log correlation/trace IDs, handle cancellation, and design appropriate streaming protocols.

Never call `block()` inside `WebExceptionHandler` to query services or logs; handlers must return `Mono<Void>` and compose Publishers properly.

## 13. Distributed Tracing, Micrometer, and Logs

Across microservices, leverage Micrometer Observation/Tracing or OpenTelemetry. Instrumentation automatically creates traces/spans, propagates W3C `traceparent` across HTTP clients, and injects `traceId`/`spanId` into logs when configured. An application's correlation ID can sit alongside as an extra field rather than replacing telemetry frameworks.

Structured log example:

~~~json
{
  "timestamp": "2026-11-07T14:32:00Z",
  "service": "inventory-api",
  "level": "WARN",
  "httpStatus": 409,
  "errorCode": "INSUFFICIENT_STOCK",
  "correlationId": "req-order987654",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "message": "Reservation rejected by inventory policy"
}
~~~

This is a simulated log entry, not live system data. Never dump raw user inputs, access tokens, or sensitive content into logs just to improve searchability.

### 13.1. Structured Logging and MDC

In Servlet MVC, MDC works well during synchronous single-thread execution; a filter sets `correlationId` before the chain and clears it in `finally`. With async controllers, `@Async`, or Reactor, use context propagation; never pass MDC via static variables or uncleaned `ThreadLocal`s.

In WebFlux, prefer Reactor Context and Micrometer context propagation/tracing. If bridging into MDC at logging boundaries, use a dedicated bridge library and test across scheduler switches. Never use MDC as the sole source of truth for `correlationId` in reactive flows.

### 13.2. Looking Up Logs by Correlation ID

A production support workflow:

1. Client hits a 409 error and captures `code`, `correlationId`, timestamp, and route.
2. Support searches logs by `correlationId`, scoped by service and time window.
3. Trace upstream/downstream across the API Gateway and services propagating the same ID or trace context.
4. If tracing is enabled, use `traceId` to inspect spans and latency.
5. Inspect domain or dependency errors in logs rather than relying solely on raw exception text reported by the client.
6. Verify idempotency and prior side effects before deciding to retry.
7. Fix the root cause and add a regression test for the exact error code/status.

Never ask clients to send stack traces or tokens for debugging when correlation/trace data already allows authorized operators to inspect protected logs.

## 14. Security of an Error Contract

Error responses are an information-disclosure surface. Rules:

- Never return `ex.getStackTrace()`, internal class names, file paths, SQL queries, connection strings, or database schema info.
- Never echo the full `@RequestBody` inside validation errors.
- Never return `rejectedValue` containing passwords, tokens, account numbers, or personal data.
- Never expose token-verification details or unauthorized usernames/tenant names.
- Never put PII inside `correlationId`, `type` URI, `instance` URI, or metric tags.
- Validate inbound ID headers to prevent CR/LF log injection, oversized values, and unbounded cardinality.
- For 500 errors, show safe messages while keeping stack traces in access-controlled logs.
- Never trust forwarded/correlation headers from outside your trust boundary.
- Enforce authentication/authorization on any endpoint that lets users inspect details of an `instance` URI.
- Ensure error codes do not reveal existence of resources the caller cannot access; security policies sometimes intentionally return 404 instead of 403.
- Review cache behavior on error responses so sensitive error details are never cached in shared proxies.

### 14.1. Status, CORS, and Browser Clients

If a frontend runs cross-origin, `X-Correlation-ID` is a custom response header; JavaScript can read it only when CORS policy **exposes** the header, e.g., `Access-Control-Expose-Headers: X-Correlation-ID`. Configure this in Spring Security/CORS or the gateway depending on architecture. Never add wildcard exposure alongside credentials policies without understanding the impact.

Ensure body `correlationId` and header match. Even if CORS prevents a browser from reading a custom header, the body can still deliver the ID on JSON errors permitted by CORS, whereas network/CORS failures may block the client from reading the response at all.

## 15. Designing Validation Error Responses

Inputs with multiple invalid fields need a stable machine-readable structure. The `errors` extension in `ProblemDetail` can be an array:

~~~json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Bad Request",
  "status": 400,
  "detail": "Submitted data is invalid.",
  "instance": "urn:uuid:ef0db84d-4c3f-4c16-a06f-522ba2c7139d",
  "code": "VALIDATION_FAILED",
  "correlationId": "req-validate12345",
  "errors": [
    {"field": "sku", "rule": "NotBlank"},
    {"field": "quantity", "rule": "Min"}
  ]
}
~~~

This is an illustrative example, not static output of any fixed request. Error order should not be part of the contract unless deterministic sorting is explicitly specified.

**Should include**:
- `field` or JSON pointer, when safe to expose.
- `rule` or per-field error code, invariant across languages.
- Safe localized message if required by the UI.
- Omit `rejectedValue` by default; if included, enforce strict protection policies.

**Do not treat** every HTTP 400 as `VALIDATION_FAILED`. Malformed JSON, missing headers, unsupported encodings, or type conversion mismatches should be distinguished if clients take different actions. Otherwise, a generic `HTTP_400` is better than inventing an inaccurate specific code.

### 15.1. Bean Validation and Method Validation Across Versions

Spring Framework 6.1+ includes built-in controller method validation for direct constraints on parameters/return values, raising `HandlerMethodValidationException`, whereas `@Valid @RequestBody` object validation raises `MethodArgumentNotValidException` in MVC. WebFlux object validation typically produces `WebExchangeBindException`.

To keep contracts aligned, handle both types on your active web stack. In MVC, `ResponseEntityExceptionHandler` provides `handleHandlerMethodValidationException` in Framework 6.1+. Never force server-side return-value validation errors into HTTP 400: they are typically 500 server errors.

The MVC demo above overrides `handleMethodArgumentNotValid`. If you add `@Min` directly on `@RequestParam`, also override the method-validation hook or rely on `createResponseEntity` so `code` and `correlationId` remain present. If the API wants `code=VALIDATION_FAILED` consistently for **input method validation**, distinguish it from return-value failures and map accordingly.

### 15.2. How Should Clients Consume the Error List?

Frontends can use `errors` to place hints next to matching fields. If a field is unrecognized, fall back to displaying the general `detail`. Never assume `errors` is always present: 503 or 409 responses typically have no field errors. Clients should parse optional extensions gracefully and ignore unknown fields per RFC extensibility rules.

## 16. Coordinating with API Gateways and Multiple Microservices

When multiple backend frameworks serve one product (Spring MVC, WebFlux, Node.js, Go), publish a **shared error schema** at the API contract level rather than letting each framework invent its own.

A coordinated flow:

~~~text
Client request
  |
  v
Gateway: issues/validates correlation ID, starts trace context
  |
  +-- Service A: handles HTTP request, validation, domain
  |      |
  |      +-- downstream Service B: returns internal status/code
  |      |
  |      +-- maps to public HTTP status and public error code
  |
  v
Gateway: preserves status, headers, and contract-compliant body
  |
  v
Client: reads status + code + correlationId
  |
  v
Support: queries logs by correlationId, traces by traceId
~~~

Do not let the gateway flatten all upstream errors to 200 or turn 409 into 500, or clients will misbehave. If the gateway must mask internal errors, configure explicit mappings, test them, and log both internal and public codes where permitted.

### 16.1. Errors Generated Solely by the Gateway

Gateways can return 413, 429, 502, 503, and 504 before requests ever reach a Spring controller. If absolute uniformity is required, the gateway itself must emit the same Problem Details contract and attach/echo `X-Correlation-ID`. Spring `@ControllerAdvice` cannot handle errors returned by the gateway before forwarding.

### 16.2. When Downstream Services Use Different Business Codes

Suppose Service A's public API uses `INVENTORY_UNAVAILABLE`, while Service B returns warehouse/slot-specific codes. Service A can map those into one documented public code while logging the internal code and correlation/trace ID.

Never forward raw downstream `ProblemDetail` payloads if they expose internal hostnames, internal trace IDs, debug fields, or table names. Public clients should see only fields belonging to Service A's contract.

## 17. End-to-End Testing and Error Matrix

| Scenario | Status | Expected Code | Correlation |
|---|---:|---|---|
| Valid GET product | 200 | No error code required | Header has ID |
| GET missing product | 404 | `PRODUCT_NOT_FOUND` | Header = body |
| Reserve exceeding stock | 409 | `INSUFFICIENT_STOCK` | Header = body |
| Invalid `@Valid` body | 400 | `VALIDATION_FAILED` | Header = body |
| Malformed JSON | 400 | `HTTP_400` or `MALFORMED_REQUEST` | Header = body |
| Query type mismatch | 400 | `HTTP_400` or `INPUT_TYPE_MISMATCH` | Header = body |
| Input method validation | 400 | Validation code per contract | Header = body |
| Return-value validation failure | 500 | `INTERNAL_ERROR` | Header = body if writable |
| Unexpected exception | 500 | `INTERNAL_ERROR` | No stack trace leaked |
| Spring Security blocks 401 | 401 | `AUTHENTICATION_REQUIRED` | Requires dedicated security handler |
| Spring Security blocks 403 | 403 | `ACCESS_DENIED` | Requires dedicated security handler |
| Servlet error dispatch | Per error | Shared contract if configured | Test request attribute/filter |
| Gateway rate limit | 429 | `RATE_LIMITED` | Gateway issues/preserves ID |
| Gateway timeout | 504 | `GATEWAY_TIMEOUT` per contract | Gateway issues/preserves ID |
| WebFlux functional handler error | Per error | Shared contract via reactive handler | Reactive context |
| Streaming response committed | Stream may close | New `ProblemDetail` not guaranteed | Logs/traces still needed |
| Malformed incoming `correlationId` | Per error | Independent of domain code | ID replaced or rejected per policy |

Additional checks beyond the table:

1. `status` in the body matches the actual HTTP status.
2. `Content-Type` matches `application/problem+json`.
3. `code` belongs to the catalog and stays invariant across locales.
4. `type` URI is well-formed, meaningful, and backed by stable documentation.
5. `instance` contains no PII or sensitive query parameters.
6. `errors` contains no rejected values.
7. `correlationId` is non-empty and matches between header and body.
8. Oversized incoming IDs, CR/LF, or disallowed Unicode are rejected or replaced per policy.
9. Duplicate headers or multiple ID sources follow clear precedence rules.
10. Async and error dispatches neither drop the ID nor leak MDC across requests.
11. Tracing propagation stays intact across `WebClient` and other HTTP clients.
12. API Gateways adhere to the same schema even when requests never hit the backend.
13. 5xx bodies never contain class names, SQL, tokens, or stack traces.
14. Client retries never trigger duplicate side effects; `Idempotency-Key` is used where needed.
15. OpenAPI specs, examples, and generated clients match the actual contract.

## 18. Rollout Workflow in a Real System

### Step 1: Lock Down the Contract Before Writing Filters

Choose RFC 9457 `ProblemDetail`, media type, required extensions (`code`, `correlationId`), optional extensions (`errors`), and status list. Agree on `type`/`title`/`detail`/`instance` semantics and whether localization is supported.

### Step 2: Govern the Business Code Catalog

Store codes in an enum/registry mapped to statuses and documentation. Require review for new codes; avoid collisions or changing the meaning of existing codes.

### Step 3: Issue and Store correlationId at the Trust Boundary

Prefer the ingress/gateway or an early `WebFilter`/Servlet Filter. Store the ID in request/exchange context, response headers, and logs. Never treat client-supplied headers as authentication proof.

### Step 4: Use a Single Factory to Build Errors

Extract an `ErrorResponseFactory` from the sample code to build `ProblemDetail` and populate `code`/`correlationId`/`type`/`instance` consistently. Reuse it across MVC advice, WebFlux advice, security handlers, and `/error`; avoid copy-pasting status mappings.

### Step 5: Cover Handling Points Outside MVC

Add security entry points/denied handlers, container error dispatch handling, WebFlux `ErrorWebExceptionHandler`, and gateway error mappers as dictated by your architecture. Never mark “all errors standardized” just because `@RestControllerAdvice` works for one controller.

### Step 6: Wire Logs, Metrics, and Tracing

Attach `correlationId`, `traceId`, `spanId`, and `code` appropriately. Never use `correlationId` as a per-request metric tag due to high cardinality; bounded error codes fit metrics better. Protect log access and retention.

### Step 7: Contract Tests and Fault Injection

Test business errors, invalid bodies, missing queries, security 401/403, upstream timeouts, filter exceptions, and 500s. Inspect actual body/status/headers rather than only testing Java exception classes.

### Step 8: Publish API Docs and Plan Migration

Define `ProblemDetail` + extensions in OpenAPI, publish the error catalog, and maintain backward compatibility. If legacy clients expect old JSON formats, use versioning or transitional dual-read clients rather than breaking everyone overnight without coordination.

## 19. Common Mistakes

### Mistake 1 — Treating HTTP Status as the Business Code

HTTP 404 alone does not tell whether a product, order, or user is missing. Whenever clients must behave differently, provide stable codes like `PRODUCT_NOT_FOUND` or `ORDER_NOT_FOUND`.

### Mistake 2 — Returning HTTP 200 for All Error Responses

Monitoring, gateways, and clients may treat failures as successes. Keep statuses accurate and payloads consistent.

### Mistake 3 — Using Messages as Branching Keys

A `detail` sentence can change by locale or wording edits. Clients must branch on `code`/`type`.

### Mistake 4 — Putting Stack Traces Inside detail

Risks leaking file paths, SQL, or internal data. Return safe messages to clients and keep technical details in protected logs.

### Mistake 5 — Adding correlationId to HTTP Headers Without Logging It

When a user reports an ID, support finds nothing. Put the ID in request context, MDC/tracing, and ensure thread/reactive context propagation.

### Mistake 6 — Using ThreadLocal MDC Directly in WebFlux

Reactive callbacks switch threads; MDC does not follow Publishers automatically. Use Reactor Context and an appropriate bridge.

### Mistake 7 — Trusting IDs Sent by Public Internet Clients

Clients can spoof IDs, pollute logs, or try correlating others' requests. Validate/replace at trusted ingress and never use IDs for access control.

### Mistake 8 — Using correlationId to Deduplicate POST Requests

Correlation IDs only trace requests; they provide no idempotency guarantee. Use `Idempotency-Key` and proper storage policies when operations require deduplication.

### Mistake 9 — Treating instance as a Raw Request URL with Query Params

RFC 9457 defines `instance` as an occurrence URI reference. Copying raw URLs risks leaking PII/query secrets and may not distinguish separate occurrences.

### Mistake 10 — Enabling Problem Details and Assuming /error Is Automatically Standardized

`BasicErrorController` and non-MVC error sources can still emit legacy JSON or HTML. Verify with real integration tests.

### Mistake 11 — Trying to Catch Exception in Controller Advice for the Entire System

Filters, Spring Security, gateways, and committed responses live at different layers. Handle each at its own boundary.

### Mistake 12 — Returning 400 for Return-Value Validation or Server Bugs

Server-originated errors should be classified as 5xx when appropriate. Never “blame” the request to make metrics look cleaner.

### Mistake 13 — Passing Downstream Errors Straight Through to Frontends

Risks leaking internal hostnames, exception details, or unstable internal codes. Translate them into your public contract.

### Mistake 14 — Colliding Code Names Across Teams

If multiple domains use a bare `"NOT_FOUND"`, clients lack semantic context. Maintain a governed, documented namespace/catalog.

### Mistake 15 — Forgetting CORS Header Exposure

Browser frontends may receive errors yet fail to read `X-Correlation-ID`. Configure `Access-Control-Expose-Headers` safely when needed.

### Mistake 16 — Using correlationId as a Metric Tag

A per-request ID creates huge cardinality, bloating memory and time-series storage. Metric tags should be bounded error codes, statuses, or normalized routes; `correlationId` belongs in logs and traces.

### Mistake 17 — Not Testing Error Paths During Startup or Shutdown

While a server is not ready or during graceful shutdown, error responses may come from gateways or containers without hitting advice. Ensure correlation/tracing rules exist at ingress.

### Mistake 18 — Changing Old Codes Without Versioning

Clients branching on old codes can break if meanings shift. Never repurpose a code; add a new code and plan a migration.

## 20. Self-Check Questions

**Question 1. Why include both HTTP 409 and `INSUFFICIENT_STOCK`?**  
409 informs HTTP infrastructure of a conflict; `INSUFFICIENT_STOCK` identifies the exact business failure so the client can act.

**Question 2. Are `correlationId` and `traceId` always identical?**  
No. They belong to different contracts, though an architecture may intentionally align them.

**Question 3. Should clients parse `detail` to identify errors?**  
No. `detail` is human-facing and may be translated; clients should use `code`/`type` URI.

**Question 4. Why shouldn't `instance` contain raw query strings?**  
It can leak secrets/PII and does not necessarily uniquely identify an individual occurrence.

**Question 5. Does `@RestControllerAdvice` catch a 401 returned by Spring Security before MVC?**  
Not guaranteed; configure `AuthenticationEntryPoint` or appropriate security handlers.

**Question 6. When a validation field fails, should `rejectedValue` be returned so the frontend knows what the user typed?**  
Usually no, especially for passwords/tokens. The frontend already has the input; the server only needs to return field, rule, and a safe message.

**Question 7. Why not use `correlationId` as an `Idempotency-Key`?**  
One is for tracing while the other prevents duplicate side effects. They carry no equivalent guarantees.

**Question 8. When should a validation error return HTTP 500?**  
When a constraint on a server return value fails or an internal invariant breaks, rather than bad client input.

**Question 9. In WebFlux, can you call `MDC.put` inside a `WebFilter` and immediately return `Mono` expecting all downstream logs to carry the ID?**  
No. A `Mono` executes upon subscription and may switch threads. Use Reactor Context, a bridge, or instrumentation.

**Question 10. What should a client do if it receives no `problem+json` because the connection dropped?**  
Use dedicated HTTP/network error handling, record any available correlation/trace ID, and decide retries based on operation safety and idempotency.

## 21. Summary

A consistent HTTP error in Spring Boot requires **three independent layers of information**:

- Accurate HTTP status per protocol.
- Stable business error code/type for client handling.
- Correlation ID (and trace context when available) for operator tracing.

**RFC 9457 `ProblemDetail`** preserves the five standard fields `type`/`title`/`status`/`detail`/`instance`. Spring Framework provides `ProblemDetail`, `ErrorResponse`, `ErrorResponseException`, and `ResponseEntityExceptionHandler`; application-specific fields such as `code`, `correlationId`, and `errors` are added as extensions.

In Spring MVC, `@RestControllerAdvice` paired with a correlation filter is a solid starting point, though separate configuration is needed to cover Spring Security, `/error`, the Servlet container, and gateways. In Spring WebFlux, use `WebFilter`/Reactor Context and reactive exception handling; never copy `ThreadLocal`/MVC hooks verbatim into a reactive pipeline.

A contract is truly “unified” only when **schema, status semantics, stable error codes, correlation policy, and tests cover every boundary**. Clarifying these rules keeps frontends resilient, reduces information leaks, and shortens root-cause investigations across distributed services.

## 22. Official Documentation

- IETF RFC 9457 – Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- Spring Framework – MVC REST exceptions, ProblemDetail, and ErrorResponse: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework – WebFlux REST exceptions, ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.1 Javadoc – ResponseEntityExceptionHandler: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework – MVC Controller Advice: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html
- Spring Boot – Error Handling and Problem Details: https://docs.spring.io/spring-boot/reference/web/servlet.html
- W3C Trace Context specification: https://www.w3.org/TR/trace-context/
- Micrometer Tracing: https://docs.micrometer.io/tracing/reference/
- OpenTelemetry – Context propagation: https://opentelemetry.io/docs/concepts/context-propagation/