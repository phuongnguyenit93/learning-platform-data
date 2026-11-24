# Logging Object Code, Path, and Failure Stage Without Leaking Data in Spring Framework

## 1. Goal and Diagnostic Mindset

When Spring MVC handles a failing HTTP request, a generic "400 Bad Request" or "Validation failed" is not enough for operators to know whether the failure came from **binding**, **validation**, **deserialization**, or **business rules**. However, dumping full request bodies, rejected values, and stack traces into logs for easy debugging risks leaking passwords, tokens, emails, financial records, and private user data.

A useful diagnostic log record should answer **only the questions that can be answered safely**:

- **Object code:** which data unit was being processed, e.g., `SIGNUP_FORM` or `ORDER_COMMAND`?
- **Path:** which field/property failed, e.g., `email`, `seats`, or `shippingAddress.postalCode`? When referring to HTTP paths, use a **route template** such as `POST /orders/{id}`, never raw URLs containing IDs, query parameters, and tokens.
- **Failure stage:** did the failure occur during **BIND**, **VALIDATE**, **DESERIALIZE**, **ARGUMENT**, or **POLICY**?
- **Error code:** `typeMismatch`, `NotBlank`, `Email`, `INVALID_JSON`, `POLICY_DENIED`…?
- **Outcome (status):** e.g., HTTP 400, 409, 422, or 500?
- **Correlation ID (request ID):** a server-generated or policy-verified ID linking events in the same request—**never use a session ID or access token as a request ID**.

Example of a **content-safe** log entry:

```text
event=INPUT_FAILURE route=SIGNUP_FORM object=SIGNUP_FORM field=seats stage=BIND code=typeMismatch status=400 requestId=9adac0b5-0e34-411b-ab9c-4e92e8da7f61
```

The UUID above is illustrative; each real request generates a new ID. This record is sufficient to classify the failure while **revealing none** of the rejected value, email address, JSON payload, IP, cookie, or customer identifier.

Examples of what **not** to log:

```text
ERROR /users/123456?token=very-secret password="hunter2"
Rejected value for email: private.person@example.test
Exception: JSON body {"accessToken":"secret", ...}
```

**Principle:** Log **reliable, bounded metadata sufficient for diagnosis**; never copy user or exception data into logs merely because the framework exposes `getMessage()` or `getRejectedValue()`.

## 2. Five Layers of Information in a Failure Event

| Field | What to log | What never to log directly |
| --- | --- | --- |
| `object_code` | Fixed internal code like `SIGNUP_FORM`, `BOOKING_FORM` | Entire entity or object payload |
| `field_path` | `email`, `seats`, `recipient.name` after allowlisting/sanitization | Input value, arbitrary map keys that may contain PII |
| `route` | Static route name or template like `SIGNUP_JSON` | `request.getRequestURI()` with IDs/secrets, query strings |
| `stage` | Enum BIND/VALIDATE/DESERIALIZE/ARGUMENT/POLICY | Client-supplied free text |
| `error_code` | `typeMismatch`, `NotBlank`, `INVALID_JSON`, `POLICY_DENIED` | Default messages containing input values, nested exception messages |
| `status` | 400, 403, 409, 422, 500 | Response bodies containing PII |
| `request_id` | Infrastructure-controlled UUID or trace ID | Session ID, bearer token, unvalidated client `X-Request-Id` |
| `time` | Standard timestamp added by the logger | Unverified client timestamps |
| `service` | Public component/service name and version | Secret config, sensitive environment details |
| `count` | Error count, bounded/bucketed if needed | Whole `BindingResult` or exception object |

Some field names can also be sensitive (for instance, internal fields revealing medical records, transactions, or staff names). When schema disclosure itself poses a risk, mapping field paths to fixed **error path codes** is safer.

### 2.1. "Object Code" Is Not a Database ID by Default

Distinguish:

- **Object type code**: `SIGNUP_FORM`, `ORDER_INPUT`; generally safe to log.
- **Spring object name**: `BindingResult#getObjectName()`, e.g., `signupForm`; indicates the validation target, though still best bounded by an allowlist.
- **Database primary key**: `accountId=12345`; can constitute personal data or enable identity correlation, so do not log indiscriminately by default.
- **Business identifiers**: email, phone number, order number, customer code; sensitive even when not cryptographic secrets.
- **Request/correlation ID**: identifier for one execution; links trace events rather than substituting for business identifiers.

In the lab, `object=SIGNUP_FORM` is an **object type code**, not an account ID. When an app must correlate events with real resources, consider server-issued opaque IDs, key-managed HMACs with retention/authorization policies; avoid plain hashes of low-entropy emails or phone numbers because they can be reversed by dictionary guessing.

## 3. Failure Stages: Do Not Label Everything "Validation"

An incoming request traverses multiple stages with different data sources:

```text
HTTP request
   |
   +--> Filter / security / correlation
   |
   v
DispatcherServlet
   |
   +--> Route matching + argument resolution
   |        |
   |        +--> ARGUMENT: wrong path/query parameter type
   |
   +--> Body parsing / HttpMessageConverter
   |        |
   |        +--> DESERIALIZE: malformed JSON, unreadable field
   |
   +--> WebDataBinder for @ModelAttribute
   |        |
   |        +--> BIND: type mismatch, missing required field, suppressed field
   |
   +--> Jakarta Bean Validation / Spring Validator
   |        |
   |        +--> VALIDATE: @NotBlank, @Email, @Min, custom constraint
   |
   v
Controller -> service -> domain policy
   |
   +--> POLICY: rejected by business/domain rule
   |
   +--> PERSIST: database/repository/transaction failure
   |
   v
HTTP response / error handler
```

This diagram illustrates **separation of responsibilities**, not a guarantee every request executes identically in lockstep. Spring MVC 6.1+ adds whole-method validation; exceptions vary with annotations. The Spring Security filter chain also handles exceptions outside `@ControllerAdvice`.

### 3.1. `BIND`: Property Assignment Failures

With a form submission:

```text
Content-Type: application/x-www-form-urlencoded

username=Alice&email=alice@example.test&seats=not-an-integer
```

If the DTO has `Integer seats`, `WebDataBinder` produces:

```text
object=SIGNUP_FORM field=seats stage=BIND code=typeMismatch
```

You can inspect:

```java
FieldError error = bindingResult.getFieldError("seats");
boolean failure = error != null && error.isBindingFailure();
String code = error == null ? null : error.getCode();
```

This is a fragment requiring the DTO/bindingResult. `FieldError#isBindingFailure()` separates conversion/binding errors from Validator rejections.

**Never use** `error.getRejectedValue()`, `error.toString()`, or `bindingResult.toString()` as log content. Those APIs can include raw client-submitted values.

### 3.2. `VALIDATE`: Data Parsed, Yet Constraint Failed

With `seats=0`, Spring parses the integer `0`, yet `@Min(1)` rejects it. Then:

```text
object=SIGNUP_FORM field=seats stage=VALIDATE code=Min
```

