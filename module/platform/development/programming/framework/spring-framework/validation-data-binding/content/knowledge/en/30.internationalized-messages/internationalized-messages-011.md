# Never Put Sensitive Data in Messages or Interpolation Expressions in Spring Validation

## 1. Goal: Errors Must Be Helpful Without Exposing User Data

Validation messages do not stay on the screen alone. They can travel through JSON APIs, `BindingResult`, exception handlers, logs, tracing, monitoring, error alert emails, analytics systems, or caches. If a message contains **user-entered values**, sensitive data can easily leak outside authorized boundaries.

For example, an endpoint receives:

- `secret` or `password`: passwords or secret codes;
- `accessToken`: authentication tokens;
- `recoveryCode`: recovery codes;
- `nationalId`: national identification numbers;
- `email`, street addresses, phone numbers, personal details.

A valid business error is “Password does not meet security requirements”. An **unsafe** error is “Password `user-entered-secret` does not meet requirements”, because even though the request was rejected, the response or log itself leaked the secret.

Two related but distinct sources of risk exist:

1. **Data leakage through message content:** the program concatenates `rejectedValue`/input directly into a message or log. Even without an expression engine, this exposes data.
2. **Passing untrusted input into an interpolation *template*:** some Jakarta Bean Validation providers, such as Hibernate Validator, support message parameters and Jakarta Expression Language (EL). Building a message template by concatenating input can cause **unintended expression evaluation**, depending on configuration and feature level.

**Guiding rule:** build messages from **server-controlled error codes/keys**, locale selection, and non-sensitive metadata; **never** pass raw input, target objects, tokens, or secrets into message templates or interpolation variables. Checking values is the validator's job; user feedback should describe **which rule was violated**, not echo back what was submitted.

## 2. Map of Where Data Can Leak

| Data Flow Point | Risk Signal | Safety Principle |
| --- | --- | --- |
| `ConstraintValidator#isValid` | Concatenating `value` into `message` or a custom violation template. | Keep templates fixed and free of sensitive values. |
| `ConstraintViolation#getMessage()` | Message may contain interpolated values. | Only use controlled messages; never inject input into templates. |
| `ConstraintViolation#getInvalidValue()` | Directly returns the rejected value. | Never serialize or log this value. |
| `FieldError#getRejectedValue()` | Retains the invalid field value after data binding. | Keep out of JSON, HTML, logs, and tracing. |
| `BindingResult` / `BindException` | Printing the full object/exception can drag in field errors and rejected values. | Extract only safe metadata; never log the raw result. |
| `HttpMessageNotReadableException` | Cause/JSON parse details may contain input or internal structure. | Return a generic body-unreadable message; do not echo exception messages. |
| `MessageSource#getMessage(...)` | Message arguments contain secrets, or key is client-chosen. | Only pass allowlisted keys and non-sensitive arguments. |
| `@ControllerAdvice` | Returning raw `ex.getMessage()`, `toString()`, stack traces, or target objects. | Use a stable public response schema mapped by error category. |
| Logs/telemetry | `logger.warn("{}", request)` or attaching body to spans. | Strip, mask, or restrict data; log error codes, normalized paths, and request IDs. |
| Frontend HTML | Using `innerHTML` for messages or raw rejected values. | Render as **text**; encode for the output context. |

**Note on sensitivity levels:** field names and error codes are not automatically public information either. An internal property like `internalRiskScore`, `passwordHash`, or deep entity paths can reveal system design. When building a public error API, **allowlist exposed field names** rather than emitting arbitrary property paths.

## 3. Distinguishing *Message Template*, *Interpolated Message*, and *Public Response*

### 3.1. Jakarta Bean Validation Has Two Separate Concepts

Given constraint:

~~~java
@NotBlank(message = "{signup.email.required}")
private String email;
~~~

`"{signup.email.required}"` is an application-declared **message template/descriptor**. Jakarta Validation's `MessageInterpolator` uses resource bundles and interpolation rules to turn it into a message, such as “Please enter an email”.

When a `ConstraintViolation` occurs:

- `violation.getMessageTemplate()` returns the original template, e.g., `"{signup.email.required}"`.
- `violation.getMessage()` returns the **interpolated** wording.
- `violation.getInvalidValue()` can return the **actual rejected value**, including secrets, and is **unsafe for responses or logs**.
- `violation.getPropertyPath()` identifies the violation location, though you should decide which parts of the path may be public.
- `violation.getConstraintDescriptor()` holds constraint metadata; there is no reason to serialize the entire descriptor into a JSON response.

Templates are **not** user data. Keep keys and templates authored, reviewed, and versioned in server source code or resources.

### 3.2. Spring `MessageSource` Is Another Message Resolution Layer

In Spring MVC, Bean Validation and binding errors can be placed into `BindingResult` as `FieldError` or `ObjectError` instances. A `FieldError` typically has:

- `getCode()`: base code such as `NotBlank`, `Size`, `typeMismatch`.
- `getCodes()`: candidate codes by object/field/type.
- `getDefaultMessage()`: fallback message (which may already have gone through Bean Validation interpolation).
- `getArguments()`: arguments for message resolution.
- `getRejectedValue()`: rejected value, **never display or log directly**.

`MessageSource` can call `getMessage(error, locale)` to try error codes in order. Even when Spring picks a seemingly safe message key, **arguments and default messages must still be controlled**. Putting a secret into message arguments or serializing `FieldError` directly will still leak data.

**Do not confuse the two layers:** Jakarta Bean Validation **interpolates constraint messages**, whereas Spring `MessageSource` **resolves messages by code and locale**. They can be integrated in Spring Boot, but that does not mean every bundle shares the same scope, syntax, or security policy.

## 4. Interpolation Syntax: `{...}` vs. `${...}`

Hibernate Validator, a widely used Jakarta Validation provider, supports:

