# Stripping Sensitive `rejectedValue` and Internal Details Before Returning Errors in Spring

## 1. Goal: helpful error responses without leaking data

When Spring MVC or Spring WebFlux validates a request, the framework may retain client-submitted values to help developers diagnose issues. For example, `FieldError#getRejectedValue()` holds the value that failed binding or validation; `ConstraintViolation#getInvalidValue()` holds the violating value; exceptions from Jackson, type conversion, or custom validators can include input, class names, or configuration details in their messages.

That data is **not inherently safe to return to the client**.

Suppose a request is:

~~~json
{
  "email": "not-an-email_PRIVATE",
  "password": "SECRET-password-123!",
  "apiToken": "TOKEN-secret-456!",
  "contacts": [
    {"name": "", "priority": 0}
  ]
}
~~~

An unsafe handler:

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
public Object unsafe(MethodArgumentNotValidException ex) {
    return ex.getBindingResult().getAllErrors();
}
~~~

This snippet only **illustrates a dangerous pattern**, not part of a runnable project. When Jackson serializes framework objects, the response can expose `rejectedValue`, class names, or metadata outside the API contract. Another anti-pattern:

~~~java
return Map.of("error", ex.getMessage());
~~~

`ex.getMessage()` is meant for diagnostics, **not as a public contract**; it can include field paths, rejected values, Java method signatures, or raw parser diagnostics.

Instead, return an intentionally defined response:

~~~json
{
  "type": "urn:problem:invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "Review the indicated fields.",
  "code": "INVALID_REQUEST",
  "issues": [
    {
      "code": "INVALID_EMAIL",
      "path": "email",
      "location": "body",
      "message": "Enter a valid email address"
    },
    {
      "code": "INVALID_FORMAT",
      "path": "password",
      "location": "body",
      "message": "Value has an invalid format"
    }
  ]
}
~~~

This is an abbreviated example: a request might also have errors on `apiToken` and `contacts`, yet nowhere is there room for secret inputs or full exception details. The fields `code`, `issues`, `path`, and `location` are **application-designed extensions** on Spring 6.x / RFC 9457 `ProblemDetail`.

**Core principles:**
- Keep **error codes, sanitized field paths, input locations, and safe messages** so clients can fix errors.
- Strip **rejected/invalid values, stack traces, causes, Java class/method signatures, SQL, filesystem paths, and provider internals** before serialization.
- **Never assume `getDefaultMessage()` is always safe**: a custom validator can concatenate input into its message.
- HTTP 400 is for invalid input; validation failures on **return values** are server issues and should normally remain HTTP 500 with minimal public details.
- Apply the same rules across HTTP bodies, headers, logs, traces, monitoring, WebSocket/RSocket error frames, and any other error reporting channels.

This lesson uses **Java 17, Spring Boot 3.5.7, Spring Framework 6.2, Jakarta Validation**. A complete project and JUnit/`MockMvc` tests are included to verify secrets never leak into responses.

## 2. Why is `rejectedValue` sensitive data?

### 2.1. `FieldError#getRejectedValue()`

With a form field:

~~~text
password=SECRET-password-123!
~~~

If the Java DTO has a `@Pattern` constraint, Spring can construct a `FieldError` containing:
- `objectName`: the model object name.
- `field`: the property name, e.g., `password`.
- `rejectedValue`: the exact rejected string.
- `codes`: list of Spring error codes.
- `arguments`: arguments used for message resolution.
- `defaultMessage`: error message.
- `bindingFailure`: whether it came from conversion/binding vs. validation.

Developers may want these details in a debugger, yet **`FieldError` is not a public DTO**. Never return `FieldError`, `BindingResult`, or `MethodArgumentNotValidException` directly from an API and let Jackson decide which properties get serialized.

### 2.2. `ConstraintViolation#getInvalidValue()`

With Jakarta Bean Validation:

~~~java
Set<ConstraintViolation<RegistrationInput>> violations =
        validator.validate(input);
~~~

Each `ConstraintViolation` carries `getPropertyPath()`, `getMessage()`, `getMessageTemplate()`, `getConstraintDescriptor()`, and `getInvalidValue()`. Never serialize raw `ConstraintViolation` objects. Specifically:
- `getInvalidValue()` can be a password, access token, OTP code, email, document number, or nested object.
- `getConstraintDescriptor().getAttributes()` can contain regexes, groups, payloads, and internal configuration.
- `getRootBean()` / `getLeafBean()` can reference objects containing data never meant for the client.

When mapping codes from a Jakarta constraint, look up the annotation type against an **allowlist** and translate it to a public code. When exposing bounds like minimum/maximum, extract **only the approved safe attributes**, never the entire descriptor.

### 2.3. Exception messages, causes, and parser details

An `HttpMessageNotReadableException` can wrap a Jackson exception. Its message/cause chain can reveal:
- JSON tokens read, input near the failure, or property names.
- Java target types, packages, and classes.
- Line/column positions and serializer internals.
- Object paths or constructor signatures.
- Converter/provider configuration.

`MethodArgumentTypeMismatchException#getValue()` can hold an invalid query parameter. `MissingServletRequestParameterException#getMessage()` is diagnostic text, not wording meant for a public API.

**Never build responses from `exception.getMessage()`, `getMostSpecificCause()`, `getRootCause()`, `getStackTrace()`, or `printStackTrace()`.** Those details can be written to protected internal observability systems when truly necessary, subject to sensitive-data handling policies.

### 2.4. Raw content inside custom validation messages

A custom validator sometimes builds a message like:

~~~java
context.buildConstraintViolationWithTemplate(
        "Invalid token: " + tokenFromRequest);
~~~

This is an **anti-pattern**: even if you never read `rejectedValue`, `FieldError#getDefaultMessage()` will now contain the token itself. Thus, **merely omitting the `rejectedValue` field from JSON is not enough**.

A stronger safeguard: public messages come from a **trusted catalog** selected by an allowlisted code, rather than taking arbitrary default messages from exceptions/providers. If the product needs custom validation messages, maintain a reviewed list of message codes and never concatenate raw input.

## 3. Data classification: keep, evaluate, or strip