`@NotBlank` and `@Email` are other constraint codes. In Spring MVC, DTO errors from `@Valid @RequestBody` without an adjacent `BindingResult` typically throw `MethodArgumentNotValidException`.

A `@Valid` failure does not necessarily mean "malicious" data; it only means the input broke the contract. Never dump the entire object on validation failures merely because it was not saved yet.

### 3.3. `DESERIALIZE`: Unreadable Body

With incomplete JSON:

```text
{"username":"Alice",
```

Jackson/HTTP message converters throw before Bean Validation runs; MVC normally wraps it in `HttpMessageNotReadableException`. A safe log entry:

```text
route=SIGNUP_JSON object=SIGNUP_FORM field=body stage=DESERIALIZE code=INVALID_JSON status=400
```

Do not log `ex.getMostSpecificCause().getMessage()` or the full `ex.getMessage()`: depending on parser and config, messages can include JSON tokens, field values, input offsets, or internal class names.

### 3.4. `ARGUMENT`: Path/Query Conversion Failed

Example:

```text
GET /api/signups/lookup?limit=abc
```

The controller expects `Integer limit`, so `MethodArgumentTypeMismatchException` occurs and routes through `ResponseEntityExceptionHandler#handleTypeMismatch(...)`.

Safe diagnosis:

```text
route=LOOKUP object=LOOKUP_ARGUMENT field=limit stage=ARGUMENT code=TYPE_MISMATCH status=400
```

Never log the entire query string. Authorization headers or query tokens can leak unintentionally when logging raw request URLs.

### 3.5. `POLICY`: Business Rule Rejection

When the application rejects a registration based on current business state:

```text
route=SIGNUP_JSON object=SIGNUP_FORM field=object stage=POLICY code=POLICY_DENIED status=409
```

This is an example of a **fixed error code**, not an exception message interpolated with usernames or customer data. Security authorization (403) and business conflict (409) are distinct decisions; not every `POLICY` failure should return 409.

### 3.6. `PERSIST`: Database Failures

For `DataIntegrityViolationException`, never log raw SQL, bound parameters, or connection/constraint exception strings that could leak data. You can classify an internal code like `UNIQUE_CONSTRAINT` or `PERSISTENCE_FAILURE` and log SQLState/constraint identifiers **only when** those identifiers are allowlisted and permitted by security policy. Many DB failures require HTTP 500; do not force every exception down to 400.

The runnable example in Section 9 **has no database**, so `PERSIST` is extended guidance rather than an exercised branch in the sample app.

## 4. Information From `BindingResult`: What to Use and What to Avoid

`BindingResult` and `ObjectError`/`FieldError` carry both potentially safe metadata and potentially sensitive data.

| API | Value | Default safety level |
| --- | --- | --- |
| `BindingResult#getObjectName()` | Object name set by MVC/binder | Log only after mapping/allowlist |
| `FieldError#getField()` | Property path such as `email` or `addresses[0].zip` | Must filter or map, especially dynamic indexes/keys |
| `FieldError#getCode()` | General code such as `NotBlank`/`typeMismatch` | Good once mapped to a fixed set |
| `FieldError#getCodes()` | Array of i18n codes with object/field names | Do not log all of them if they leak schema |
| `FieldError#isBindingFailure()` | Boolean indicating binding origin | Useful for selecting stage |
| `FieldError#getRejectedValue()` | Rejected input value | **Never log** |
| `FieldError#getDefaultMessage()` | Message from provider/custom validator | **Never log blindly**; may contain values |
| `ObjectError#getArguments()` | Message arguments | May contain values/schema; avoid |
| `ObjectError#toString()` | Technical representation | Do not use directly in logs |
| `BindingResult#getTarget()` | Bound target object | **Never serialize/log** |
| `BindingResult#getSuppressedFields()` | List of suppressed field names | Log count or fixed code; filter names |

To determine the stage for a field:

```java
Stage stage = error.isBindingFailure()
    ? Stage.BIND
    : Stage.VALIDATE;
```

This is a Java fragment using the sample's `Stage` enum. For global `ObjectError`s (without a field), log `field=object` and an allowlisted code rather than touching a nonexistent `rejectedValue`.

### 4.1. Why Do Field Paths Also Need Filtering?

`FieldError#getField()` usually comes from server-side structures, yet property binding can support nested/indexed paths or Map keys influenced by clients:

```text
items[100000].price
settings[private-user@example.test].value
metadata[Authorization].value
```

These paths can be huge, contain identifying values, or hold line breaks if inputs/metadata permit. Never assume an entire field path is automatically safe just because it came from `FieldError`.

In the demo, only a fixed set of fields is allowed: `username`, `email`, `seats`, `body`, `limit`, `object`, `suppressed`. Any other name maps to `other` instead of being printed verbatim. In larger systems, maintain static per-DTO field/schema code lists and normalize nested paths to validated structures.

### 4.2. When You Truly Need the Concrete Object ID

Three approaches:

1. **Log no ID:** keep object type, route template, and request ID; investigate details later via access-controlled queries.
2. **Opaque public reference:** use an ID from which no PII can be derived, with scoped access and log retention limits.
3. **HMAC pseudonymization:** generate a stable tag using a secret key with rotation and access controls; avoid plain SHA-256 of emails or phone numbers because their input space is guessable.

Pseudonymized identifiers may still count as personal data under many legal frameworks; enforce retention, access control, and explicit purpose. Never log a domain ID automatically just because it is an integer.

## 5. Request ID, Trace ID, and MDC

### 5.1. Why Is Correlation Needed?

One HTTP request can emit multiple log lines across controller, validation advice, and services. With timestamps alone, correlating lines belonging to the same request under concurrency is hard. Correlation IDs link events without logging usernames or payloads.

In a simple Servlet Spring MVC app, generate a UUID in `OncePerRequestFilter` and store it temporarily in SLF4J `MDC`:

```java
String requestId = UUID.randomUUID().toString();
MDC.put("requestId", requestId);
try {
    filterChain.doFilter(request, response);
} finally {
    MDC.remove("requestId");
}
```

This is a fragment; the full class appears in Section 9. **MDC is typically ThreadLocal-backed**; in async processing, thread pools, `@Async`, `CompletableFuture`, or Reactor, context does not propagate across threads automatically. Use framework-supported context propagation/tracing and test its lifecycle. Never rely on an unmanaged `ThreadLocal` for full distributed tracing.

### 5.2. Never Blindly Trust Client `X-Request-Id`

Client-supplied headers may contain line breaks, oversized strings, query strings, or personal data. In the demo, the server **always generates a fresh UUID**, ignoring inbound headers. Systems behind a trusted gateway can verify and forward a correlation ID, provided format/length/issuer and trust boundaries are enforced.

Never use session IDs, access tokens, cookies, or emails as correlation IDs; those outlive the request and risk identity correlation.

### 5.3. Request ID Does Not Grant Authorization