1. **Message parameters** such as `{min}`, `{max}`, or `{signup.secret.invalid}`. These can reference constraint attributes, validator-added parameters, or keys in `ValidationMessages.properties`.
2. **Jakarta Expression Language** of the form `${...}`, allowing expressions over metadata, variables, and—depending on feature level—the validated object.

Example interpolating **non-sensitive metadata**:

~~~java
@Size(min = 12, max = 128,
      message = "Length must be between {min} and {max} characters")
private String secret;
~~~

In this example, `min=12` and `max=128` are **server-declared limits**, not the secret's content. Passing those limit numbers into a message is acceptable if product policy permits disclosing length requirements. Never bind `secret` into a `{userValue}` variable and ask the template to print it.

A familiar EL example is `${validatedValue}`. Hibernate Validator can expose the value under validation under this name when the EL context permits. For passwords, tokens, PII, or private content, **never use that expression to display the value**. A message does not need to repeat what the user typed in order to explain a rule.

### Escaping Syntax

According to Hibernate Validator documentation, if you need interpolation syntax characters **as literal text** inside a message descriptor, escaping rules exist for `\{`, `\}`, `\$`, and `\\`. However, **syntax escaping is not the primary strategy for handling untrusted data**. For secrets, the best approach is **never placing secrets into descriptors or arguments at all**; avoid guessing escaping rules across multiple libraries.

### Do Not Use EL to Craft Messages for Secrets

Two helpful messages without any EL:

~~~properties
signup.secret.invalid=Password does not meet security requirements.
signup.email.invalid=Email is invalid.
~~~

Instead of trying to construct “Value X has Y characters and misses Z conditions”, the application can provide guidance **with zero user input**: “Use at least 12 characters, including uppercase, lowercase, and digits”. This is also easier to translate, easier to test, and far lower risk.

## 5. Hibernate Validator: Expression Language Feature Levels

Since Hibernate Validator 6.2, `ExpressionLanguageFeatureLevel` provides capability levels for EL:

| Level | Capability | Security Guidance |
| --- | --- | --- |
| `NONE` | No EL interpolation. | Preferred for custom violations that need no EL. |
| `VARIABLES` | Allows added expression variables, formatter, and configured resource bundles. | Use only when truly needed; never put secrets in variables. |
| `BEAN_PROPERTIES` | Adds access to bean properties. | Evaluate the risk of exposing properties that should remain hidden. |
| `BEAN_METHODS` | Adds ability to invoke bean methods. | Very high security risk if templates can be influenced by input; **never enable just for dynamic phrasing**. |

In Hibernate Validator 8/9, **the default for standard constraint messages** can permit `BEAN_PROPERTIES`, while **EL for custom violations created via `ConstraintValidatorContext` defaults to `NONE`**; if you explicitly enable EL on a custom violation, a safer default is `VARIABLES`. These are **provider- and version-specific** details and should not be assumed as universal rules across every Bean Validation implementation.

Hibernate Validator documentation specifically warns against concatenating input directly into templates and granting broad EL permissions; doing so can trigger unintended expression execution, information disclosure, or severe consequences. Never use `BEAN_METHODS` for templates with any untrusted influence.

**Important:** Disabling EL **does not stop** a message from deliberately concatenating a secret as a plain string literal. These are two distinct layers of defense:

- Prevent **data leakage**: never include secrets in messages or responses.
- Prevent **expression injection**: never build templates from input and never relax EL permissions casually.

### Patterns to Avoid

~~~java
// WRONG: message contains raw input, leaking the value.
String message = "Invalid value: " + secret;

// WRONG: user input enters the *message template*.
context.buildConstraintViolationWithTemplate(
        "Invalid: " + secret)
        .addConstraintViolation();

// WRONG: an EL variable carrying the secret if later printed in the message.
// hibernateContext.addExpressionVariable("entered", secret);

// WRONG: logging the full rejected value.
// logger.warn("Rejected secret={}", secret);
~~~

These are **anti-patterns to spot during code review**, not code to run. An attacker does not need database access if the API or logs print the secret for them. With EL, do not rely on provider feature-level restrictions to justify letting client-controlled text into a template.

### Safe Pattern for Custom Violations

~~~java
@Override
public boolean isValid(String secret,
                       ConstraintValidatorContext context) {
    if (secret == null || secret.isBlank()) {
        return true; // @NotBlank can handle null/blank separately.
    }

    if (isAllowedByLocalPolicy(secret)) {
        return true;
    }

    context.disableDefaultConstraintViolation();
    context.buildConstraintViolationWithTemplate(
            "{signup.secret.invalid}")
            .addConstraintViolation();

    return false;
}
~~~

This is a **snippet** inside a `ConstraintValidator` with a hypothetical `isAllowedByLocalPolicy` helper. The template `"{signup.secret.invalid}"` is a **hardcoded key in source**, containing no secret. With Hibernate Validator's custom EL default, EL does not even need to be enabled here.

If only one message is needed, it is simpler to set `message = "{signup.secret.invalid}"` on the custom constraint annotation and have `isValid(...)` **return `false`**, without manually building a custom violation. The full runnable version in Section 9 uses this simpler approach.

### When You Must Pass Parameters into a Message

Some applications want to display limits such as `12` or `128`. Hibernate Validator provides `HibernateConstraintValidatorContext#addMessageParameter(name, value)` to add a message parameter **without** concatenating user input strings. Example **passing only non-sensitive metadata**:

~~~java
HibernateConstraintValidatorContext hibernate =
        context.unwrap(HibernateConstraintValidatorContext.class);

hibernate.addMessageParameter("policyMin", 12);

hibernate.disableDefaultConstraintViolation();
hibernate.buildConstraintViolationWithTemplate(
        "{signup.secret.min}")
        .addConstraintViolation();
~~~

With a server-controlled key:

~~~properties
signup.secret.min=Value must be at least {policyMin} characters long.
~~~