| Data | Public API policy | Reason |
| --- | --- | --- |
| Business code `INVALID_EMAIL`, `REQUIRED` | Keep | Stable, actionable by clients |
| Appropriate HTTP status 400/422/500 | Keep | Accurate HTTP semantics |
| Field path `contacts[0].priority` | Keep **if allowlisted/canonicalized** | UI needs to highlight the item |
| Source `body`/`form`/`query` | Keep | Avoids ambiguity across sources |
| Server-selected message from catalog | Keep | Useful and localizable |
| Public threshold `min=1` | Keep only if reviewed | Can help UX, not always needed |
| Map key embedded in path | Evaluate/mask | Map keys may be emails/tokens |
| `rejectedValue` / `invalidValue` | **Never return** | May contain secrets/PII |
| Raw `ObjectError#getArguments()` | **Never return** | May carry internal metadata/values |
| Full `ConstraintViolation` / `BindingResult` | **Never return** | Not public DTOs |
| Regexes, internal validation groups, payloads | **Never return** by default | May expose internal rules |
| Exception class/method/stack trace | **Never return** | Aids attackers, useless to end users |
| Raw SQL, hostnames, file paths, connection strings | **Never return** | Exposes system configuration |
| Access tokens, cookies, `Authorization` headers | **Never return, never log raw** | Authentication secrets |
| Server-generated correlation/trace ID | May keep | Aids support without leaking secrets |
| Error timestamp | Contract-dependent | Low risk, though does not fix the error |
| Entire request body | **Never echo back** | Client already has input; echoing adds risk |

Crucial point: even `path`, which looks like "metadata", can hold client-controlled data such as `contacts[private-email@example.com].email`. Never adopt a naive rule that "values are sensitive, paths are always safe". Published paths must have a grammar and bounds.

## 4. Designing a minimal, safe error contract

Example using `ProblemDetail` (RFC 9457):

~~~json
{
  "type": "urn:problem:invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "Review the indicated fields.",
  "code": "INVALID_REQUEST",
  "issues": [
    {
      "code": "INVALID_FORMAT",
      "path": "password",
      "location": "body",
      "message": "Value has an invalid format"
    }
  ]
}
~~~

In this design:

1. `type` identifies the error category and never embeds URIs with query strings holding secrets.
2. `status` separates client errors (400) from server errors (500).
3. `detail` is a generic application phrase, never taken from `Exception#getMessage()`.
4. `code` is a stable response-level error code.
5. `issues` is a list of curated, safe issues.
6. `issues[*].code` comes exclusively from an allowlist, such as `REQUIRED`, `INVALID_EMAIL`, `INVALID_FORMAT`, `BELOW_MIN`, `INVALID_TYPE`.
7. `issues[*].path` holds an approved field name/path, not arbitrary raw Java property paths.
8. `issues[*].message` is resolved by `MessageSource` from a stable code without passing rejected values as arguments.

**You do not always have to return a path for every error.** For malformed JSON, the backend may be unable to identify a safe field, so return `path=""` / `location="body"`. For return-value or server-side Bean Validation configuration errors, never return a list of internal fields.

### 4.1. Public error codes are not the full Spring error code list

`FieldError#getCodes()` can contain `Pattern.registrationInput.password`, `Pattern.password`, `Pattern.java.lang.String`, `Pattern`. Some of those codes leak Java class/object names. Pick a public code:

~~~text
Pattern     -> INVALID_FORMAT
NotBlank    -> REQUIRED
NotNull     -> REQUIRED
Email       -> INVALID_EMAIL
Min         -> BELOW_MIN
Size        -> INVALID_LENGTH
typeMismatch -> INVALID_TYPE
unknown     -> INVALID_VALUE
~~~

This mapping is an **API policy**, not a built-in Spring mapping table. For custom constraints, add their codes to the allowlist after review; never serialize `error.getCodes()` verbatim.

### 4.2. Paths must follow a public schema

The demo exposes only:
- `email`, `password`, `apiToken`.
- `contacts[0].name`, `contacts[0].priority`, … up to a small index.
- `count` in query.
- `path=""` when the error applies to the body as a whole or has no approved public name.

Any other field becomes `field` or `parameter` instead of echoing an unreviewed path. In systems with hundreds of DTOs, build a metadata-driven allowlist from the API schema rather than hardcoding arbitrarily; **never replace an allowlist with "allow any reflection property"**.

### 4.3. Keep only as many issues as needed

For a malicious request with thousands of invalid elements, the full error set can exhaust memory and bandwidth. Enforce a policy:
- Sort issues safely and deterministically.
- Cap the returned issue count (e.g., max 50) and add `truncated=true` if needed.
- Never build messages from raw values to "explain better".
- Ensure framework input-size and collection-count limits run before building issues.

The demo project keeps logic visible and does not act as a full API gateway.

## 5. Exception contexts in Spring MVC 6.1+/6.2

### 5.1. `MethodArgumentNotValidException`

Typically occurs when `@Valid @RequestBody` or `@Valid @ModelAttribute` validates a command object without an immediately following `BindingResult`. Inspect:

~~~java
BindingResult binding = ex.getBindingResult();
for (ObjectError error : binding.getAllErrors()) {
    // Extract code and field name after allowlist checks.
    // Never read rejectedValue into the response.
}
~~~

`getAllErrors()` includes both field and global/object errors. Use `getFieldErrors()` if you only want field errors, provided global errors are handled separately so they are not dropped.

### 5.2. `HandlerMethodValidationException`

Since Spring Framework 6.1, direct method constraints such as `@Min` on `@RequestParam` or on a return value can trigger built-in MVC method validation.

~~~java
@GetMapping("/api/limits")
public Map<String, Integer> check(
        @RequestParam(name = "count")
        @Min(1) int count) {
    return Map.of("count", count);
}
~~~

Violating `count=0` normally returns HTTP 400 / `HandlerMethodValidationException`. Violating a constraint on a **return value** is a 500 error, not bad client input.

In `ex.getParameterValidationResults()`, Spring provides `ParameterValidationResult`, offering `getMethodParameter()`, `getResolvableErrors()`, and container index/key metadata. For nested DTO errors, a result can be `ParameterErrors` exposing `getFieldErrors()`. In a general implementation, classify parameter kinds (`query`/`header`/`path`/`body`/`form`) rather than treating every result as `query`.

**Never expose `getArgument()` or raw `MessageSourceResolvable#getArguments()`**. They can contain untrusted values, objects, or framework metadata.

### 5.3. JSON parsing, missing parameter, and type mismatch errors