Holding a valid request ID does not grant a caller permission to read logs for that ID. Returning request IDs in a response header lets users pass them to support, while support staff must still have proper authorization before querying logs. Correlation IDs must contain no user data and are not security keys.

### 5.4. Spring Boot / Micrometer Tracing

When integrating Micrometer Tracing/Actuator, Spring Boot provides `traceId`/`spanId` in the logging context and correlation pattern. When distributed tracing already exists, prefer reusing infrastructure-controlled IDs over inventing conflicting IDs. Still, never place `baggage` containing PII into MDC/logs merely because it sits in the trace context.

**The demo uses a simple request ID**, without enabling Micrometer Tracing and without claiming it is distributed tracing.

## 6. Structured Logging and Preventing Log Injection

The OWASP Logging Cheat Sheet recommends structured events, clear data provenance, sensitive-data filtering, size bounds, and log-injection prevention.

An attacker might send:

```text
x=bad\r\nWARN event=ADMIN_LOGIN_SUCCESS user=admin
```

If an app concatenates raw input into a plain-text log line, CR/LF characters can forge log entries or break parsers. For untrusted data:

- Prefer a **fixed schema**: stage enum, object code enum, route enum, allowlisted fields/codes.
- Use **parameterized logging**, never string concatenation in message templates.
- Use a **JSON structured encoder** with context-appropriate escaping, not placeholders alone.
- Bound length, character set, and cardinality; replace invalid values with a sentinel like `other`.
- Never log stack traces/exception objects by default for client-input errors.
- Avoid raw request logging in servlet filters, HTTP clients, API gateways, reverse proxies, or APM payload capture; one safe application logger does not automatically make downstream loggers safe.

Dangerous examples:

```java
log.warn("Invalid value: " + rejectedValue);
log.warn("Request failed: {}", exception.getMessage());
log.warn("Request body: {}", rawBody);
```

These lines are **illustrative anti-patterns**, without standalone variable declarations. Using `{...}` placeholders **does not scrub secrets** from variables if you pass `rejectedValue`; secrets are simply formatted differently.

Safer example:

```java
log.warn(
    "event=INPUT_FAILURE object={} field={} stage={} code={} status={}",
    ObjectCode.SIGNUP_FORM,
    SafeField.EMAIL,
    Stage.VALIDATE,
    "Email",
    400
);
```

All values here are server-controlled or mapped into bounded sets.

### 6.1. JSON Logs Alone Are Not a Complete Security Control

Spring Boot 3.5 supports structured logging formats such as ECS/Logstash/GELF. Setting `logging.structured.format.console=ecs` formats each event as single-line JSON with proper field escaping.

However, if you put `password` into a JSON attribute, the log **still contains the password**. Structured formatting mainly helps parsers and prevents log injection; **data minimization and redaction must happen beforehand**. Centralized log storage also needs its own access control, retention, encryption, and auditing.

### 6.2. Fixed Message Templates and Separate Fields

In the hands-on project, the logger uses a fixed message template:

```text
event=INPUT_FAILURE route={} object={} field={} stage={} code={} status={} requestId={}
```

Because every placeholder is an enum/allowlisted token, integer, or server-generated UUID, no raw input enters. The ECS console writer wraps the message in JSON. In larger systems, you can use SLF4J's fluent API `logger.atWarn().addKeyValue("stage", stage)...` to emit each field as a separate JSON attribute—while still filtering those exact values.

## 7. Safe Metadata Mapping Rules

### 7.1. Object Code

A Spring error has `getObjectName()="signupForm"`. The application maps:

```text
signupForm -> SIGNUP_FORM
other      -> UNKNOWN_OBJECT
```

Do not log arbitrary object names via `String.valueOf(error.getObjectName())` if they can be built from requests or uncontrolled runtime data.

### 7.2. Field Path

In a fixed DTO:

```text
username -> username
email    -> email
seats    -> seats
anything else -> other
```

To allow nested paths such as `shippingAddress.zip`, add them deliberately to the mapping. For indexed paths, consider normalizing `items[137].price` to `items[].price` instead of keeping huge indexes or PII-carrying keys; mapping should parse against schema rather than running blind regex replacements on arbitrary strings.

### 7.3. Error Code

Read `FieldError#getCode()` and map through an application-approved set. Typical Spring/Bean Validation codes include `typeMismatch`, `required`, `NotBlank`, `Email`, `Min`, `Size`, and `NotNull`. New custom codes should be added to the allowlist only after review.

Do not log the entire `getCodes()` array unnecessarily, as it can reveal model names, field paths, or internal types. Never append `rejectedValue` into `errorCode`.

### 7.4. Stage

The stage comes from **the API/layer detecting the failure**, never a client-supplied `stage` string. `FieldError#isBindingFailure()` signals `BIND`; errors from `HttpMessageNotReadableException` belong to `DESERIALIZE`; direct method argument errors belong to `ARGUMENT`; business rule exceptions belong to `POLICY`.

Do not log `VALIDATE` for malformed JSON merely because the client ultimately receives HTTP 400.

## 8. Expected Output Examples

A type-mismatched form request:

```text
POST /api/signups/form
Content-Type: application/x-www-form-urlencoded

username=Alice&email=alice@example.test&seats=SECRET_SENTINEL_42
```

Expected application log contains **metadata only**:

```text
event=INPUT_FAILURE route=SIGNUP_FORM object=SIGNUP_FORM field=seats stage=BIND code=typeMismatch status=400 requestId=<server-generated-uuid>
```

`SECRET_SENTINEL_42` must never appear. In the HTTP response, return a `ProblemDetail` with `status=400`, `title="Request rejected"`, and `code="INVALID_INPUT"`, without serializing `BindingResult` into JSON.

If a form submits a malformed email address, log field `email` and code `Email`; never log the address itself. This cleanly separates **failure location** from **failing value**.

For sensitive accounts or profiles, avoid logging raw IDs from URLs by default. Using route enum `SIGNUP_FORM` or template `POST /api/signups/form` tells operators the request kind without exposing identity.

## 9. Complete Sample Project: Java 17 + Spring Boot 3.5.6

The lab builds a small REST API featuring:

- JSON and form endpoints for the same `SignupForm`.
- `@Valid` on request DTOs to generate validation errors.
- `BindingResult` in the form handler to separate `BIND` from `VALIDATE`.
- `ResponseEntityExceptionHandler` overrides for JSON, argument, and validation errors.
- Business exception with a fixed code containing zero raw input.
- `OncePerRequestFilter` generating a server-side request ID and clearing MDC in `finally`.
- Logger emitting only allowlisted object codes, field paths, stages, error codes, routes, and statuses.
- Spring Boot ECS console JSON logging.
- MockMvc tests verifying **zero synthetic sensitive markers** appear in application logs.

This is a **local demo** with no persistence or real authentication. It is not a production API; production requires authentication/authorization, privacy review, rate limiting, audit/retention, proper tracing, and full-pipeline logging filters.