This snippet is **Hibernate Validator-specific**, requiring an import of `org.hibernate.validator.constraintvalidation.HibernateConstraintValidatorContext`, and is not a standalone file. On failure, the caller must return `false`; since the default violation was disabled, at least one custom violation must be added. Never pass a secret into `addMessageParameter` even though the API supports escaping; **escaping does not stop the value itself from being displayed**.

Likewise, `addExpressionVariable(...)` **is not automatically privacy-safe**. While binding a variable reduces injection risk compared to string concatenation, any template allowed to read/print that variable can still leak data. Only use EL when product requirements truly demand it and both feature levels and inputs are constrained.

## 6. Avoiding Data Leaks Through `BindingResult` and Spring MVC

`BindingResult` is designed to help UIs process errors and retain form input when needed. That is both a useful feature and the exact reason **you cannot serialize the error object directly**:

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
ResponseEntity<?> onInvalid(MethodArgumentNotValidException ex) {
    // WRONG: do not return BindingResult/FieldError directly as JSON.
    return ResponseEntity.badRequest()
            .body(ex.getBindingResult());
}
~~~

This is an illustrative anti-pattern. `FieldError#getRejectedValue()` can be a password, token, or PII. Many objects also carry internal object names, class names, constraint metadata, and property paths that clients should never see.

Operations to avoid as well:

~~~java
// Do not do this when input may be sensitive:
logger.warn("Validation exception: {}", ex);
logger.warn("All errors: {}", ex.getBindingResult());
logger.warn("Rejected value: {}", fieldError.getRejectedValue());
return ResponseEntity.badRequest()
        .body(Map.of("details", ex.getMessage()));
~~~

`Exception#toString()`, `getMessage()`, `BindingResult#toString()`, and messages created by converters/validators **can** include unintended data or details; never assume every version prints identical content. The security rule is **never rely on internal string formatting as an API or logging contract**.

### Returning Messages by Controlled Error Codes

Safer example:

~~~java
List<String> publicFields =
        ex.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getField)
                .map(field -> switch (field) {
                    case "email" -> "email";
                    case "secret" -> "secret";
                    default -> "request";
                })
                .distinct()
                .sorted()
                .toList();
~~~

This is a snippet inside a handler (complete version in Section 9). Only **allowlist public field names**; never return `rejectedValue`, templates, target objects, parser exceptions, or arbitrary messages. Then map each field to a **server-decided message code**, such as `signup.email.invalid` or `signup.secret.invalid`.

Subtle detail: `FieldError#getDefaultMessage()` should not be assumed 100% safe either if an application's custom validator or bundle could include raw input. For APIs needing strict redaction, use an **audited code/field mapping** instead of copying every default message.

### Object-Level Errors and Other Exceptions

- `getGlobalErrors()` returns object-level errors, which can come from class-level constraints. Never expose `ObjectError#getObjectName()` if it is an internal name; map it to a public error type.
- `HttpMessageNotReadableException` can occur when JSON fails to parse/deserialize, **before Bean Validation**. Never echo `ex.getMostSpecificCause().getMessage()`.
- `HandlerMethodValidationException` is another error type in MVC 6.1+ when method validation runs. If used, write a dedicated handler that enforces the **same no-value-leakage policy**.
- `ConstraintViolationException` thrown by another executable/service validation layer also exposes `ConstraintViolation#getInvalidValue()`; never serialize the raw set of violations.
- `@ModelAttribute` and `@RequestBody` go through different binding/conversion pipelines, yet both process **untrusted input**; never enforce redaction in one place while leaking raw values in the other.

## 7. Spring `MessageSource`: Translate **Codes**, Not **Secrets**

A safe multilingual design usually has three layers:

~~~text
User input -> binding / validation -> public error category
                                        |
                                        v
                          Allowlisted message key
                           /                 \
                    Locale vi             Locale en
                       |                      |
           "Mật khẩu không..."     "Secret does not..."
                       \                      /
                        v                    v
                  Generic JSON/HTML message
                  (no raw input)
~~~

A simple bundle:

~~~properties
signup.secret.invalid=Password does not meet security requirements.
signup.email.invalid=Email is invalid.
signup.request.invalid=Invalid request.
~~~

Keys are **server-defined**. Only pick keys from a fixed set:

~~~java
String key = switch (field) {
    case "email" -> "signup.email.invalid";
    case "secret" -> "signup.secret.invalid";
    default -> "signup.request.invalid";
};

String publicMessage =
        messageSource.getMessage(key, null, locale);
~~~

This is a snippet inside a handler with `field`, `messageSource`, and `locale` variables. **Never** construct keys from arbitrary client-supplied names and let clients query internal bundle keys.

### Be Careful with `MessageFormat` Arguments Too

Spring `MessageSource` can format messages with placeholders like `{0}`, `{1}`. This is **not** the same syntax or engine as Hibernate Validator EL `${...}`, yet argument values are still **displayed** after formatting.

Reasonable example:

~~~java
messageSource.getMessage(
        "signup.secret.minimum",
        new Object[] {12},  // non-sensitive metadata
        locale);
~~~

With bundle:

~~~properties
signup.secret.minimum=Password must be at least {0} characters.
~~~

Inappropriate example:

~~~java
messageSource.getMessage(
        "signup.secret.rejected",
        new Object[] {secret}, // WRONG: message may print the secret.
        locale);
~~~

If the message has `{0}`, the `secret` content becomes part of the returned sentence. Even if the message code is allowlisted, **arguments can still leak data**. When dynamic info is not truly needed, pass `null` arguments and use static text.

### Locale and Caching

The same error may need Vietnamese or English. The backend can read `Locale` from `Accept-Language` or another application locale policy. Choosing a different locale **never** justifies returning extra data:

~~~text
vi: "Mật khẩu không đáp ứng yêu cầu bảo mật."
en: "Secret does not meet the security requirements."
~~~

If public responses vary by `Accept-Language`, consider `Vary: Accept-Language` or an appropriate cache policy so a CDN never serves the wrong language. Never cache request bodies containing secrets, and never use raw validation responses as a store of submitted values.