`HttpMessageNotReadableException` handles malformed/unreadable JSON; `MethodArgumentTypeMismatchException` handles unconvertible query values; `MissingServletRequestParameterException` handles missing required query parameters. These occur **before or outside** Bean Validation on a DTO and typically have no `FieldError`.

Do not force them into `ConstraintViolation` or return parser exception messages. Use generic codes instead:
- `INVALID_JSON`: request body cannot be read.
- `INVALID_TYPE`: query/form input has the wrong type.
- `MISSING_PARAMETER`: a required parameter is absent.
- `INTERNAL_ERROR`: internal processing error.

### 5.4. Do not confuse Bean Validation with authorization

Even when input passes `@Valid`, the backend must still verify ownership, business invariants, and permissions. If a request sends `role=ADMIN`, do not merely "mask that value in the error response" and call it done; first and foremost, **never bind sensitive properties** into application objects. For form binding use dedicated DTOs and `setAllowedFields`; for JSON `@RequestBody`, Jackson deserializes per the DTO/JSON config and does not use form `allowedFields` the same way.

## 6. Runnable project: Spring Boot 3.5.7, Java 17

The example covers:
- JSON `@Valid @RequestBody` containing intentionally invalid passwords and API tokens.
- URL-encoded form with indexed fields and type mismatch.
- Query `@Min` using method validation.
- Malformed JSON and missing required parameter.
- Server-side failing return-value constraint.
- A `@RestControllerAdvice` that **builds public DTOs exclusively from allowlisted data**.
- `MessageSource` for English and Vietnamese.
- JUnit/`MockMvc` integration tests verifying responses **contain no secret strings or exception internals**.

No database is needed. Secrets in the tests are **synthetic marker strings**, never real passwords or tokens.

### 6.1. Directory tree

~~~text
pom.xml
src/main/java/com/example/safeerrors/
  SafeErrorsApplication.java
  ContactInput.java
  RegistrationInput.java
  PublicIssue.java
  RegistrationController.java
  SafeErrorAdvice.java
src/main/resources/
  messages.properties
  messages_vi.properties
src/test/java/com/example/safeerrors/
  SafeErrorAdviceIntegrationTest.java
  SafeErrorMappingTest.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>safe-validation-errors</artifactId>
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
</project>
~~~

The example uses Servlet Spring MVC (`spring-boot-starter-web`), **not WebFlux**. `spring-boot-starter-validation` provides the Jakarta Bean Validation provider. Tests use `@SpringBootTest @AutoConfigureMockMvc` to verify real MVC exception resolution rather than testing a helper in isolation.

### 6.3. Main application

~~~java
// src/main/java/com/example/safeerrors/SafeErrorsApplication.java
package com.example.safeerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeErrorsApplication.class, args);
    }
}
~~~

### 6.4. Nested DTO

~~~java
// src/main/java/com/example/safeerrors/ContactInput.java
package com.example.safeerrors;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class ContactInput {

    @NotBlank
    private String name;

    @Min(1)
    private Integer priority;

    public ContactInput() {}

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public Integer getPriority() { return priority; }
    public void setPriority(Integer priority) {
        this.priority = priority;
    }
}
~~~

`@Min(1)` allows `null`; if priority is required, add `@NotNull`. This lesson specifically demonstrates `typeMismatch` when a form submits letters for an `Integer`: conversion fails before the constraint ever sees a valid number.

### 6.5. DTO containing sensitive data

~~~java
// src/main/java/com/example/safeerrors/RegistrationInput.java
package com.example.safeerrors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import java.util.ArrayList;
import java.util.List;

public class RegistrationInput {

    @NotBlank
    @Email
    private String email;

    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9]{12,64}",
             message = "Internal password-format rule failed")
    private String password;

    @NotBlank
    @Pattern(regexp = "[A-Z0-9]{8,32}",
             message = "Internal API-token rule failed")
    private String apiToken;

    @Valid
    private List<ContactInput> contacts = new ArrayList<>();

    public RegistrationInput() {}

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getPassword() { return password; }
    public void setPassword(String password) {
        this.password = password;
    }

    public String getApiToken() { return apiToken; }
    public void setApiToken(String apiToken) {
        this.apiToken = apiToken;
    }

    public List<ContactInput> getContacts() {
        return contacts;
    }
    public void setContacts(List<ContactInput> contacts) {
        this.contacts = contacts;
    }
}
~~~

This is a **synthetic demo**, not a production password policy design: the regexes in the example only produce testable failures and do not replace proper password storage, breach checks, hashing, MFA, or credential policies.

Both `@Pattern` messages are intentionally written as **internal messages**. The advice will **never use `FieldError#getDefaultMessage()` to return them**; it substitutes server-managed `error.INVALID_FORMAT` instead. Tests verify neither `Internal password-format rule failed` nor `Internal API-token rule failed` appears in the response body.

For real protection, never write passwords or API tokens into logs/traces; on success, use dedicated secret storage/generation rather than echoing them in responses.

### 6.6. Controller illustrating error sources