### 9.1. Directory Structure

```text
safe-validation-logs/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/safelogs/
    │   │   ├── SafeLogsApplication.java
    │   │   ├── CorrelationFilter.java
    │   │   ├── SignupForm.java
    │   │   ├── FailureEvents.java
    │   │   ├── SafeProblem.java
    │   │   ├── PolicyDeniedException.java
    │   │   ├── SignupController.java
    │   │   └── GlobalErrorAdvice.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/safelogs/SafeLogsTest.java
```

### 9.2. `pom.xml`

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
  <artifactId>safe-validation-logs</artifactId>
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
```

`spring-boot-starter-web` brings in Spring MVC and the logging starter (typically Logback) transitively. `spring-boot-starter-validation` provides the Bean Validation provider. The test starter includes MockMvc/JUnit and `OutputCaptureExtension`.

### 9.3. `application.properties`

```properties
# Listen locally only for testing.
server.address=127.0.0.1
server.port=8080

# Spring Boot 3.5: JSON logs in Elastic Common Schema.
logging.structured.format.console=ecs

# Do not enable DEBUG/TRACE for framework requests/bodies by default.
logging.level.org.springframework.web=INFO
logging.level.demo.safelogs=INFO

spring.application.name=safe-validation-logs
```

ECS formatting turns each log event into JSON instead of unstructured multi-line text. In the checks below, we mainly inspect the `message` field content and token presence/absence rather than asserting every Boot-generated ECS attribute.

### 9.4. `SafeLogsApplication.java`

```java
package demo.safelogs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeLogsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeLogsApplication.class, args);
    }
}
```

### 9.5. `CorrelationFilter.java`

```java
package demo.safelogs;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // Server-generated UUID; never trust raw X-Request-Id.
        String requestId = UUID.randomUUID().toString();

        MDC.put("requestId", requestId);
        response.setHeader("X-Request-Id", requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            // Prevent request ID bleed when servlet threads are reused.
            MDC.remove("requestId");
        }
    }
}
```

This can be extended into dedicated tracing context in async/distributed systems. This example covers synchronous servlet requests only; the filter does not propagate MDC across worker pools.

### 9.6. `SignupForm.java`

```java
package demo.safelogs;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class SignupForm {

    @NotBlank
    @Size(max = 40)
    private String username;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(1)
    private Integer seats;

    public SignupForm() {
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }
}
```

The DTO includes only required fields; no password, token, role, or internal tenant ID. For log testing, we still treat all field **values** as untrusted and never log them.

### 9.7. `FailureEvents.java` — Logging Only Allowlisted Metadata

```java
package demo.safelogs;

import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

@Component
public class FailureEvents {

    private static final Logger LOG =
        LoggerFactory.getLogger(FailureEvents.class);

    public enum Route {
        SIGNUP_JSON,
        SIGNUP_FORM,
        LOOKUP
    }

    public enum ObjectCode {
        SIGNUP_FORM,
        LOOKUP_ARGUMENT,
        UNKNOWN_OBJECT
    }

    public enum Stage {
        BIND,
        VALIDATE,
        DESERIALIZE,
        ARGUMENT,
        POLICY
    }

    private static final Set<String> SAFE_FIELDS = Set.of(
        "username", "email", "seats", "body",
        "limit", "object", "suppressed"
    );

    private static final Set<String> SAFE_CODES = Set.of(
        "typeMismatch", "required",
        "NotBlank", "Email", "NotNull", "Min", "Size",
        "INVALID_JSON", "TYPE_MISMATCH",
        "POLICY_DENIED", "SUPPRESSED_FIELDS", "OTHER"
    );

    private static String safeField(String field) {
        return SAFE_FIELDS.contains(field) ? field : "other";
    }

    private static String safeCode(String code) {
        return SAFE_CODES.contains(code) ? code : "OTHER";
    }

    private static ObjectCode objectCode(
            BindingResult errors) {

        // Never blindly log raw getObjectName().
        return "signupForm".equals(errors.getObjectName())
            ? ObjectCode.SIGNUP_FORM
            : ObjectCode.UNKNOWN_OBJECT;
    }

    public void event(
            Route route,
            ObjectCode object,
            String field,
            Stage stage,
            String code,
            int status) {

        String requestId = MDC.get("requestId");
        if (requestId == null) {
            requestId = "none";
        }

        // Every argument is an enum/allowlisted token, number, or server-generated UUID.
        LOG.warn(
            "event=INPUT_FAILURE route={} object={} field={} "
                + "stage={} code={} status={} requestId={}",
            route.name(),
            object.name(),
            safeField(field),
            stage.name(),
            safeCode(code),
            status,
            requestId
        );
    }

    public void fromBindingResult(
            Route route,
            BindingResult errors,
            int status) {

        ObjectCode object = objectCode(errors);

        for (FieldError error : errors.getFieldErrors()) {
            Stage stage = error.isBindingFailure()
                ? Stage.BIND
                : Stage.VALIDATE;

            event(
                route, object, error.getField(),
                stage, error.getCode(), status);
        }

        for (ObjectError error : errors.getGlobalErrors()) {
            event(
                route, object, "object",
                Stage.VALIDATE, error.getCode(), status);
        }
    }
}
```

Because `Set.of(...).contains(null)` on Java immutable sets throws `NullPointerException`, handle APIs that can return `null` codes carefully. In Spring, `FieldError#getCode()` can be null if a custom `ObjectError` was added without a code. **Update the two helpers in the hands-on code with a null guard before `contains`**:

```java
private static String safeField(String field) {
    return field != null && SAFE_FIELDS.contains(field)
        ? field : "other";
}

private static String safeCode(String code) {
    return code != null && SAFE_CODES.contains(code)
        ? code : "OTHER";
}
```

The two helpers above are **the exact version to use** in `FailureEvents.java`: when copying the complete file, **replace the two matching methods with these null-guarded versions**. Keep the remaining methods unchanged. Do not skip this detail, because a failing request must never trigger a secondary logging crash.

Key properties of the logger:

- `Route`, `ObjectCode`, and `Stage` are internal enums that never accept arbitrary client strings.
- `safeField` logs only **approved** property paths; unknown fields become `other`.
- `safeCode` retains only allowlisted codes; unapproved custom codes become `OTHER`.
- `fromBindingResult` uses `isBindingFailure()` to distinguish `BIND` from `VALIDATE`.
- Never touches `getRejectedValue()`, `getDefaultMessage()`, `getTarget()`, or raw request bodies.
- Never passes an exception as the logger's final argument, avoiding accidental stack traces on input failures.

### 9.8. `SafeProblem.java` — Safe Response

```java
package demo.safelogs;

import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;

public final class SafeProblem {

    private SafeProblem() {
    }

    public static ProblemDetail of(
            HttpStatusCode status, String publicCode) {

        ProblemDetail problem =
            ProblemDetail.forStatus(status);

        problem.setTitle("Request rejected");
        problem.setDetail(
            "The request could not be processed");
        problem.setProperty("code", publicCode);

        return problem;
    }
}
```