## 8. Risk Taxonomy: Interpolation, Logging, HTML, and Observability

### 8.1. Message Interpolation Is Not HTML Escaping

Suppose a client enters text containing HTML characters into a displayable field. Even if message interpolation evaluates no EL, if the frontend renders raw messages via `innerHTML`, markup strings can create an XSS risk. **Do not conflate two kinds of protection**:

1. Keep sensitive/user-controlled values out of error messages right in the backend.
2. When rendering permitted messages/field data, escape/encode appropriately for the **output context**.
3. On the frontend, prefer DOM `textContent`, React text rendering, or equivalent APIs—never HTML injection APIs for error messages.

A properly serialized JSON response can still be mishandled if the frontend takes `message` and assigns it to `innerHTML`. JSON escaping and HTML output encoding are **two different contexts**.

### 8.2. Logging Must Minimize Data

OWASP recommends avoiding logging passwords, access tokens, session identifiers, and many kinds of sensitive personal data directly. Instead of:

~~~java
logger.warn("Invalid sign up: {}", signupRequest);
logger.warn("Field errors: {}", bindingResult.getAllErrors());
~~~

log **metadata sufficient for investigation without user input**:

~~~java
logger.info("Validation failed: route={}, code={}, count={}",
        "/api/signup",
        "VALIDATION_FAILED",
        errorCount);
~~~

This snippet assumes `logger` and `errorCount`. In production, useful additional fields include timestamp, a random request ID, route template, status, and error category. If using a correlation ID, control its source and format; never use an access token as a request ID.

**Beware** of logging/observability middleware: body logging filters, request/response capture, APM span attributes, automatic exception reporters, or DTO `toString()` methods can leak values **outside the controller**. Audit infrastructure configuration, not just `logger.info` calls in business code.

### 8.3. Never Rely on Hashing to “Hide” Secrets in Logs

Hashing a password or token and logging it can still create linkable values, aid guessing, or allow re-identification depending on the data. **By default, log neither the secret nor a hash of the secret.** If a special audit requirement exists, design it under an independent data/retention policy and threat model; do not add `hash(password)` to logs just because it looks safer.

### 8.4. Overly Detailed Messages Can Also Leak System State

In a login form, distinct “email does not exist” vs. “wrong password” messages can enable account enumeration. Depending on the use case, a generic `AUTH_FAILED` code is safer. For signup, messages saying a username/email is already taken can also permit enumeration, so weigh product/security policy, rate limiting, and UX design. **Not every non-password detail is harmless.**

## 9. Runnable Example: Spring Boot 3.x, Java 17+, and Safe Error Messages

The following demo aims to **never print raw secrets into validation messages, JSON, or logs**. It uses:

- Jakarta Bean Validation: `@NotBlank`, `@Email`, and a `@SecretPolicy` constraint.
- Hibernate Validator (via `spring-boot-starter-validation`) as the standard Spring Boot 3.x provider.
- `@Valid @RequestBody` to validate the JSON DTO.
- `@RestControllerAdvice` returning **error codes, allowlisted field names, and translated messages** via `MessageSource`.
- `ValidationMessages.properties` to hold fixed constraint templates, while `messages*.properties` drives public responses.
- `MockMvc` and JUnit 5 to test the no-input-echo policy.

To run standalone without a database, the endpoint only simulates accepting valid input; **it never stores or logs the secret**.

### 9.1. Maven Dependencies

Create a Spring Boot 3.x project with parent/BOM version management, Java 17+, and Maven. Add:

~~~xml
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
~~~

Java files belong to package `com.example.safevalidation`. Resources reside in `src/main/resources/`. Use the starters above; **do not manually pin a different Hibernate Validator version** from the Spring Boot BOM.

### 9.2. File `SafeValidationApplication.java`

Path: `src/main/java/com/example/safevalidation/SafeValidationApplication.java`

~~~java
package com.example.safevalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeValidationApplication.class, args);
    }
}
~~~

### 9.3. File `SecretPolicy.java`: Fixed Message Template

Path: `src/main/java/com/example/safevalidation/SecretPolicy.java`

~~~java
package com.example.safevalidation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.RECORD_COMPONENT,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = SecretPolicyValidator.class)
public @interface SecretPolicy {