~~~java
// src/main/java/com/example/safeerrors/RegistrationController.java
package com.example.safeerrors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class RegistrationController {

    @InitBinder("registrationForm")
    void configureForm(WebDataBinder binder) {
        binder.setAllowedFields(
                "email", "password", "apiToken",
                "contacts[*].name",
                "contacts[*].priority");
        binder.setAutoGrowCollectionLimit(10);
    }

    @PostMapping(path = "/api/register",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> registerJson(
            @Valid @RequestBody RegistrationInput body) {
        return Map.of("accepted", true);
    }

    @PostMapping(path = "/api/register/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> registerForm(
            @Valid @ModelAttribute("registrationForm")
            RegistrationInput form) {
        return Map.of("accepted", true);
    }

    @GetMapping("/api/limits")
    public Map<String, Integer> getLimit(
            @RequestParam(name = "count") @Min(1) int count) {
        return Map.of("count", count);
    }

    @GetMapping("/api/broken")
    @NotBlank
    public String brokenReturn() {
        return "";
    }
}
~~~

Class-level `@Validated` is omitted on the controller so **Spring MVC 6.1+'s built-in method validation** is used. `@InitBinder` restricts only **form property binding**, not Jackson JSON deserialization for `@RequestBody`. The DTO is kept minimal with only expected inputs; in production code, never put role, owner, or payment state into public DTOs.

`brokenReturn()` intentionally violates a return-value constraint and must be treated as a server error (HTTP 500). The advice below **never exposes the method name, constraint, or return value**.

### 6.7. Public issue record

~~~java
// src/main/java/com/example/safeerrors/PublicIssue.java
package com.example.safeerrors;

public record PublicIssue(
        String code,
        String path,
        String location,
        String message) {
}
~~~

This record has **no** `rejectedValue`, `invalidValue`, `cause`, `exception`, or `arguments` properties. Stripping sensitive data is enforced at the schema level, rather than sprinkling Jackson `@JsonIgnore` onto framework objects the application does not own.

### 6.8. Advice: select only allowlisted data

~~~java
// src/main/java/com/example/safeerrors/SafeErrorAdvice.java
package com.example.safeerrors;

import org.springframework.context.MessageSource;
import org.springframework.context.MessageSourceResolvable;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.net.URI;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

@RestControllerAdvice
public class SafeErrorAdvice {

    private final MessageSource messages;

    public SafeErrorAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> objectValidation(
            MethodArgumentNotValidException ex) {

        String location = ex.getParameter()
                .hasParameterAnnotation(ModelAttribute.class)
                ? "form" : "body";

        List<PublicIssue> issues = new ArrayList<>();
        for (ObjectError error :
                ex.getBindingResult().getAllErrors()) {
            issues.add(fromObjectError(
                    error, location, messages,
                    LocaleContextHolder.getLocale()));
        }
        return badRequest("INVALID_REQUEST", issues);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> methodValidation(
            HandlerMethodValidationException ex) {

        if (ex.isForReturnValue()) {
            // Return-value violation: server-side, never
            // expose raw method/return validation metadata.
            return internalFailure();
        }

        List<PublicIssue> issues = new ArrayList<>();

        for (ParameterValidationResult result :
                ex.getParameterValidationResults()) {

            MethodParameter parameter =
                    result.getMethodParameter();
            String location = publicLocation(parameter);

            if (result instanceof ParameterErrors nested) {
                for (ObjectError error : nested.getAllErrors()) {
                    issues.add(fromObjectError(
                            error, location, messages,
                            LocaleContextHolder.getLocale()));
                }
            } else {
                String path = publicParameterName(parameter);
                for (MessageSourceResolvable error :
                        result.getResolvableErrors()) {

                    String code = publicCode(error.getCodes());
                    issues.add(new PublicIssue(
                            code, path, location,
                            publicMessage(messages, code,
                                    LocaleContextHolder.getLocale())));
                }
            }
        }

        // Cross-parameter errors are not arbitrarily pinned to a single field.
        for (MessageSourceResolvable error :
                ex.getCrossParameterValidationResults()) {
            issues.add(new PublicIssue(
                    "INVALID_VALUE", "", "crossParameter",
                    publicMessage(messages, "INVALID_VALUE",
                            LocaleContextHolder.getLocale())));
        }

        return badRequest("INVALID_REQUEST", issues);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ProblemDetail> queryType(
            MethodArgumentTypeMismatchException ex) {

        // Never use ex.getValue() or ex.getMessage().
        String path = publicField(ex.getName());
        return badRequest("INVALID_REQUEST",
                List.of(new PublicIssue(
                        "INVALID_TYPE", path, "query",
                        publicMessage(messages, "INVALID_TYPE",
                                LocaleContextHolder.getLocale()))));
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ProblemDetail> missingQuery(
            MissingServletRequestParameterException ex) {

        return badRequest("INVALID_REQUEST",
                List.of(new PublicIssue(
                        "MISSING_PARAMETER",
                        publicField(ex.getParameterName()),
                        "query",
                        publicMessage(messages, "MISSING_PARAMETER",
                                LocaleContextHolder.getLocale()))));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ProblemDetail> invalidJson(
            HttpMessageNotReadableException ex) {

        // Never use ex.getMostSpecificCause()
        // or parser location/excerpts in public responses.
        return badRequest("INVALID_JSON",
                List.of(new PublicIssue(
                        "INVALID_JSON", "", "body",
                        publicMessage(messages, "INVALID_JSON",
                                LocaleContextHolder.getLocale()))));
    }

    private ResponseEntity<ProblemDetail> badRequest(
            String code, List<PublicIssue> issues) {

        ProblemDetail detail =
                ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);

        detail.setType(URI.create("urn:problem:invalid-request"));
        detail.setTitle("Invalid request");
        detail.setDetail("Review the indicated fields.");
        detail.setProperty("code", code);

        List<PublicIssue> safeSorted = issues.stream()
                .sorted(Comparator
                        .comparing(PublicIssue::location)
                        .thenComparing(PublicIssue::path)
                        .thenComparing(PublicIssue::code))
                .toList();
        detail.setProperty("issues", safeSorted);

        return ResponseEntity.badRequest().body(detail);
    }

    private static ResponseEntity<ProblemDetail> internalFailure() {
        ProblemDetail detail =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);

        detail.setType(URI.create("urn:problem:internal-error"));
        detail.setTitle("Internal error");
        detail.setDetail("The service could not complete the request.");
        detail.setProperty("code", "INTERNAL_ERROR");
        detail.setProperty("issues", List.of());

        return ResponseEntity.status(
                HttpStatus.INTERNAL_SERVER_ERROR).body(detail);
    }

    // Package-private for dedicated testing with a FieldError holding a secret.
    static PublicIssue fromObjectError(
            ObjectError error,
            String location,
            MessageSource messages,
            Locale locale) {

        String code = publicCode(error.getCode());
        String path = error instanceof FieldError field
                ? publicField(field.getField())
                : "";

        // Never read error.getDefaultMessage(),
        // error.getArguments(), or field.getRejectedValue().
        return new PublicIssue(
                code, path, location,
                publicMessage(messages, code, locale));
    }

    static String publicCode(String sourceCode) {
        if (sourceCode == null) {
            return "INVALID_VALUE";
        }

        return switch (sourceCode) {
            case "NotBlank", "NotNull", "NotEmpty" -> "REQUIRED";
            case "Email" -> "INVALID_EMAIL";
            case "Pattern" -> "INVALID_FORMAT";
            case "Size" -> "INVALID_LENGTH";
            case "Min" -> "BELOW_MIN";
            case "typeMismatch" -> "INVALID_TYPE";
            default -> "INVALID_VALUE";
        };
    }

    private static String publicCode(String[] candidateCodes) {
        if (candidateCodes == null) {
            return "INVALID_VALUE";
        }
        // Spring typically orders specific codes first, general codes last.
        for (int i = candidateCodes.length - 1; i >= 0; i--) {
            String code = publicCode(candidateCodes[i]);
            if (!"INVALID_VALUE".equals(code)) {
                return code;
            }
        }
        return "INVALID_VALUE";
    }

    private static String publicField(String field) {
        if (field == null) {
            return "field";
        }

        if ("email".equals(field)
                || "password".equals(field)
                || "apiToken".equals(field)
                || "count".equals(field)) {
            return field;
        }

        if (field.matches(
                "contacts\\[(0|[1-9][0-9]?)\\]\\.(name|priority)")) {
            return field;
        }
        return "field";
    }

    private static String publicLocation(
            MethodParameter parameter) {
        if (parameter.hasParameterAnnotation(RequestParam.class)) {
            return "query";
        }
        if (parameter.hasParameterAnnotation(PathVariable.class)) {
            return "path";
        }
        if (parameter.hasParameterAnnotation(RequestHeader.class)) {
            return "header";
        }
        if (parameter.hasParameterAnnotation(RequestBody.class)) {
            return "body";
        }
        if (parameter.hasParameterAnnotation(ModelAttribute.class)) {
            return "form";
        }
        return "parameter";
    }

    private static String publicParameterName(
            MethodParameter parameter) {
        RequestParam annotation =
                parameter.getParameterAnnotation(RequestParam.class);

        if (annotation == null) {
            return "parameter";
        }

        String name = annotation.name().isBlank()
                ? annotation.value() : annotation.name();

        return publicField(name);
    }

    private static String publicMessage(
            MessageSource messages,
            String code,
            Locale locale) {

        return messages.getMessage(
                "error." + code,
                null,
                "Invalid input",
                locale);
    }
}
~~~

**Security characteristics of this code:**
- `fromObjectError(...)` never **touches rejected values** or custom-constraint messages.
- `publicCode(...)` and `publicField(...)` are **positive allowlists**, rather than trying to "scrub sensitive words" from strings that can take endless variants.
- `publicMessage(...)` reads text from a **server-owned resource bundle**, never from request data.
- JSON parsing errors never expose raw Jackson exceptions.
- Return validation errors become HTTP 500 with zero method, field, or value details.
- `ProblemDetail` holds only standard fields and extensions explicitly set by the app.
- No raw exception messages or user inputs are logged in this code.
- Spring may populate RFC 9457's `instance` field during rendering. In production, if URL paths ever carry private data, **audit both `instance` and access logs**: never assume default `ProblemDetail` automatically hides URL data.

**Note on paths:** the app allows indices `contacts[0]` through `contacts[99]`. If larger lists are needed, adjust the grammar/limits per the public API contract and never expose emails/tokens inside Map keys. In WebFlux, path/container metadata APIs can differ; see Section 10.

### 6.9. Resource bundles for vetted messages

**`src/main/resources/messages.properties`:**

~~~properties
error.REQUIRED=This field is required
error.INVALID_EMAIL=Enter a valid email address
error.INVALID_FORMAT=Value has an invalid format
error.INVALID_LENGTH=Value has an invalid length
error.BELOW_MIN=Value is below the permitted minimum
error.INVALID_TYPE=Value has an invalid type
error.MISSING_PARAMETER=A required parameter is missing
error.INVALID_JSON=Request body is not valid JSON
error.INVALID_VALUE=Invalid value
~~~

**`src/main/resources/messages_vi.properties`:**

~~~properties
error.REQUIRED=Trường này là bắt buộc
error.INVALID_EMAIL=Địa chỉ email không hợp lệ
error.INVALID_FORMAT=Giá trị sai định dạng
error.INVALID_LENGTH=Độ dài giá trị không hợp lệ
error.BELOW_MIN=Giá trị nhỏ hơn ngưỡng cho phép
error.INVALID_TYPE=Giá trị sai kiểu dữ liệu
error.MISSING_PARAMETER=Thiếu tham số bắt buộc
error.INVALID_JSON=Nội dung JSON không hợp lệ
error.INVALID_VALUE=Giá trị không hợp lệ
~~~

When a client requests Vietnamese via the request locale, **the `INVALID_FORMAT` code stays unchanged**; only the message text changes language. Here `publicMessage` uses `LocaleContextHolder.getLocale()` via Spring MVC's request context and falls back safely if a key is missing. In WebFlux/reactive pipelines, handle locale propagation explicitly rather than relying on `ThreadLocal`.

## 7. JUnit/`MockMvc`: directly testing that no secrets leak

Do not assert only HTTP 400. A security test must deliberately submit recognizable marker values, **read the entire response body**, and verify those values never appear. Combine positive assertions (useful codes/paths are present) with negative assertions (no secrets or exception internals are present).

### 7.1. HTTP integration tests

~~~java
// src/test/java/com/example/safeerrors/SafeErrorAdviceIntegrationTest.java
package com.example.safeerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Locale;

import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeErrorAdviceIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidJsonDtoDoesNotEchoPasswordOrToken()
            throws Exception {

        mvc.perform(post("/api/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "email":"not-an-email_PRIVATE",
                      "password":"SECRET-password-123!",
                      "apiToken":"TOKEN-secret-456!",
                      "contacts":[{"name":"","priority":0}]
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_REQUEST"))
            .andExpect(jsonPath("$.issues[*].path", hasItems(
                    "email",
                    "password",
                    "apiToken",
                    "contacts[0].name",
                    "contacts[0].priority")))
            .andExpect(content().string(not(
                    containsString("SECRET-password-123!"))))
            .andExpect(content().string(not(
                    containsString("TOKEN-secret-456!"))))
            .andExpect(content().string(not(
                    containsString("not-an-email_PRIVATE"))))
            .andExpect(content().string(not(
                    containsString("Internal password-format rule"))))
            .andExpect(content().string(not(
                    containsString("Internal API-token rule"))))
            .andExpect(content().string(not(
                    containsString("rejectedValue"))));
    }

    @Test
    void formTypeMismatchIsSafeAndKeepsFieldPath()
            throws Exception {

        mvc.perform(post("/api/register/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "valid@example.com")
                .param("password", "SECRET-password-123!")
                .param("apiToken", "VALIDTOKEN99")
                .param("contacts[0].name", "Lan")
                .param("contacts[0].priority",
                        "not-a-number-PRIVATE"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[*].path", hasItems(
                    "password", "contacts[0].priority")))
            .andExpect(jsonPath("$.issues[*].code", hasItems(
                    "INVALID_FORMAT", "INVALID_TYPE")))
            .andExpect(content().string(not(
                    containsString("SECRET-password-123!"))))
            .andExpect(content().string(not(
                    containsString("not-a-number-PRIVATE"))))
            .andExpect(content().string(not(
                    containsString("typeMismatch.registration"))));
    }

    @Test
    void directMinConstraintShowsCodeWithoutInternalArgument()
            throws Exception {

        mvc.perform(get("/api/limits").param("count", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].path")
                    .value("count"))
            .andExpect(jsonPath("$.issues[0].location")
                    .value("query"))
            .andExpect(jsonPath("$.issues[0].code")
                    .value("BELOW_MIN"));
    }

    @Test
    void malformedNumericQueryNeverEchoesValue()
            throws Exception {

        mvc.perform(get("/api/limits")
                .param("count", "SECRET-QUERY-999"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("INVALID_TYPE"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("count"))
            .andExpect(content().string(not(
                    containsString("SECRET-QUERY-999"))))
            .andExpect(content().string(not(
                    containsString("NumberFormatException"))));
    }

    @Test
    void missingRequiredParameterDoesNotRevealMethodName()
            throws Exception {

        mvc.perform(get("/api/limits"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("MISSING_PARAMETER"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("count"))
            .andExpect(content().string(not(
                    containsString("RegistrationController"))));
    }

    @Test
    void malformedJsonNeverEchoesParserExcerpt()
            throws Exception {

        mvc.perform(post("/api/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"password":"SECRET-IN-BROKEN-JSON",
                     "apiToken":"SECRET-IN-PARSER",
                     "contacts":[
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"))
            .andExpect(content().string(not(
                    containsString("SECRET-IN-BROKEN-JSON"))))
            .andExpect(content().string(not(
                    containsString("SECRET-IN-PARSER"))))
            .andExpect(content().string(not(
                    containsString("JsonParseException"))));
    }

    @Test
    void badServerReturnIs500WithoutInternalDetails()
            throws Exception {

        mvc.perform(get("/api/broken"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
            .andExpect(jsonPath("$.issues.length()").value(0))
            .andExpect(content().string(not(
                    containsString("brokenReturn"))))
            .andExpect(content().string(not(
                    containsString("HandlerMethodValidationException"))));
    }

    @Test
    void vietnameseMessageUsesSameStableCode()
            throws Exception {

        mvc.perform(post("/api/register")
                .locale(Locale.forLanguageTag("vi"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"","password":"ValidPassword1234",
                     "apiToken":"VALIDTOKEN99"}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code")
                    .value("REQUIRED"))
            .andExpect(jsonPath("$.issues[0].path")
                    .value("email"))
            .andExpect(jsonPath("$.issues[0].message")
                    .value("Trường này là bắt buộc"));
    }

    @Test
    void validBodyAndQueryReturnSuccess() throws Exception {

        mvc.perform(post("/api/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"lan@example.com",
                     "password":"ValidPassword1234",
                     "apiToken":"VALIDTOKEN99",
                     "contacts":[{"name":"Lan","priority":1}]}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.accepted").value(true));

        mvc.perform(get("/api/limits").param("count", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(2));
    }
}
~~~

These tests **never assert raw exception messages**. They assert published error codes and paths while verifying synthetic secret markers, raw parser errors, and internal validation messages are **absent** from the response.

### 7.2. Unit test with a `FieldError` containing `rejectedValue` and a malicious `defaultMessage`

Integration tests exercise multiple framework layers. The unit test below directly tests the **mapping function** designed to discard raw data:

~~~java
// src/test/java/com/example/safeerrors/SafeErrorMappingTest.java
package com.example.safeerrors;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.validation.FieldError;

import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class SafeErrorMappingTest {

    @Test
    void mapperIgnoresRejectedValueAndUntrustedMessage()
            throws Exception {

        String secret = "PRIVATE-REJECTED-PASSWORD";
        FieldError raw = new FieldError(
                "registrationInput",
                "password",
                secret,
                false,
                new String[]{"Pattern"},
                null,
                "UNSAFE default message contains " + secret);

        StaticMessageSource catalog = new StaticMessageSource();
        catalog.addMessage("error.INVALID_FORMAT",
                Locale.ENGLISH, "Value has an invalid format");

        PublicIssue safe = SafeErrorAdvice.fromObjectError(
                raw, "body", catalog, Locale.ENGLISH);

        String json = new ObjectMapper()
                .writeValueAsString(safe);

        assertEquals("INVALID_FORMAT", safe.code());
        assertEquals("password", safe.path());
        assertEquals("Value has an invalid format",
                safe.message());

        assertFalse(json.contains(secret));
        assertFalse(json.contains("UNSAFE default message"));
        assertFalse(json.contains("rejectedValue"));
    }

    @Test
    void unapprovedFieldPathIsReplaced()
            throws Exception {

        FieldError raw = new FieldError(
                "registrationInput",
                "contacts[private-email@example.com].name",
                "private-data",
                false,
                new String[]{"NotBlank"},
                null,
                "private-data");

        StaticMessageSource catalog = new StaticMessageSource();
        catalog.addMessage("error.REQUIRED",
                Locale.ENGLISH, "This field is required");

        PublicIssue safe = SafeErrorAdvice.fromObjectError(
                raw, "body", catalog, Locale.ENGLISH);

        assertEquals("field", safe.path());
        String json = new ObjectMapper()
                .writeValueAsString(safe);
        assertFalse(json.contains("private-email@example.com"));
        assertFalse(json.contains("private-data"));
    }
}
~~~

**Expected outcome:** 11 JUnit tests PASS (9 HTTP tests and 2 mapper tests) with the project as declared. This is the expected result based on static code/API analysis, **not a claim that Maven was executed live**.

Run command:

~~~bash
mvn test
~~~

Run only the security tests:

~~~bash
mvn -Dtest=SafeErrorMappingTest,SafeErrorAdviceIntegrationTest test
~~~

Never use real secrets in tests, even in CI. Synthetic marker strings like `PRIVATE-REJECTED-PASSWORD` suffice to verify leak prevention without risking real sensitive data in logs or test reports.

### 7.3. Testing with curl

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i -X POST http://localhost:8080/api/register \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"email":"bad-email","password":"SECRET-password-123!","apiToken":"VALIDTOKEN99"}'
~~~

Expected response is 400 with `code="INVALID_REQUEST"` and issues carrying codes like `INVALID_EMAIL` and `INVALID_FORMAT`, **without** echoing `SECRET-password-123!`. Never send real passwords to a demo page or share requests containing credentials through unauthorized tools.

## 8. Anti-patterns to eliminate

### 8.1. Serializing framework error objects directly

~~~java
// DO NOT DO THIS:
return ResponseEntity.badRequest()
        .body(ex.getBindingResult());
~~~

Because `BindingResult` is not a public schema and can retain `rejectedValue`, raw property values, or unwanted internal fields.

~~~java
// DO NOT DO THIS:
return ResponseEntity.badRequest()
        .body(ex.getBindingResult().getFieldErrors());
~~~

Even when returning only `FieldError`s, the objects still carry raw rejected values. Replace with an application-owned `PublicIssue`.

### 8.2. Returning raw exception messages

~~~java
// DO NOT DO THIS:
return Map.of("message", exception.getMessage());
~~~

Messages can reveal packages/classes, method signatures, JSON snippets, SQL, or user input. Return only allowlisted message codes and server-vetted text.

### 8.3. Returning `getDefaultMessage()` for every case

~~~java
// NOT SAFE ENOUGH FOR ALL SYSTEMS:
String publicMessage = error.getDefaultMessage();
~~~

For built-in constraints with controlled messages, `getDefaultMessage()` may be fine. However, in open systems with custom validators, third-party annotations, dynamic interpolation, or messages concatenating user input, **it cannot be trusted by default**. A stronger strategy maps `sourceCode → publicCode → messageCatalog` as in the demo. If you decide to permit certain default messages, establish a source-specific policy and test with sensitive inputs.

### 8.4. Using regexes to "scrub secrets" from exception strings

~~~java
// AVOID:
String safe = exception.getMessage()
        .replaceAll("password=[^, ]+", "password=***");
~~~

This misses many secret formats (JSON-escaped, URL-encoded, quoted, nested arrays, base64, multiline, custom key names, multiple languages). **Never accept raw exception text and try to redact sensitive parts afterward**; construct responses exclusively from approved fields from the start.

### 8.5. Returning headers or request bodies "to help debug"

Headers like `Authorization`, `Cookie`, `X-API-Key`, `Set-Cookie`, and query parameters can carry credentials. Never dump `request.getHeaderNames()` and return key/value pairs. If a request identifier is truly needed, use a server-generated, format-checked ID rather than trusting arbitrary client-supplied trace headers.

### 8.6. Turning every exception into HTTP 400

If a return-value constraint fails or the backend has a configuration error, returning 400 breaks semantics, hides production outages, and sometimes leaks server details. Separate input validation (typically 400) from server errors (500); log server-side per security policy.

## 9. Logging and telemetry without leaking input

Not returning secrets over HTTP is insufficient if a `@ControllerAdvice` simultaneously runs:

~~~java
// DO NOT DO THIS:
logger.error("Validation failed: {}", exception.getMessage());
~~~

Specifically, Spring's `FieldError#toString()` and `BindException#getMessage()` can embed rejected values. Logs may be shipped to APM, analytics, third-party services, or systems with looser access controls than the origin data.

### Recommended logging policy

Log only approved attributes:

~~~java
// Illustrative, not part of the runnable project in Section 6.
log.info("request_rejected code={} issueCount={}",
        "INVALID_REQUEST", safeIssues.size());
~~~

For auditing and incident response, include:
- Server-generated request/correlation ID.
- HTTP method and public route template (without raw query strings).
- Status and standardized error code.
- Issue count, never raw failing values.
- Useful environment/service/version metadata inside the observability system.
- Proper access controls, retention/TTL, and encryption.

**Never log passwords or tokens, even at debug level**. Never log request bodies on login, registration, or payment endpoints. For server errors, stack traces may be necessary in protected internal logs, yet still watch for secrets inside exception messages/causes; use error aggregation with redaction/allowlists and test sampling before enabling in production.

### Correlation IDs are not secrets

A backend-generated ID, such as a UUID v4, can be returned in a `requestId` field so support can look up logs. Never echo arbitrary client-supplied `X-Request-ID` headers unchecked. If accepting inbound correlation IDs, enforce format, length, character set, and trust boundaries. Never place raw URLs with query tokens into `ProblemDetail.instance`.

## 10. Preventing leaks across other layers

### 10.1. `ProblemDetail.instance`

Spring can populate `ProblemDetail.instance` from the request path when unset. On endpoints carrying private information directly in the path, such as `/reset/{secret}`, echoing the path in responses or logs can leak the secret. **Never put secrets in URLs**; if legacy endpoints already do, override `instance` with a non-sensitive value or withhold raw paths externally.

### 10.2. Unsafe JSON serialization

Do not build error DTOs holding `Throwable`, `MethodParameter`, `BindingResult`, `ConstraintDescriptor`, or domain objects and then slap `@JsonIgnore` on a few fields. A framework upgrade can introduce new getters, or nested objects may go unignored. Designing a **dedicated record/class for the public error schema** is far easier to verify.

### 10.3. GraphQL, gRPC, WebSocket, and RSocket

The principle of exposing only error codes, safe messages, and vetted metadata still applies even when the response is not HTTP `ProblemDetail`:
- GraphQL `errors[*].extensions` must not contain raw exceptions or internal state.
- gRPC status details require explicit schemas, never raw framework objects.
- WebSocket error frames must not carry raw request payloads or stack traces.
- RSocket application errors must not turn arbitrary exception messages into public text.

Each transport has its own encoding, status mapping, and trace handling; do not copy MVC's `@RestControllerAdvice` blindly to other protocols.

### 10.4. Spring WebFlux

In WebFlux, object-only `@Valid @ModelAttribute` can throw `WebExchangeBindException`, while method validation in Spring WebFlux 6.1+ can throw `HandlerMethodValidationException`. Use WebFlux's reactive exception handlers / `ResponseEntityExceptionHandler`, never Servlet MVC imports.

Maintain the same security rules:
- Never serialize `WebExchangeBindException.getBindingResult()`.
- Never call `FieldError#getRejectedValue()` when building response bodies.
- For `Mono<ResponseEntity<ProblemDetail>>`, build the body from safe issues without blocking the event loop.
- Locale in reactive pipelines requires proper context propagation; never assume `ThreadLocal` follows the request.

### 10.5. Validation groups and cross-parameter constraints

`@Validated(Group.class)` selects constraint groups; Java group names may be internal. Never expose class names, payloads, or raw group metadata. For cross-parameter constraints, responses can emit `path=""` with a general code or `relatedFields` from a public list, rather than exposing full method signatures.

## 11. Issues easily missed during testing

| Scenario | Potentially leaked data | Assertion to include |
| --- | --- | --- |
| Password fails `@Pattern` | `FieldError.rejectedValue` | Body does not contain password marker |
| Invalid API token | `ConstraintViolation.invalidValue` | Body does not contain token marker |
| Invalid email | Email address value | Body contains only `email` path + error code |
| Indexed form type mismatch | `contacts[0].priority` + raw value | Keeps path, omits raw value |
| Malformed JSON | Jackson parser excerpt | Has `INVALID_JSON`, no parser details |
| Query type mismatch | `MethodArgumentTypeMismatchException.value` | Has `INVALID_TYPE`, never echoes query |
| Missing parameter | Java parameter/method details | Has `MISSING_PARAMETER` and public name |
| Return-value validation failure | Value, method name, class | HTTP 500, empty issue list |
| Custom validator concatenates input into message | `defaultMessage` holds input | Body takes catalog text, never default |
| Map key contains email/token | Key embedded in field path | Path canonicalized or replaced with placeholder |
| Exception with nested cause | SQL/file paths/internal class | No stack trace or cause |
| Locale=`vi`/`en` | Message changes | Public code remains unchanged |
| Logs/APM | Raw request/exception | Unit/integration audit on logging filters |
| Max issues | Excessive payload size | Intentional cap and test |
| Secret headers | `Authorization`, `Cookie` | Never logged or serialized |

Negative tests must inspect the **entire response body**. Do not check merely that the JSON lacks a `rejectedValue` property, because a secret may have been concatenated into `message`, `detail`, or `path`.

For some paths, default framework responses can change depending on `server.error.include-message`, `server.error.include-binding-errors`, `server.error.include-stacktrace`, or custom error attributes. Test behavior under **realistic production configuration**, not only unit tests on a mapper.

## 12. Deployment hardening and contract governance

### 12.1. Error rendering configuration

Spring Boot provides error attribute/rendering properties on certain error paths, such as:

~~~properties
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
~~~

These properties help when using Boot's built-in error path, yet **do not replace** sanitizing a custom `@RestControllerAdvice`. If your own code returns a raw `FieldError`, the settings above will not strip rejected values automatically.

### 12.2. API documentation review

Clearly document:
- Response-level `type`, `status`, and `code`.
- Stable list of issue codes and when each appears.
- `path` syntax for nested properties, indices, and object-level errors.
- `location` vocabulary and cross-parameter error handling.
- Locale mechanism and `message` fallback policy.
- Policy against echoing invalid values and exception diagnostics.
- Maximum issue limits, sort order, and versioning.

If a client genuinely needs to re-display input after a validation failure, it should keep form state client-side. Never use the backend as a round-trip echo for raw passwords/tokens via rejected values.

### 12.3. Security review and observability

The OWASP Developer Guide recommends error messages helpful enough for users to act **without exposing critical data or internals**; MITRE CWE-209 describes this exact weakness class. Audit across:
1. Response bodies and headers.
2. Standard/global exception handlers.
3. Application logs and request tracing.
4. Reverse proxy and API gateway logs.
5. Client telemetry and analytics.
6. Sentry/APM/error aggregation tools.
7. Test reports and CI artifacts.
8. Error-handling paths on other transports.

A safe HTTP response does not make the whole system safe if a reverse proxy still logs raw query strings containing tokens. Limit exposure starting from API design: keep credentials in appropriate headers/bodies rather than URLs, and still avoid logging raw headers/bodies.

## 13. Code review checklist

- [ ] Public error schema is application-owned; never return `BindingResult`, `FieldError`, `ConstraintViolation`, or `Throwable`.
- [ ] Never serialize `getRejectedValue()`, `getInvalidValue()`, `getArgument()`, raw `getArguments()`, or provider descriptors.
- [ ] Never use unvetted `exception.getMessage()`/`getDefaultMessage()` as public text.
- [ ] Error codes and field paths use **allowlists**, never exposing Java class/method names or sensitive Map keys.
- [ ] Messages are resolved by code from a server-owned `MessageSource` with locale support.
- [ ] Response-level `detail`, `title`, `type`, and `instance` contain no sensitive input.
- [ ] Input violations return appropriate HTTP 400; server/return violations keep 500 with minimal info.
- [ ] Handle JSON parse failures, form binding type mismatches, query conversion/missing parameters, and object/method validation.
- [ ] Negative tests submit marker secrets in body/form/query and assert they **appear nowhere in the response**.
- [ ] Positive tests retain code, path, location, and message sufficient for clients to fix errors.
- [ ] Never log raw request bodies, authorization headers, exception messages, or rejected values on sensitive endpoints.
- [ ] Production error settings are verified and not treated as the sole defense.
- [ ] Define policies for max issues, pagination/truncation (if applicable), path escaping, and rate/size limits.
- [ ] Error response API contracts have regression tests before upgrading Spring, Boot, or validators.

## 14. References

- Spring Framework 6.2 — Spring MVC Error Responses and `ProblemDetail` (RFC 9457): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — MVC Validation, `MethodArgumentNotValidException` and `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — `FieldError` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 — `ObjectError` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html
- Spring Framework 6.2 — `ParameterValidationResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Framework 6.2 — `ResponseEntityExceptionHandler` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Boot 3.5 — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- OWASP Developer Guide — Handle all Errors and Exceptions: https://devguide.owasp.org/en/04-design/02-web-app-checklist/10-handle-errors-exceptions/
- MITRE CWE-209 — Generation of Error Message Containing Sensitive Information: https://cwe.mitre.org/data/definitions/209.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