`publicCode` is passed by the caller **from server constants**. Never embed detailed error messages, stack traces, or rejected values into `ProblemDetail`. When Spring MVC serializes `ProblemDetail` via Jackson, standard fields include `type/title/status/detail/instance` plus the `code` extension property, with media type `application/problem+json`.

### 9.9. `PolicyDeniedException.java`

```java
package demo.safelogs;

public class PolicyDeniedException extends RuntimeException {

    private final FailureEvents.Route route;

    public PolicyDeniedException(FailureEvents.Route route) {
        super("Operation rejected by policy");
        this.route = route;
    }

    public FailureEvents.Route route() {
        return route;
    }
}
```

This exception carries only a safe route enum. It never builds messages from client usernames/emails/IDs. This simulates a business conflict and **does not replace an application's real authorization layer**.

### 9.10. `SignupController.java`

```java
package demo.safelogs;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/signups")
public class SignupController {

    private final FailureEvents events;

    public SignupController(FailureEvents events) {
        this.events = events;
    }

    @InitBinder("signupForm")
    void restrictForm(WebDataBinder binder) {
        binder.setAllowedFields("username", "email", "seats");
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> json(
            @Valid @RequestBody SignupForm form) {

        checkPolicy(form, FailureEvents.Route.SIGNUP_JSON);
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("state", "accepted"));
    }

    @PostMapping(
        path = "/form",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> form(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            events.event(
                FailureEvents.Route.SIGNUP_FORM,
                FailureEvents.ObjectCode.SIGNUP_FORM,
                "suppressed",
                FailureEvents.Stage.BIND,
                "SUPPRESSED_FIELDS",
                400
            );
            return ResponseEntity.badRequest()
                .body(SafeProblem.of(
                    HttpStatus.BAD_REQUEST, "INVALID_INPUT"));
        }

        if (errors.hasErrors()) {
            events.fromBindingResult(
                FailureEvents.Route.SIGNUP_FORM, errors, 400);

            return ResponseEntity.badRequest()
                .body(SafeProblem.of(
                    HttpStatus.BAD_REQUEST, "INVALID_INPUT"));
        }

        checkPolicy(form, FailureEvents.Route.SIGNUP_FORM);
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("state", "accepted"));
    }

    @GetMapping("/lookup")
    public Map<String, String> lookup(
            @RequestParam("limit") Integer limit) {
        return Map.of("state", "checked");
    }

    private static void checkPolicy(
            SignupForm form,
            FailureEvents.Route route) {

        if ("blocked".equalsIgnoreCase(form.getUsername())) {
            throw new PolicyDeniedException(route);
        }
    }
}
```

Key takeaways:

- JSON goes through Jackson deserialization and `@Valid`, not `@ModelAttribute`'s property allowlist.
- The form binds via `@ModelAttribute("signupForm")` and receives `BindingResult` **immediately after** the argument to classify binding/validation errors locally.
- On suppressed fields, the handler rejects and logs **a fixed code**, never logging disallowed field names or values.
- On validation failures, it logs metadata and returns a generic `ProblemDetail`.
- When data is valid yet simulated policy rejects it, it throws a dedicated exception without logging the username.
- The lookup endpoint merely demonstrates query conversion errors like `limit=abc`. The `limit` value is never echoed or logged raw.
- `@Valid` is not authorization; the project omits Spring Security solely for local logging study.

### 9.11. `GlobalErrorAdvice.java`

```java
package demo.safelogs;

import org.springframework.beans.TypeMismatchException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.method.MethodValidationException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class GlobalErrorAdvice extends ResponseEntityExceptionHandler {

    private final FailureEvents events;

    public GlobalErrorAdvice(FailureEvents events) {
        this.events = events;
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        events.fromBindingResult(
            FailureEvents.Route.SIGNUP_JSON,
            ex.getBindingResult(),
            status.value());

        return handleExceptionInternal(
            ex,
            SafeProblem.of(status, "INVALID_INPUT"),
            headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        events.event(
            FailureEvents.Route.SIGNUP_JSON,
            FailureEvents.ObjectCode.SIGNUP_FORM,
            "body",
            FailureEvents.Stage.DESERIALIZE,
            "INVALID_JSON",
            status.value()
        );

        return handleExceptionInternal(
            ex,
            SafeProblem.of(status, "INVALID_INPUT"),
            headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        events.event(
            FailureEvents.Route.LOOKUP,
            FailureEvents.ObjectCode.LOOKUP_ARGUMENT,
            "limit",
            FailureEvents.Stage.ARGUMENT,
            "TYPE_MISMATCH",
            status.value()
        );

        return handleExceptionInternal(
            ex,
            SafeProblem.of(status, "INVALID_INPUT"),
            headers, status, request);
    }

    @ExceptionHandler(PolicyDeniedException.class)
    public ResponseEntity<ProblemDetail> handlePolicy(
            PolicyDeniedException ex) {

        events.event(
            ex.route(),
            FailureEvents.ObjectCode.SIGNUP_FORM,
            "object",
            FailureEvents.Stage.POLICY,
            "POLICY_DENIED",
            409
        );

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(SafeProblem.of(
                HttpStatus.CONFLICT, "POLICY_DENIED"));
    }
}
```

**Import check:** `org.springframework.validation.method.MethodValidationException` is unused in this file and can be removed. This is a complete example of the hooks **actually used** in the demo controller without whole-method validation. Remove unused imports in your IDE to keep code clean.

**Do not add `@ExceptionHandler(MethodArgumentNotValidException.class)` to a subclass** of `ResponseEntityExceptionHandler`: the base class already registers framework mappings. Override `handleMethodArgumentNotValid(...)` and `handleHttpMessageNotReadable(...)` with Spring 6.2's `HttpStatusCode` signature. Business exception `PolicyDeniedException` is not in the base class, so it uses its own `@ExceptionHandler`.

In real applications, global advice methods handle multiple routes rather than just the lab's two routes. **Never hardcode `Route.SIGNUP_JSON` for every HTTP exception in a multi-endpoint application.** Map server-side handler/route metadata (such as Spring-resolved request mapping patterns with an allowlist) or use controller-scoped advice. The demo hardcodes it solely because all JSON POSTs and lookups belong to a fixed-scope lab API.

### 9.12. Running the Application

Requires JDK 17+ and Maven 3.x. In the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

The app listens on `http://127.0.0.1:8080` per lab config. In another terminal, try each case.

**A. Valid JSON:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups' \
  -H 'Content-Type: application/json' \
  -d '{"username":"Alice","email":"alice@example.test","seats":2}'
```

HTTP **201 Created**, response body:

```json
{"state":"accepted"}
```

No `event=INPUT_FAILURE` is emitted for this request. The `X-Request-Id` header contains a server-generated UUID; no user input needs to enter logs to obtain a request ID.

**B. Form Type Mismatch:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=Alice' \
  --data-urlencode 'email=alice@example.test' \
  --data-urlencode 'seats=PRIVATE_SENTINEL_42'
```