    String message() default "{signup.secret.invalid}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

**Security point:** `message()` holds only a **fixed key**. It does not accept the secret value and does not use `${validatedValue}`. When multiple locales are needed, the provider resolves the key via message interpolation configuration; the public response is still governed by a separate mapping.

### 9.4. File `SecretPolicyValidator.java`: Validate Only, Never Repeat Input

Path: `src/main/java/com/example/safevalidation/SecretPolicyValidator.java`

~~~java
package com.example.safevalidation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class SecretPolicyValidator
        implements ConstraintValidator<SecretPolicy, String> {

    @Override
    public boolean isValid(
            String secret, ConstraintValidatorContext context) {

        // @NotBlank on the DTO handles null or blank.
        if (secret == null || secret.isBlank()) {
            return true;
        }

        // Simple, local policy, no I/O.
        if (secret.length() < 12 || secret.length() > 128) {
            return false;
        }

        boolean upper = false;
        boolean lower = false;
        boolean digit = false;

        for (int i = 0; i < secret.length(); i++) {
            char c = secret.charAt(i);
            upper |= Character.isUpperCase(c);
            lower |= Character.isLowerCase(c);
            digit |= Character.isDigit(c);
        }

        return upper && lower && digit;
    }
}
~~~

The validator performs no logging, network/database calls, or per-request state retention, and never puts `secret` into a message. The provider creates a violation with template `"{signup.secret.invalid}"` when `isValid` returns `false`.

**Policy limitation:** this is a learning example on message safety, not a complete guide to choosing a modern password policy. For production, follow an organization-approved authentication standard; consider length, blocklists, rate limiting, and guidelines like NIST SP 800-63. Do not copy arbitrary complexity rules just because the example checks uppercase/digits. Distinguish Java UTF-16 length from user-perceived character counts if supporting Unicode; the demo uses a simple length rule.

### 9.5. File `SignupRequest.java`: DTO Without a Self-Logging `toString`

Path: `src/main/java/com/example/safevalidation/SignupRequest.java`

~~~java
package com.example.safevalidation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public final class SignupRequest {

    @NotBlank
    @Email
    private String email;

    @NotBlank
    @SecretPolicy
    private String secret;

    public SignupRequest() {
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getSecret() {
        return secret;
    }

    public void setSecret(String secret) {
        this.secret = secret;
    }
}
~~~

This DTO omits `toString` to avoid accidentally constructing a string that leaks `secret`. Even so, **that does not make the object safe to log via arbitrary serializers or reflection loggers**. Avoid tools that automatically dump all fields. Also avoid Lombok `@Data` or Java `record` types containing secrets if objects could be logged carelessly, because auto-generated `toString()` includes field values.

### 9.6. File `SignupController.java`

Path: `src/main/java/com/example/safevalidation/SignupController.java`

~~~java
package com.example.safevalidation;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class SignupController {

    @PostMapping(path = "/signup",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> signup(
            @Valid @RequestBody SignupRequest request) {

        // Demo: only accept valid requests.
        // Never log or echo request.getSecret().
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "accepted"));
    }
}
~~~

`@Valid` triggers validation on `SignupRequest` after JSON deserialization succeeds. If `secret` fails the constraint, the method body is usually **never invoked**; `MethodArgumentNotValidException` is handled by the advice next. If the JSON has broken syntax, the converter can throw `HttpMessageNotReadableException` **even before validation**.

This endpoint **does not persist a real account** and returns HTTP 201 solely to illustrate the valid-request status; a production system should return Created only after persisting the resource safely under proper security handling.

### 9.7. File `SignupValidationAdvice.java`: A Controlled Error Contract

Path: `src/main/java/com/example/safevalidation/SignupValidationAdvice.java`

~~~java
package com.example.safevalidation;

import org.springframework.context.MessageSource;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.List;
import java.util.Locale;

@RestControllerAdvice
public class SignupValidationAdvice {

    private final MessageSource messages;

    public SignupValidationAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<PublicError> invalidArgument(
            MethodArgumentNotValidException ex, Locale locale) {

        // Only pick field names from the public allowlist.
        List<String> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .map(field -> switch (field) {
                    case "email" -> "email";
                    case "secret" -> "secret";
                    default -> "request";
                })
                .distinct()
                .sorted()
                .toList();

        List<FieldIssue> issues = fields.stream()
                .map(field -> {
                    String code = switch (field) {
                        case "email" -> "signup.email.invalid";
                        case "secret" -> "signup.secret.invalid";
                        default -> "signup.request.invalid";
                    };

                    return new FieldIssue(
                            field,
                            "INVALID_FIELD",
                            messages.getMessage(code, null, locale));
                })
                .toList();

        // Do not serialize ex, BindingResult, or rejectedValue.
        return ResponseEntity.badRequest().body(
                new PublicError("VALIDATION_FAILED", issues));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<PublicError> unreadableBody(
            HttpMessageNotReadableException ex, Locale locale) {

        // Never return ex.getMessage(), parser cause, or raw body.
        return ResponseEntity.badRequest().body(
                new PublicError(
                        "MALFORMED_BODY",
                        List.of(new FieldIssue(
                                "request",
                                "INVALID_BODY",
                                messages.getMessage(
                                        "signup.request.invalid",
                                        null,
                                        locale)))));
    }

    public record FieldIssue(
            String field, String code, String message) {
    }

    public record PublicError(
            String error, List<FieldIssue> fields) {
    }
}
~~~

Security analysis:

1. `FieldError#getField()` is **mapped through a switch**. Only `email`, `secret`, or `request` can be emitted; nested or internal property paths are never exposed.
2. Message keys are also selected by a **server-authored switch**, never supplied by query parameters or the body.
3. Neither `FieldError#getRejectedValue()`, `ex.getMessage()`, `BindingResult#toString()`, nor `ConstraintViolation#getInvalidValue()` is called.
4. `MessageSource#getMessage(code, null, locale)` runs **with no arguments**, because the response needs no dynamic values.
5. `HttpMessageNotReadableException` has a dedicated handler returning a generic message without exposing decoder/Jackson errors to clients.
6. `distinct()` + `sorted()` ensure deterministic field order for tests and clients even when both `@NotBlank` and `@SecretPolicy` fail.
7. `FieldIssue`/`PublicError` records contain only public metadata, never secrets or target objects.

**Limitation:** the illustrative handler covers only field errors and unreadable JSON. Real applications may also need dedicated mappings for global/object-level errors, `HandlerMethodValidationException`, media type errors, security errors, and service/domain exceptions. Every branch must follow the **same redaction policy**. Never catch `Exception` broadly and return 400, as that can mask server bugs.

### 9.8. Spring Bundles: `messages.properties`, `messages_vi.properties`, `messages_en.properties`

Create `src/main/resources/application.properties`:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Create `src/main/resources/messages.properties`:

~~~properties
signup.email.invalid=Email address is invalid.
signup.secret.invalid=Secret does not meet the security requirements.
signup.request.invalid=Request body is invalid.
~~~

Create `src/main/resources/messages_en.properties`:

~~~properties
signup.email.invalid=Email address is invalid.
signup.secret.invalid=Secret does not meet the security requirements.
signup.request.invalid=Request body is invalid.
~~~

Create `src/main/resources/messages_vi.properties`:

~~~properties
signup.email.invalid=Email không hợp lệ.
signup.secret.invalid=Mật khẩu không đáp ứng yêu cầu bảo mật.
signup.request.invalid=Dữ liệu yêu cầu không hợp lệ.
~~~

In Spring Boot, the base bundle `messages.properties` lets auto-configuration discover the basename. The request locale can be resolved by Spring MVC from `Accept-Language` unless the app swaps `LocaleResolver`; `messages_vi` and `messages_en` supply the corresponding public messages.

### 9.9. Jakarta Validation Bundles: `ValidationMessages.properties`

Create `src/main/resources/ValidationMessages.properties`:

~~~properties
signup.secret.invalid=Secret does not meet the configured policy.
~~~

Depending on the Bean Validation provider's i18n goals, you can also create `ValidationMessages_vi.properties`:

~~~properties
signup.secret.invalid=Mật khẩu không đáp ứng quy tắc được cấu hình.
~~~

**Why two bundle groups?** `ValidationMessages*` belongs to Jakarta Bean Validation message interpolation; `messages*` in this example belongs to Spring `MessageSource` for building public responses. In Spring Boot, `LocalValidatorFactoryBean` and `MessageSource` can be integrated, yet **do not rely on coincidental language alignment of default constraint messages** to drive responses. Regardless of whether the provider interpolates English or Vietnamese, the advice returns only **allowlisted** messages via `messages.getMessage(code,null,locale)`.

For systems with complex i18n, you can unify the bundle/message source across both layers **once you have full control over keys, interpolation context, and versions**, though that is a separate architectural decision. Using two clear bundles in the demo makes security boundaries easy to test.

### 9.10. Example HTTP Responses

Request with a short secret:

~~~http
POST /api/signup
Content-Type: application/json
Accept-Language: vi

{"email":"lan@example.com","secret":"tiny"}
~~~

Expected HTTP 400:

~~~json
{
  "error": "VALIDATION_FAILED",
  "fields": [
    {
      "field": "secret",
      "code": "INVALID_FIELD",
      "message": "Mật khẩu không đáp ứng yêu cầu bảo mật."
    }
  ]
}
~~~

The response contains neither `"tiny"` nor `rejectedValue`, describes no internal constraint expressions, and leaks no target object.

With `Accept-Language: en`, the same error returns:

~~~json
{
  "error": "VALIDATION_FAILED",
  "fields": [
    {
      "field": "secret",
      "code": "INVALID_FIELD",
      "message": "Secret does not meet the security requirements."
    }
  ]
}
~~~

Both messages share the same error code with different locales. If an organization requires hiding even which field failed (such as during login), return a single generic public code instead of listing `secret`; the exact policy must fit the threat model.

## 10. JUnit 5 and MockMvc Testing: Verifying Input Is Never Echoed

Create `src/test/java/com/example/safevalidation/SafeValidationApplicationTest.java`:

~~~java
package com.example.safevalidation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Set;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SafeValidationApplicationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    Validator validator;