HTTP **400 Bad Request**, application log contains the tokens:

```text
event=INPUT_FAILURE
route=SIGNUP_FORM
object=SIGNUP_FORM
field=seats
stage=BIND
code=typeMismatch
status=400
requestId=<UUID generated by server>
```

The snippet above lists **tokens to observe in the message**, not a full ECS JSON log line. `PRIVATE_SENTINEL_42` never appears in the event message emitted by `FailureEvents`. Fields such as `timestamp`, `logger`, and `level` are added separately by Boot.

**C. Form Validation Error:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=Alice' \
  --data-urlencode 'email=PRIVATE_SENTINEL_NOT_EMAIL' \
  --data-urlencode 'seats=2'
```

HTTP **400 Bad Request**, emitting event:

```text
route=SIGNUP_FORM object=SIGNUP_FORM field=email stage=VALIDATE code=Email status=400
```

Neither the email address nor the sentinel appears in the log message.

**D. Unreadable JSON Body:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups' \
  -H 'Content-Type: application/json' \
  -d '{"username":"PRIVATE_SENTINEL"'
```

HTTP **400 Bad Request**, logger records:

```text
route=SIGNUP_JSON object=SIGNUP_FORM field=body stage=DESERIALIZE code=INVALID_JSON status=400
```

Neither raw JSON, parser tokens, nor exception chains are logged.

**E. Query Argument Type Mismatch:**

```bash
curl -i 'http://127.0.0.1:8080/api/signups/lookup?limit=PRIVATE_SENTINEL'
```

HTTP **400 Bad Request**, logger records:

```text
route=LOOKUP object=LOOKUP_ARGUMENT field=limit stage=ARGUMENT code=TYPE_MISMATCH status=400
```

**F. Business Policy Rejection:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups' \
  -H 'Content-Type: application/json' \
  -d '{"username":"blocked","email":"a@example.test","seats":1}'
```

HTTP **409 Conflict**, logger records:

```text
route=SIGNUP_JSON object=SIGNUP_FORM field=object stage=POLICY code=POLICY_DENIED status=409
```

The response includes extension `code="POLICY_DENIED"` without leaking the username.

**G. Disallowed Extra Field in Form:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=Alice' \
  --data-urlencode 'email=alice@example.test' \
  --data-urlencode 'seats=2' \
  --data-urlencode 'internalToken=PRIVATE_SENTINEL'
```

HTTP **400 Bad Request** and event:

```text
route=SIGNUP_FORM object=SIGNUP_FORM field=suppressed stage=BIND code=SUPPRESSED_FIELDS status=400
```

Neither `internalToken` nor `PRIVATE_SENTINEL` enters the event. Note that `getSuppressedFields()` **does not automatically become a `FieldError`**; the controller checks it explicitly and logs a dedicated code.

## 10. Testing Safe Logs with MockMvc

Checking HTTP status alone is not enough. This lesson verifies **logs actually omit input markers**. With Spring Boot Test, `OutputCaptureExtension` captures stdout/stderr during test execution. Because logging is configured as ECS JSON, tests assert key tokens rather than byte-for-byte JSON output.

### 10.1. `SafeLogsTest.java`

```java
package demo.safelogs;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class SafeLogsTest {

    @Autowired
    MockMvc mvc;

    @Test
    void wrongFormTypeLogsFieldAndStageButNotValue(
            CapturedOutput output) throws Exception {

        final String marker = "PRIVATE_SENTINEL_42";

        mvc.perform(post("/api/signups/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "Alice")
                .param("email", "alice@example.test")
                .param("seats", marker))
            .andExpect(status().isBadRequest())
            .andExpect(header().exists("X-Request-Id"))
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

        String logs = output.getAll();
        assertTrue(logs.contains("route=SIGNUP_FORM"));
        assertTrue(logs.contains("field=seats"));
        assertTrue(logs.contains("stage=BIND"));
        assertTrue(logs.contains("code=typeMismatch"));
        assertFalse(logs.contains(marker));
    }

    @Test
    void invalidEmailLogsValidationCodeWithoutValue(
            CapturedOutput output) throws Exception {

        final String marker = "PRIVATE_SENTINEL_NOT_EMAIL";

        mvc.perform(post("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"Alice\","
                    + "\"email\":\"" + marker + "\","
                    + "\"seats\":2}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

        String logs = output.getAll();
        assertTrue(logs.contains("route=SIGNUP_JSON"));
        assertTrue(logs.contains("field=email"));
        assertTrue(logs.contains("stage=VALIDATE"));
        assertTrue(logs.contains("code=Email"));
        assertFalse(logs.contains(marker));
    }

    @Test
    void malformedJsonLogsStageNotPayload(
            CapturedOutput output) throws Exception {

        final String marker = "PRIVATE_SENTINEL_JSON";

        mvc.perform(post("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"" + marker + "\""))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

        String logs = output.getAll();
        assertTrue(logs.contains("stage=DESERIALIZE"));
        assertTrue(logs.contains("code=INVALID_JSON"));
        assertFalse(logs.contains(marker));
    }

    @Test
    void queryTypeMismatchLogsArgumentStage(
            CapturedOutput output) throws Exception {

        final String marker = "PRIVATE_SENTINEL_QUERY";

        mvc.perform(get("/api/signups/lookup")
                .param("limit", marker))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

        String logs = output.getAll();
        assertTrue(logs.contains("route=LOOKUP"));
        assertTrue(logs.contains("field=limit"));
        assertTrue(logs.contains("stage=ARGUMENT"));
        assertFalse(logs.contains(marker));
    }

    @Test
    void policyFailureLogsOnlyBusinessCode(
            CapturedOutput output) throws Exception {

        mvc.perform(post("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"blocked\","
                    + "\"email\":\"a@example.test\","
                    + "\"seats\":1}"))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("POLICY_DENIED"));

        String logs = output.getAll();
        assertTrue(logs.contains("stage=POLICY"));
        assertTrue(logs.contains("code=POLICY_DENIED"));
        assertFalse(logs.contains("a@example.test"));
    }

    @Test
    void suppressedFormFieldDoesNotLeakItsNameOrValue(
            CapturedOutput output) throws Exception {

        final String marker = "PRIVATE_SENTINEL_EXTRA";

        mvc.perform(post("/api/signups/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "Alice")
                .param("email", "alice@example.test")
                .param("seats", "2")
                .param("internalToken", marker))
            .andExpect(status().isBadRequest());

        String logs = output.getAll();
        assertTrue(logs.contains("field=suppressed"));
        assertTrue(logs.contains("code=SUPPRESSED_FIELDS"));
        assertFalse(logs.contains(marker));
        assertFalse(logs.contains("internalToken"));
    }

    @Test
    void validRequestGetsServerGeneratedCorrelationId()
            throws Exception {

        mvc.perform(post("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"Alice\","
                    + "\"email\":\"alice@example.test\","
                    + "\"seats\":2}"))
            .andExpect(status().isCreated())
            .andExpect(header().exists("X-Request-Id"))
            .andExpect(jsonPath("$.state").value("accepted"));
    }
}
```