    @Test
    void validRequestReturnsOnlyPublicStatus() throws Exception {
        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "email":"lan@example.com",
                              "secret":"StrongSecret123"
                            }
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("accepted"))
                .andExpect(content().string(
                        not(containsString("StrongSecret123"))));
    }

    @Test
    void vietnameseValidationMessageDoesNotEchoSecret()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .content("""
                            {
                              "email":"lan@example.com",
                              "secret":"tiny"
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("secret"))
                .andExpect(jsonPath("$.fields[0].message")
                        .value(
                            "Mật khẩu không đáp ứng yêu cầu bảo mật."))
                .andExpect(content().string(
                        not(containsString("tiny"))));
    }

    @Test
    void englishMessageUsesControlledTranslation()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                    .content("""
                            {
                              "email":"lan@example.com",
                              "secret":"tiny"
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].message")
                        .value(
                            "Secret does not meet the security requirements."))
                .andExpect(content().string(
                        not(containsString("tiny"))));
    }

    @Test
    void invalidEmailIsMappedToPublicFieldAndMessage()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                    .content("""
                            {
                              "email":"invalid-address",
                              "secret":"StrongSecret123"
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].field")
                        .value("email"))
                .andExpect(jsonPath("$.fields[0].message")
                        .value("Email address is invalid."))
                .andExpect(content().string(
                        not(containsString("invalid-address"))));
    }

    @Test
    void multipleErrorsAreDeduplicatedAndSorted()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .content("""
                            {
                              "email":"invalid-address",
                              "secret":"tiny"
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].field")
                        .value("email"))
                .andExpect(jsonPath("$.fields[1].field")
                        .value("secret"))
                .andExpect(content().string(
                        not(containsString("invalid-address"))))
                .andExpect(content().string(
                        not(containsString("tiny"))));
    }

    @Test
    void missingSecretIsRejectedWithoutEcho()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .content("""
                            {"email":"lan@example.com"}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].field")
                        .value("secret"))
                .andExpect(jsonPath("$.fields[0].code")
                        .value("INVALID_FIELD"));
    }

    @Test
    void brokenJsonGetsOnlyGenericMessage()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .content("{\"email\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("MALFORMED_BODY"))
                .andExpect(jsonPath("$.fields[0].message")
                        .value("Dữ liệu yêu cầu không hợp lệ."));
    }

    @Test
    void missingBodyIsGenericRequestError()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "en"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("MALFORMED_BODY"));
    }

    @Test
    void constraintTemplateIsFixedAndDoesNotContainInput() {
        SignupRequest input = new SignupRequest();
        input.setEmail("lan@example.com");
        input.setSecret("tiny");

        Set<ConstraintViolation<SignupRequest>> violations =
                validator.validate(input);

        assertEquals(1, violations.size());

        ConstraintViolation<SignupRequest> violation =
                violations.iterator().next();

        assertEquals("{signup.secret.invalid}",
                violation.getMessageTemplate());
        assertFalse(violation.getMessage().contains("tiny"));
        assertEquals("secret",
                violation.getPropertyPath().toString());
    }
}
~~~

With the listed files and starters, **9 tests are designed to pass**. They verify:

- Valid JSON returns public status without echoing the secret.
- Secret failure returns accurate Vietnamese/English translations without `"tiny"`.
- Invalid email does not echo the raw address back.
- Multiple field errors are deduplicated and sorted.
- Missing secret is rejected without emitting sensitive values.
- Malformed JSON and missing bodies return generic errors.
- `ConstraintViolation#getMessageTemplate()` is a **fixed key** containing no user input.

Run from the Maven project root:

~~~bash
./mvnw test -Dtest=SafeValidationApplicationTest
~~~

On Windows, run `mvnw.cmd test -Dtest=SafeValidationApplicationTest`. If Maven is installed globally, run `mvn test -Dtest=SafeValidationApplicationTest`.

**Limitation:** the lesson provides a consistent Spring Boot 3.x + Java 17+ source/test set; actual execution depends on versions, build setup, and configuration. This is not proof that **every middleware** in a running stack strips raw bodies from logs. In production, also inspect reverse proxies, request logging filters, security events, APM/tracing, and data policies.

### Manual Testing with curl

While the app is running via `./mvnw spring-boot:run`:

~~~bash
curl -i -X POST "http://localhost:8080/api/signup" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"email":"lan@example.com","secret":"tiny"}'

curl -i -X POST "http://localhost:8080/api/signup" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: en" \
  -d '{"email":"lan@example.com","secret":"tiny"}'
~~~

Both commands use **dummy values, not real secrets**. Never pass production passwords or tokens into shell history just to test an API; data passed via `-d` can end up in terminal history, process monitoring, or test-environment logs. When testing live systems, use dedicated dummy secrets and proper safeguards.

## 11. When Using `@ModelAttribute`/Forms: Special Binding Considerations

With an HTML form:

~~~java
@PostMapping(path = "/signup-form",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
ResponseEntity<?> signupForm(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult result) {
    // Use allowlisted codes/fields;
    // do not serialize result or form.
    return result.hasErrors()
            ? ResponseEntity.badRequest().build()
            : ResponseEntity.ok().build();
}
~~~

This is a **snippet** for another controller without complete `SignupForm`/imports. In Spring MVC, form-urlencoded/query values are bound via `WebDataBinder`, and `BindingResult` right after the object allows local error handling.

For example, the user submits:

~~~text
email=lan@example.com
secret=example-only-secret
age=not-a-number
~~~

The binder can create a `FieldError` with code `typeMismatch` for `age`, and `getRejectedValue()` can retain `"not-a-number"`. The `secret` field can also hold a rejected value on validation failure. **Do not relax the general policy based on a single “non-sensitive” field**; logging serializers do not automatically know which fields need masking when new DTOs are added.

If you want to avoid forcing users to re-type form fields after an error, **the backend does not have to send the secret back**. The frontend can retain UI input state in memory per product policy, or ask the user to re-enter sensitive fields. Never store secrets in server-side sessions or message bundles just to re-render a form.

### `setAllowedFields` and Redaction Are Two Different Concerns

`WebDataBinder#setAllowedFields(...)` restricts **property binding** to prevent mass assignment; it **does not automatically redact values** in `FieldError`, logs, or validator-generated messages. Conversely, refraining from echoing secrets **does not replace** authorization checks and updatable-field allowlists.

With JSON `@RequestBody`, Jackson deserializes per JSON mapping rules; `setAllowedFields` on form binders is not a general solution against JSON overposting. Use dedicated request DTOs, validation, authentication/authorization, and controlled response schemas.

## 12. Protecting Data at Other Layers

### 12.1. Never Use Messages to Reveal Authentication State

A login error must not become an oracle distinguishing “username exists” from “wrong password” when the threat model forbids it. Use a generic code/message such as `AUTHENTICATION_FAILED`. For password resets or signup, consider anti-enumeration, rate limiting, and balanced UX.

### 12.2. Never Serialize Raw Exceptions

Classes such as `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `ConstraintViolationException`, and `HttpMessageNotReadableException` typically carry developer-focused metadata and causes. They are **not response DTOs**. Use `@RestControllerAdvice`/`ResponseEntityExceptionHandler` to separate technical exceptions from public payloads; responses must control fields, codes, messages, and statuses.

### 12.3. Centralized Log Redaction

Organizations should establish consistent policies across logging and telemetry middleware: skip body logging on login/signup, strip `Authorization`/`Cookie` headers, never log tokens, configure trace sampling and retention, and audit APM integrations and log access controls. Controller-level redaction is necessary but insufficient if a reverse proxy already logs raw bodies upstream.

### 12.4. Never Use Uncontrolled Data as an Error Code

Even without echoing passwords, an endpoint that lets clients pass a bundle key directly to `MessageSource` can leak internal messages. Public error codes must come from a **server-side enum/allowlist**, never from `request.getParameter("messageCode")` or an untrusted JSON `code` field.

### 12.5. Safety of Payload and Input Limits

Beyond preventing data leaks, the validation pipeline should also bound JSON/form/multipart size and complexity, avoid catastrophic regex backtracking, avoid blocking DB/network calls inside custom validators on reactive event loops, and prevent clients from triggering massive error lists that bloat responses or logs. Consider capping returned field errors, while avoiding silently dropping meaningful errors without a clear contract.

## 13. Additional Security Tests for Real Projects

The tests in Section 10 check sample secrets. A stronger security regression suite should include:

1. **Canary marker test:** send a unique test string in sensitive fields and assert it **never appears** in HTTP responses, test logs, tracing attributes, or error-reporting collectors (using synthetic test data).
2. **Locale matrix:** `vi`, `en`, fallback locale, and unsupported locales all avoid echoing input.
3. **Binding errors:** `@ModelAttribute`, form-urlencoded, `typeMismatch`, nested field errors, and `getRejectedValue()` are never serialized.
4. **JSON parser errors:** malformed syntax, type errors, and empty bodies never print raw JSON or parser-specific details.
5. **Bean Validation custom violations:** `getMessageTemplate()` is fixed with no untrusted data; EL feature level is never raised unnecessarily.
6. **Multiple errors/global errors:** mapped via allowlists with bounded counts, exposing no internal property paths.
7. **Internationalization arguments:** message keys and arguments are controlled; no `secret` or user PII in `Object[] args`.
8. **Logging integration:** request-logging middleware, access logs, tracing/APM, and exception reporters all enforce redaction.
9. **Frontend rendering:** messages are rendered as text, never injecting markup/scripts via `innerHTML`.
10. **Authentication/error uniformity:** login/recovery errors never allow account-state guessing beyond policy.

When testing logging, never create or use real secrets. Static synthetic test data can be verified automatically by CI tooling. **Never treat a passing response test as proof that logs and telemetry are safe**; inspect every downstream sink independently.

## 14. Common Pitfalls and How to Fix Them

| Anti-pattern | Why It Is Dangerous | Fix |
| --- | --- | --- |
| `"Invalid: " + value` in `ConstraintValidator` | Prints raw input, potentially leaking secrets. | Fix key/message with no raw value. |
| `buildConstraintViolationWithTemplate(prefix + input)` | Template can be influenced by input and EL, while leaking data. | Server-controlled template literal, e.g., `"{signup.secret.invalid}"`. |
| Using `${validatedValue}` for passwords | Prints the value when EL permits. | Never use the validated value in messages. |
| Enabling `BEAN_METHODS` for custom violations | Expands dangerous expression evaluation surface. | Keep EL disabled or at the minimum needed; prefer no EL. |
| Passing secrets to `addMessageParameter` | Escaping does not prevent display of the value. | Pass only non-sensitive metadata, e.g., min/max. |
| Returning `ex.getBindingResult()` as JSON | Can serialize rejected values and internal metadata. | Map to an allowlisted public error DTO. |
| Using `FieldError#getDefaultMessage()` for all errors | Custom messages may already contain raw input. | Use audited codes/fields + `MessageSource`. |
| `logger.warn("{}", request)` | DTO/record `toString()` may include secrets. | Log error type, status, request ID; avoid raw bodies. |
| Logging full `ConstraintViolationException` objects | May contain invalid values via `toString`/cause. | Select safe metadata; never log values. |
| Exposing JSON parser exceptions directly to clients | Can leak body fragments and internal details. | Fixed generic 400, controlled logging. |
| `MessageSource` taking keys/arguments directly from requests | Can expose internal keys or print sensitive values. | Server-side allowlist + safe arguments. |
| Frontend using `innerHTML=message` | Can execute untrusted HTML. | Text rendering / context-appropriate encoding. |
| Masking secrets only in the Controller | Filters, APM, or reverse proxies may still capture bodies. | Audit the entire observability pipeline. |
| Hashing secrets and logging the hash | Can create fingerprints or guessing signals. | By default, log neither secrets nor hashes of secrets. |
| Overly detailed login errors | Can create an enumeration oracle. | Design generic codes/text per threat model. |

## 15. Pre-Production Review Checklist

- [ ] No `value`, `rejectedValue`, `getInvalidValue()`, or secret-bearing DTO appears in message templates, error JSON, or logs.
- [ ] Custom `ConstraintValidator` uses fixed keys/descriptors; never concatenates input into `buildConstraintViolationWithTemplate(...)`.
- [ ] No `${validatedValue}` or EL variables holding secrets; never enable `BEAN_METHODS` or elevated feature levels without reviewed justification.
- [ ] When using `addMessageParameter`, pass only non-sensitive limits/metadata; never treat escaping as redaction.
- [ ] `MessageSource` uses allowlisted keys and zero user secrets in formatting arguments.
- [ ] Spring `BindingResult` and `FieldError` are read only for necessary metadata; never serialize or log the full objects.
- [ ] Handlers cover validation, parsing, method validation, and business errors under a unified public schema.
- [ ] Public field names are allowlisted; error messages never disclose internal property or class names.
- [ ] Vietnamese and English i18n bundles contain no placeholders that insert secret values.
- [ ] JSON/body parsing errors never echo raw requests, exception causes, or stack traces.
- [ ] Frontend renders messages as plain text with context-appropriate output encoding.
- [ ] Logging, APM, and proxies do not capture request bodies, `Authorization`/`Cookie` headers, or tokens by default.
- [ ] Canary-marker tests verify responses, logs, and traces across multiple locales and error types.
- [ ] Login and signup rules do not create enumeration vectors outside policy.
- [ ] Appropriate retention, access control, and incident response procedures cover any metadata still retained in logs/monitoring.

**Summary:** **Error messages should explain only which condition failed, never repeat user data.** In Spring and Jakarta Validation, this requires **fixed templates/keys**, **non-sensitive message arguments**, **strict EL controls**, **never serializing `BindingResult`/`FieldError` directly**, and **i18n via `MessageSource` over a server-side allowlist**. Message safety must be verified across the API, logs, telemetry, and frontend—not only inside custom validators.

## References

- Hibernate Validator 8 Reference Guide — Message Interpolation, EL feature levels, and custom violation messages: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-message-interpolation
- Hibernate Validator 8 API — `ExpressionLanguageFeatureLevel`: https://docs.hibernate.org/validator/8.0/api/org/hibernate/validator/messageinterpolation/ExpressionLanguageFeatureLevel.html
- Hibernate Validator 8 API — `BaseHibernateValidatorConfiguration` (EL and validated values logging): https://docs.hibernate.org/validator/8.0/api/org/hibernate/validator/BaseHibernateValidatorConfiguration.html
- Spring Framework Reference — Bean Validation integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework Reference — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework Javadoc — `FieldError#getRejectedValue()`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework Javadoc — `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Boot Reference — Internationalization: https://docs.spring.io/spring-boot/reference/features/internationalization.html
- OWASP Logging Cheat Sheet — excluding sensitive data from logs: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Cross Site Scripting Prevention Cheat Sheet — output encoding and HTML context handling: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