The test suite has **7 methods**: binding error, validation error, JSON parse error, query type mismatch, business rejection, suppressed field, and request ID.

**Note on `OutputCaptureExtension`:** it captures console output across loggers. `assertFalse(output.getAll().contains(marker))` is a solid smoke check for the lab, whereas larger projects should target specific loggers/application events or use a scoped Logback `ListAppender`/in-memory appender to avoid interference from framework bootstrap or other tests. Run sequentially/isolated when needed because console capture and loggers share state; never mistake a passing unit test for proof that upstream log collectors, proxies, APM, and reverse proxies do not capture inputs.

### 10.2. Running Tests

```bash
mvn -q test
```

Success is indicated by **exit code 0**, not a fixed Maven stdout line (because `-q` is passed). Surefire report details are in `target/surefire-reports/`.

These assertions are designed to inspect metadata and marker absence; runtime compilation/tests **were not executed in this article**, so run them in an environment with matching JDK/Maven versions and update if framework/logging pipelines differ.

### 10.3. Adding CRLF Log Injection Tests

In a real system, add tests attempting to inject:

```text
Alice\r\nFAKE_EVENT=ADMIN_GRANTED
```

into `username`, dynamic field names, headers, or request IDs. Expect **no forged log event** emitted by the application. In the demo, none of those values are passed to `FailureEvents`; the JSON encoder further protects log formatting.

Never assume `{}` placeholders alone prevent all log injection—if a raw string containing CRLF is passed to a placeholder in plain-text logs, the risk still remains.

## 11. Relation to Other Validation Paths in Spring MVC 6.2

### 11.1. `MethodArgumentNotValidException`

With `@Valid @RequestBody SignupForm` and no immediately following `BindingResult`, argument-level Bean Validation failures are normally raised by Spring MVC as `MethodArgumentNotValidException`. The exception carries `BindingResult` so you can inspect field errors by object name and path.

Never dump the raw exception inside a handler:

```java
// Not recommended if logging prints rejected values automatically.
LOG.warn("Invalid payload: {}", ex.getBindingResult());
```

Instead, call `events.fromBindingResult(...)` using allowlisted field/code lists.

### 11.2. `HandlerMethodValidationException`

Spring MVC 6.1+ supports direct method constraints, such as `@Min(1)` on `@RequestParam int page`. When whole-method validation runs, the exception may be `HandlerMethodValidationException` carrying `ParameterValidationResult`s instead of a single `BindingResult`.

To log safely:

- Use server-defined, allowlisted **route codes** and parameter names.
- Iterate `ParameterValidationResult` or `visitResults(...)` to identify which parameter failed.
- Never log `getArgument()` or `ConstraintViolation#getInvalidValue()`.
- Derive constraint codes from mapped `ConstraintDescriptor`/error codes; never use localized messages as codes.
- Return-value validation failures carry HTTP **500** rather than 400; preserve the actual status.

The lab deliberately avoids direct constraints on method parameters; the lookup endpoint uses **type conversion** to isolate the `ARGUMENT` stage.

### 11.3. `@ModelAttribute` + `BindingResult`

For forms:

```java
public ResponseEntity<?> form(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult errors) {
    // ...
}
```

`BindingResult` sits immediately after the form argument, letting the controller inspect errors locally instead of throwing. If `errors.hasErrors()` is true yet code still calls `save`, even the best logger cannot prevent side effects. Logging is for observability, **never a substitute for validation, authorization, or transactions**.

### 11.4. JSON `@RequestBody` Differs from Form Binding

A JSON body may be rejected by Jackson before Bean Validation; `HttpMessageNotReadableException` lacks a clean list of `FieldError`s to "guess which field failed." In that case, log `field=body` and `code=INVALID_JSON` instead of scraping parser exception text.

A type-mismatched JSON property may carry a nested Jackson path; while paths help, never log arbitrary map keys or array indexes unfiltered.

### 11.5. Spring Security Errors

Authentication/authorization exceptions in the Spring Security filter chain are handled by `AuthenticationEntryPoint` or `AccessDeniedHandler`, not this MVC advice. If a unified event schema is needed, add a policy-aware logging adapter at the Security boundary; never log credentials or access tokens.

### 11.6. Exceptions Handled at Another Layer

If `@ControllerAdvice` does not execute, do not immediately assume "the logger is broken." Requests can be rejected before MVC by a proxy, CORS/filter/security, or the servlet container. Place logging hooks at the appropriate boundary without double-counting the same event.

## 12. When to Log Codes vs. When to Log Messages?

For validation, **stable codes** beat messages:

| Source | Machine code | User-facing message | What to log |
| --- | --- | --- | --- |
| `@NotBlank` | `NotBlank` | "Must not be blank" | Code + field, no value |
| `@Min(1)` | `Min` | "Must be at least 1" | Code + field, no value |
| Type binding failure | `typeMismatch` | "Invalid value type" | Code + stage `BIND` |
| Malformed JSON | `INVALID_JSON` | "Invalid request body" | Generic code + stage `DESERIALIZE` |
| Domain rule | `POLICY_DENIED` | "Request cannot be completed" | Application-controlled code |
| Internal error | `INTERNAL_ERROR` | "An error occurred" | Code + request ID; details only in controlled channels |

Custom constraint messages may interpolate `{validatedValue}` or raw input data. Therefore, **never** log `ConstraintViolation#getMessage()` by default. For investigation, rely on annotation type, mapped property path, and error code.

Error-code logs also need schema versioning: a team renaming a constraint or model field can break dashboards. If log contracts feed operations, maintain versioned mappings and tests just like HTTP APIs.

## 13. Log Levels and Prioritization

Not every client error is an emergency:

- **INFO:** normal, low-risk events useful for business monitoring.
- **WARN:** unexpected input, rejected requests, signs of abuse, or diagnosable mismatches; rate-control volume.
- **ERROR:** unexpected server/persistence failures requiring alerts; never dump raw sensitive data.
- **DEBUG/TRACE:** enable only briefly with approval for targeted scopes; never log bodies, headers, and rejected values by default.

In the demo, `FailureEvents` logs at `WARN` so controlled failure cases are easy to observe. Production must prevent noise—e.g., a bot flooding millions of invalid requests could cause log flooding and huge bills. Use sampling, rate limits, counters, and targeted alerting for dangerous patterns, **without turning off critical security events**.

`typeMismatch` on a public API may occur frequently and is not a 500. Choose log levels based on operational goals rather than HTTP status alone.

## 14. Privacy and Security Across the Entire Log Pipeline

Even if your app omits input, downstream log collectors may still capture data. During security reviews, audit the entire path:

```text
Client
  -> CDN / WAF / API Gateway / Reverse proxy
  -> Application / Spring MVC
  -> SLF4J / Logback
  -> stdout / log file
  -> agent / collector / SIEM / APM
  -> dashboards / alerts / tickets / exports
  -> backups / retention / deletion
```

Controls to enforce:

1. Never enable unconditional HTTP request/response body logging.
2. Never put `Authorization`/`Cookie`/`Set-Cookie` headers into MDC or event metadata.
3. Avoid raw query strings/path parameters in route fields.
4. Enforce least-privilege access and access auditing on log readers.
5. Encrypt log transport; keep unnecessary sensitive data out of collectors.
6. Bound retention per legal and operational needs; apply to rotations, backups, and exports too.
7. Maintain procedures to delete/redact log data when policy requires, accounting for SIEM immutability/retention.
8. Ensure dashboards and alert payloads never leak values; never attach raw untrusted event objects.
9. Test log injection with CRLF/JSON special characters and dynamic field paths.
10. Audit third-party/framework loggers left at DEBUG/TRACE after incidents; revert to safe defaults.
11. Never log DB credentials, SQL parameter bindings, JWTs, refresh tokens, or session IDs.
12. Use HMAC/opaque IDs when user/resource correlation is mandatory, with rotation and access restrictions.

**Privacy by design is not just regex-masking passwords with asterisks.** Post-hoc redaction misses secret aliases, encoded forms, and nested objects. Preventing **sensitive data from entering logs at the source** is far more effective.

## 15. Common Pitfalls When Applying This

| Symptom | Cause | Fix |
| --- | --- | --- |
| Password appears in logs after validation failure | Printing `getRejectedValue()` or raw `BindingResult` | Log only mapped object/field/code |
| Raw JSON leaked in logs | Printing `HttpMessageNotReadableException#getMessage()` | Log `DESERIALIZE/INVALID_JSON` without exception details |
| Stage is always `VALIDATE` | Ignoring `FieldError#isBindingFailure()` | Separate `BIND` and `VALIDATE` |
| Cannot tell which request caused an error | Missing correlation ID | Server-controlled UUID/traceId, clear MDC |
| Forged multi-line log entries | Raw CRLF in input/tokens | Structured JSON, allowlists, length bounds |
| Request IDs repeat or bleed across requests | Forgot `MDC.remove()` in thread pool | Clean context in `finally` |
| `@Async` logs lack `requestId` | ThreadLocal MDC does not propagate | Use framework context propagation/tracing |
| Object name accidentally contains PII | Logging raw model object name | Map to fixed object-type codes |
| Field path contains email or map key | Logging unfiltered `getField()` | Map paths by schema or `other` token |
| App logs are safe yet proxy leaks URLs | Proxy access logs record raw query | Audit the full pipeline |
| Tests assert only HTTP 400 | Never checked events or log leaks | Assert stage/code and marker absence |
| Logs accidentally contain exception stack traces | Passing `ex` as final logger argument | Log metadata only; separate controlled diagnostics |
| Unstable enum/error codes in logs | Mixing class names with public codes | Define an explicit log schema |
| Suppressed form fields go unlogged | `hasErrors()` can still be false | Check `getSuppressedFields()` separately |
| Every failure returns 500 | Catch-all generic exception handler | Separate input vs. server errors; preserve statuses |
| Log volume overwhelms storage | `WARN` on every invalid public API request | Tune levels, sampling, and monitoring |
| JSON logging enabled yet tokens still leak | Passing raw input into JSON fields | Minimize data before serialization |
| Logging bug breaks failing requests further | Helper crashes on null or unexpected data | Null guards, allowlists, resilient logger |

## 16. Practical Deployment Checklist

1. Each event uses a **stable event name** (e.g., `INPUT_FAILURE`).
2. Route is logged as a **server-controlled route name/template**, never raw request URI.
3. Object code is an object-type code, never automatically a database ID.
4. Field paths are allowlisted; nested paths/map keys/indexes follow explicit canonicalization rules.
5. Stage uses only a fixed enum: `BIND`/`VALIDATE`/`DESERIALIZE`/`ARGUMENT`/`POLICY`.
6. Error codes use an approved allowlist with fallback `OTHER`.
7. Never log `rejectedValue`, interpolated validation messages, raw bodies, HTTP authorization headers, session IDs, cookies, or SQL parameters.
8. Correlation IDs have strict format/ownership, generated by the server or a trusted gateway.
9. MDC is cleared in `finally`, with a propagation strategy for async/thread hopping.
10. HTTP statuses and error bodies are consistent and **contain zero sensitive data**.
11. For form binding, check both `hasErrors()` and `getSuppressedFields()`.
12. For JSON, distinguish parsing failures from Bean Validation failures.
13. On Spring MVC 6.1+, account for `HandlerMethodValidationException`.
14. For Spring Security, emit events at the proper filter/security boundary.
15. Use structured logging/JSON encoders and test CRLF/log injection.
16. Keep tests asserting both marker absence in logs and exact stage/field/code metadata.
17. Verify reverse proxies, gateways, APM, and log agents do not capture bodies/headers.
18. Enforce proper retention, access control, and auditing on log stores.
19. Plan log-schema versioning without breaking operational dashboards.
20. Enable higher verbosity only temporarily under change control—never leave DEBUG/TRACE running in production.

## 17. Summary

To diagnose Spring MVC failures while protecting privacy, log **object type code**, **approved field path**, **failure stage**, **stable error code**, **HTTP status**, **route template**, and a **system-controlled request ID**. That metadata answers "where and why it failed" without printing customer data.

In Spring, `BindingResult` provides `getObjectName()`, `FieldError#getField()`, `getCode()`, and `isBindingFailure()`; meanwhile `getRejectedValue()`, `getDefaultMessage()`, `getTarget()`, and exception messages can carry sensitive data. Combine allowlists, enums, structured logging, and a correlation filter with a strict lifecycle. Test binding, validation, JSON parsing, argument conversion, and business rejections, and assert that input markers never appear in **application log messages**.

**Log enough to operate, never more than necessary.** A good log event is structured, traceable, access-controlled, and never turns a user error into a data leak.

## References

- OWASP Logging Cheat Sheet — event attributes, data to exclude, log injection: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Sensitive Data Exposure / Security Logging principles: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude
- Spring Framework 6.2 — MVC validation, MethodArgumentNotValidException and HandlerMethodValidationException: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — MVC error responses / RFC 9457: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — `ResponseEntityExceptionHandler` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.2 — `BindingResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework 6.2 — `FieldError` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/FieldError.html
- Spring Boot 3.5 — Logging (structured ECS, SLF4J and Logback): https://docs.spring.io/spring-boot/3.5/reference/features/logging.html
- Spring Boot 3.5 — Tracing and correlation IDs: https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html
- SLF4J manual — parameterized logging and MDC: https://www.slf4j.org/manual.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457