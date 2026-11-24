# Designing Field-Level Error Responses Without Exposing Sensitive Input Data

## 1. Objectives and Context

A Spring Boot API frequently receives JSON containing personal data, tokens, addresses, transaction details, and nested fields. When validation fails, returning field-level errors helps clients know precisely what to fix. However, echoing raw rejected values, exception messages, or the request object in HTTP responses can leak passwords, payment tokens, emails, addresses, internal identifiers, and security-sensitive details.

Example invalid request:

~~~json
{
  "email": "private_input_not_an_email",
  "paymentToken": "tok_PRIVATE_example_314",
  "shipping": {
    "city": "",
    "postalCode": "private_bad_zip_314"
  },
  "items": [
    {"sku": "", "quantity": 0}
  ]
}
~~~

The client needs to know that email has an invalid format, city is blank, and quantity must be greater than 0. The client **does not need** to receive back the submitted email, paymentToken, postalCode, stack traces, or server class names.

This lesson aims for a structured, stable, bounded, and testable response:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request data is invalid.",
  "errorId": "c8b3913d-5ea7-4a6e-85ed-f2b24fc75ef0",
  "errors": [
    {
      "field": "email",
      "code": "FORMAT",
      "message": "Invalid format."
    },
    {
      "field": "items[0].quantity",
      "code": "RANGE",
      "message": "Value is out of the allowed range."
    },
    {
      "field": "shipping.city",
      "code": "REQUIRED",
      "message": "Field is required."
    }
  ]
}
~~~

The UUID here is purely illustrative; the application must generate a fresh errorId rather than hardcoding one. The paymentToken field may not appear in the list if it is valid; even when invalid, return only the field name, error code, and safe message—**never echo the token value**.

After this lesson, learners will be able to distinguish binding/validation/business errors; read FieldErrors safely; create an @RestControllerAdvice for Spring MVC and understand differences with Spring WebFlux; handle nested paths and lists; design stable error codes and limit error counts; write integration tests verifying zero data leakage; and apply sound logging/observability practices.

**Example scope:** Java 17+, Spring Boot 3.3.x, and Spring MVC using Jakarta Bean Validation. Data-protection concepts also apply to WebFlux, though exception types and error-handling mechanics differ. Spring Boot 4.x updates baseline/framework/dependency versions; verify APIs for your target version before reusing code.

## 2. Separating Three Data Validation Layers

On the web-runtime side, a request normally passes through these stages:

~~~text
HTTP request JSON
   |
   v
HTTP body reader / Jackson
   |
   +--> Invalid JSON syntax, invalid enum, type mismatch
   |         -> body reading / mapping error
   |
   v
Java request DTO
   |
   v
Jakarta Bean Validation
   |
   +--> @NotBlank, @Email, @Min, @Pattern, @Valid
   |         -> field / object errors
   |
   v
Application service
   |
   +--> Business rules, permissions, state, uniqueness
   |         -> domain / authorization error
   |
   v
Business result / response
~~~

**JSON parsing and data binding:** content cannot be read or converted to Java types. For example, quantity receives an object instead of an Integer, or deliveryMethod receives an unknown enum. These errors typically occur before Bean Validation.

**Bean Validation:** the DTO is constructed, yet constraints fail. Examples include @Email, @NotBlank, @Min(1), or an empty field in a nested object.

**Business validation:** data types are valid, yet the action is disallowed. Examples include an expired coupon, discontinued product, or unauthorized user. Business errors require codes and HTTP statuses matching the API contract; do not force every domain error into VALIDATION_FAILED.

For security, none of the three layers should expose raw input, stack traces, or exception.getMessage() to clients.

## 3. Why Is Returning rejectedValue Dangerous?

When MVC binding/validation encounters an error, FieldError can provide:

- getField(): field name/path, e.g., email or items[0].quantity.
- getCode(): a code created by the binder/validator, e.g., NotBlank, Email, Min, typeMismatch.
- getCodes(): multiple candidate message codes for message resolution.
- getDefaultMessage(): default validation or binding message.
- getRejectedValue(): **the rejected input value**, sometimes containing sensitive data.
- getObjectName(): target object name during binding.

Anti-pattern:

~~~java
Map<String, Object> details = Map.of(
        "field", fieldError.getField(),
        "rejectedValue", fieldError.getRejectedValue(),
        "message", fieldError.getDefaultMessage()
);
~~~

This snippet has multiple flaws: getRejectedValue can be a token/email/address; Map.of rejects null if rejectedValue is null; getDefaultMessage can carry custom validator arguments, internal names, or interpolated values.

Another anti-pattern:

~~~java
return ResponseEntity.badRequest()
        .body(exception.getMessage());
~~~

Messages from Jackson, binding, database, or validation exceptions are internal details, not API contracts. Certain exceptions embed paths, payload fragments, Java types, and stack context. Sending them directly to clients can violate data minimization principles.

**Principle:** error responses should contain only publicly approved fields, stable error codes, safe explanations, an error ID, and truly necessary non-sensitive metadata. Never pull rejected values into the response.

## 4. Classifying Sensitive Data in Validation

Passwords and tokens are not the only data needing protection:

| Category | Examples | Risk When Echoed in Errors |
| --- | --- | --- |
| Authentication secrets | password, access token, refresh token, API key | Account/access takeover |
| Payment | paymentToken, card, account number, transaction code | Fraud, financial data exposure |
| PII | email, phone number, date of birth, address | Privacy violation |
| Identity | ID document number, national ID, internal userId | Cross-referencing / identification |
| Security metadata | OTP, recovery code, session ID | Bypass / intrusion |
| Business secrets | cost price, internal coupon, sensitive tenant ID | Organizational data leak |
| Free text | customer notes, medical descriptions, form text | May contain arbitrary secrets |
| Uploaded data | filename, path, file content, MIME metadata | Exposes content or infrastructure |

There is no simplistic rule like "only hide fields named password". A note field can hold secrets entered by a user. If responses or logs echo raw JSON, the risk persists even when the DTO lacks dedicated secret fields.

Field names themselves also warrant selectivity. A field path like account.internalRiskScore or an absurdly long index can reveal backend structure. Therefore, allowlist **public field paths** rather than blindly trusting every field name from reflection or binding.

## 5. Proposed Error Response Contract

A clean schema:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request data is invalid.",
  "errorId": "c8b3913d-5ea7-4a6e-85ed-f2b24fc75ef0",
  "errors": [
    {
      "field": "shipping.city",
      "code": "REQUIRED",
      "message": "Field is required."
    }
  ]
}
~~~

### 5.1. Meaning of Each Field

- code (root): request-level error category, e.g., VALIDATION_FAILED, INVALID_JSON.
- message (root): brief description revealing no input data.
- errorId: application-generated ID for the error event. Useful for correlating with logs if logged together; a freshly generated UUID alone is not automatically a distributed trace ID.
- errors: list of field-level or request-level errors.
- field: allowlisted public path, e.g., shipping.city, items[0].quantity.
- code (field): stable code such as REQUIRED, FORMAT, RANGE, TYPE, INVALID.
- message (field): known message from a static dictionary or controlled MessageSource; never copy raw exceptions.

### 5.2. Fields That Must Never Appear

- inputValue, rejectedValue, rawRequest, originalBody, rawHeaders.
- exception, stackTrace, internalType, SQL, parameter values.
- access tokens, passwords, payment tokens, or the rejected field's contents.
- information about other users, other accounts, or internal security policies.
- server hostnames or system filesystem paths from exceptions.

JSON field names alone do not make an API secure; what matters is **which data sources** are permitted inside them.

## 6. HTTP Status and Error Codes Should Not Be Conflated

| Scenario | Typical HTTP Status | Application Code |
| --- | --- | --- |
| Malformed JSON syntax | 400 | INVALID_JSON |
| Invalid JSON mapping | 400 | INVALID_JSON |
| DTO @Valid failure | 400 | VALIDATION_FAILED |
| Query/path/type conversion failure | 400 | INVALID_PARAMETER |
| Unsupported Content-Type | 415 | UNSUPPORTED_MEDIA_TYPE |
| Payload too large | 413 | PAYLOAD_TOO_LARGE |
| Unauthenticated request | 401 | UNAUTHENTICATED |
| Authenticated but insufficient permission | 403 | FORBIDDEN |
| Resource does not exist | 404 | NOT_FOUND |
| Business state conflict | 409 | CONFLICT |
| Server/dependency failure | 5xx | INTERNAL_ERROR |

Some organizations choose 422 Unprocessable Content for semantic validation. That is reasonable when consistent across the API contract; **Spring MVC by default uses 400 for @Valid @RequestBody**. Do not switch 400 to 422 arbitrarily just because a field failed.

In particular, authorization failures must never masquerade as validation errors. Returning "userId does not exist" or "that account is already registered" can leak identity info; consider generic messages to prevent user enumeration depending on threat context.

## 7. Field Error Codes: Prefer Stable Codes Over Raw Validator Codes

Jakarta Bean Validation provides @NotBlank, @NotNull, @Min, @Email, @Pattern, and custom constraints. Annotation names or Spring binding codes can change during refactoring, so responses should not blindly mirror raw internal code names.

Mapping example:

| Internal code | Public code | Public message |
| --- | --- | --- |
| NotBlank, NotNull, NotEmpty | REQUIRED | Field is required. |
| Email, Pattern | FORMAT | Invalid format. |
| Min, Max, Positive, Negative | RANGE | Value is out of the allowed range. |
| typeMismatch | TYPE | Invalid data type. |
| Other codes outside allowlist | INVALID | Invalid value. |

Do not use FieldError.getDefaultMessage() directly when templates are uncontrolled. Custom messages can embed parameters such as "{value}" or "{validatedValue}"; even on a valid validation error, exposing the value causes data leakage.

When multilingual support is required, resolve **public codes** via MessageSource using safe message templates. Never interpolate raw input values into templates.

## 8. Allowlisting Field Names and Nested Paths

Spring can represent nested field paths:

~~~text
email
shipping.city
shipping.postalCode
items[0].sku
items[0].quantity
items[3].quantity
~~~

To protect internal DTO structures, return only paths declared in the API contract. Example:

~~~java
private static String publicField(String path) {
    if (Set.of(
            "email",
            "paymentToken",
            "shipping.city",
            "shipping.postalCode",
            "items").contains(path)) {
        return path;
    }

    if (path.matches("items\\[[0-9]{1,3}\\]\\.(sku|quantity)")) {
        return path;
    }

    return "request";
}
~~~

This snippet requires importing java.util.Set. It permits only explicit fields and list indexes up to three digits; all other paths collapse to request. This reduces the risk of leaking undisclosed field names, though it is not a JSON Schema validator.

### 8.1. Should the Name paymentToken Be Returned?

A field name already documented in the public API request can be returned so the user can fix input; **however, its value must never be returned**. In systems needing to minimize inference about token presence/format, errors may be grouped under payment or request instead of naming the exact field. That is an API/security contract decision with no one-size-fits-all answer.

### 8.2. Limiting Indexes and Depth

Never return unbounded paths from payloads with thousands of elements. A client can deliberately submit huge lists to trigger thousands of validation errors. Define:

- Maximum element count processed at the request layer.
- Maximum number of errors returned, e.g., 20.
- Maximum path length and allowed patterns.
- Deterministic ordering so tests do not flake.
- An indication that additional errors exist without listing every field.

If returning a total error count, consider whether that number leaks sensitive structure/metadata; many public APIs simply truncate errors at the cap.

## 9. Global/Object-Level Errors Without a Specific Field

Not every constraint maps to a single field name. For example, a rule "start date must be before end date" may be a class-level constraint or multi-field validation logic.

When getGlobalErrors() contains an ObjectError, you can return:

~~~json
{
  "field": "request",
  "code": "INVALID",
  "message": "Request data is invalid."
}
~~~

Do not invent a specific field name if the constraint does not identify a single failing field. Frontends can display global errors at the top of the form.

**Avoid returning objectName**, Java class names, internal field lists, or raw ObjectError messages. If a business rule such as "date range" needs its own code, define an intentional public code and test it.

## 10. Spring MVC: @RequestBody + @Valid Errors

A typical controller:

~~~java
@PostMapping("/api/checkouts")
public ResponseEntity<Map<String, String>> create(
        @Valid @RequestBody CheckoutRequest request) {
    return ResponseEntity.accepted()
            .body(Map.of("status", "accepted"));
}
~~~

The above is a snippet. For a DTO with Bean Validation, Spring MVC normally:

1. Matches the route.
2. Uses the Jackson HttpMessageConverter to read the body into the DTO.
3. Runs validation for the @Valid request body if a validation provider is present.
4. On errors, throws MethodArgumentNotValidException (when no adjacent BindingResult captures it for the controller).
5. @RestControllerAdvice or ResponseEntityExceptionHandler handles the exception.
6. If valid, the controller is invoked.

Do not add a BindingResult parameter after @Valid @RequestBody just to swallow the exception without handling it: when accepting BindingResult, the controller must explicitly check validation and avoid running business logic on invalid input.

Since Spring Framework 6.1, Spring MVC also includes built-in method validation; when placing constraints directly on controller method parameters, HandlerMethodValidationException may occur instead of MethodArgumentNotValidException. Account for both if your project uses method-level constraints.

## 11. Spring MVC: Distinguishing Which Exceptions May Expose Field Details

- MethodArgumentNotValidException: carries BindingResult; you can extract FieldErrors/ObjectErrors and **sanitize** them before returning.
- HandlerMethodValidationException: occurs when method validation applies; needs a matching response policy, e.g., returning a request-level error unless parameters are mapped to public names.
- HttpMessageNotReadableException: unreadable JSON/body; never return raw causes or JSON fragments.
- HttpMediaTypeNotSupportedException: unsupported media type; usually 415.
- MissingServletRequestParameterException: missing request parameter; if naming it, allowlist public names.
- MethodArgumentTypeMismatchException: path/query type mismatch; avoid returning getValue() as it may hold sensitive data.
- ConstraintViolationException: typically tied to method/service validation; distinguish client errors from server/programming bugs rather than returning 400 for every case.

An exception handler catching generic Exception and returning 400 is an anti-pattern: it hides server errors and skews metrics. Explicitly handle known input error types and preserve 5xx for unexpected failures.

## 12. Java 17+ and Spring Boot 3.3: Hands-On Project

The complete project below demonstrates:

- A DTO containing email, paymentToken, nested address, and nested items.
- Jakarta Bean Validation using @Valid to validate nested objects and list elements.
- @RestControllerAdvice choosing fields/codes/messages from allowlists.
- Never calling getRejectedValue() or getDefaultMessage() when building responses.
- Stable responses capped at 20 errors, sorted and deduplicated.
- Tests verifying status, error codes, and the **absence of secrets** in responses.

The example performs no real payments, stores no paymentToken, and connects to no database. All test values are dummy markers used to prove the anti-leakage policy. Requires JDK 17+, a Gradle Wrapper compatible with Spring Boot 3.3, and Maven Central access for dependencies.

Structure:

~~~text
safe-validation-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/validation/
        SafeValidationApplication.java
        CheckoutRequest.java
        ShippingAddress.java
        CheckoutItem.java
        CheckoutController.java
        FieldIssue.java
        ApiError.java
        ValidationAdvice.java
      resources/
        application.yml
    test/
      java/example/validation/
        CheckoutApiTests.java
~~~

### 12.1. settings.gradle

~~~groovy
rootProject.name = 'safe-validation-demo'
~~~

### 12.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
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

spring-boot-starter-web enables Spring MVC + embedded Tomcat in standard configuration. spring-boot-starter-validation brings Hibernate Validator and a compatible Jakarta Bean Validation implementation. Gradle/JDK version compatibility must follow the Spring Boot 3.3 matrix.

### 12.3. application.yml

~~~yaml
spring:
  application:
    name: safe-validation-demo

server:
  port: 8080
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false
~~~

The server.error settings in Boot 3.3 prevent exposing messages, binding details, or stack traces in default Boot-managed error responses. **They do not automatically disable a custom @ExceptionHandler that returns raw exception messages.** Therefore, sanitization in application code remains mandatory.

### 12.4. SafeValidationApplication.java

~~~java
package example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeValidationApplication.class, args);
    }
}
~~~

### 12.5. ShippingAddress.java

~~~java
package example.validation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record ShippingAddress(
        @NotBlank String city,
        @NotBlank
        @Pattern(regexp = "[0-9]{5,6}") String postalCode
) {
}
~~~

postalCode requires 5–6 digits in this demo. This is an illustrative contract, not an official rule for all countries/regions. Both null/blank and invalid formats are checked; multiple FieldErrors may be emitted for the same field, which the error handler below limits and sorts.

### 12.6. CheckoutItem.java

~~~java
package example.validation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CheckoutItem(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity
) {
}
~~~

Uses Integer instead of int to distinguish missing/null quantity from 0. @Min(1) does not reject null by itself, so @NotNull is required.

### 12.7. CheckoutRequest.java

~~~java
package example.validation;

import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record CheckoutRequest(
        @NotBlank @Email String email,
        @NotBlank String paymentToken,
        @NotNull @Valid ShippingAddress shipping,
        @NotEmpty List<@NotNull @Valid CheckoutItem> items
) {
}
~~~

@Valid on shipping and list elements triggers cascade checks for nested fields. @NotEmpty requires items to be non-null/non-empty. @NotNull on each element rejects null list entries. In applications with real payment flows, never place raw card numbers or other secrets into DTOs/responses/logs outside proper security and compliance scope.

### 12.8. FieldIssue.java

~~~java
package example.validation;

public record FieldIssue(
        String field,
        String code,
        String message
) {
}
~~~

### 12.9. ApiError.java

~~~java
package example.validation;

import java.util.List;

public record ApiError(
        String code,
        String message,
        String errorId,
        List<FieldIssue> errors
) {
}
~~~

Neither record has a value field, making it impossible to accidentally serialize rejectedValue simply by returning the Error DTO in the response body.

### 12.10. CheckoutController.java

~~~java
package example.validation;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/checkouts")
public class CheckoutController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> create(
            @Valid @RequestBody CheckoutRequest request) {

        // Confirms valid request received; does not process real payments.
        return ResponseEntity.accepted()
                .body(Map.of("status", "accepted"));
    }
}
~~~

When valid, the endpoint returns 202 Accepted with only status in the body, **never echoing the request DTO**. Production APIs should choose 201/202/200 based on business semantics and handle idempotency rather than blindly copying 202 from this example.

### 12.11. ValidationAdvice.java

~~~java
package example.validation;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationAdvice {

    private static final int MAX_ERRORS = 20;

    private static final Set<String> PUBLIC_FIELDS = Set.of(
            "email",
            "paymentToken",
            "shipping.city",
            "shipping.postalCode",
            "items"
    );

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> validation(
            MethodArgumentNotValidException ex) {

        List<FieldIssue> issues = new ArrayList<>();

        for (FieldError fieldError
                : ex.getBindingResult().getFieldErrors()) {

            String code = publicCode(fieldError.getCode());

            issues.add(new FieldIssue(
                    publicField(fieldError.getField()),
                    code,
                    publicMessage(code)));
        }

        for (ObjectError ignored
                : ex.getBindingResult().getGlobalErrors()) {
            issues.add(new FieldIssue(
                    "request",
                    "INVALID",
                    "Request data is invalid."));
        }

        List<FieldIssue> result = issues.stream()
                .distinct()
                .sorted(Comparator.comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .limit(MAX_ERRORS)
                .toList();

        return response(
                HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED",
                result);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException ignored) {
        return response(
                HttpStatus.BAD_REQUEST,
                "INVALID_JSON",
                List.of());
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ApiError> unsupportedMediaType(
            HttpMediaTypeNotSupportedException ignored) {
        return response(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "UNSUPPORTED_MEDIA_TYPE",
                List.of());
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ApiError> methodValidation(
            HandlerMethodValidationException ex) {

        if (ex.isForReturnValue()) {
            return response(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "INTERNAL_ERROR",
                    List.of());
        }

        return response(
                HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED",
                List.of(new FieldIssue(
                        "request",
                        "INVALID",
                        "Request data is invalid.")));
    }

    private static String publicField(String raw) {
        if (raw != null && PUBLIC_FIELDS.contains(raw)) {
            return raw;
        }

        if (raw != null
                && raw.matches(
                        "items\\[[0-9]{1,3}\\]\\.(sku|quantity)")) {
            return raw;
        }

        return "request";
    }

    private static String publicCode(String internal) {
        if (internal == null) {
            return "INVALID";
        }

        return switch (internal) {
            case "NotBlank", "NotNull", "NotEmpty" -> "REQUIRED";
            case "Email", "Pattern" -> "FORMAT";
            case "Min", "Max", "Positive", "Negative" -> "RANGE";
            case "typeMismatch" -> "TYPE";
            default -> "INVALID";
        };
    }

    private static String publicMessage(String code) {
        return switch (code) {
            case "REQUIRED" -> "Field is required.";
            case "FORMAT" -> "Invalid format.";
            case "RANGE" -> "Value is out of the allowed range.";
            case "TYPE" -> "Invalid data type.";
            default -> "Invalid value.";
        };
    }

    private static ResponseEntity<ApiError> response(
            HttpStatus status,
            String code,
            List<FieldIssue> issues) {

        String errorId = UUID.randomUUID().toString();

        return ResponseEntity.status(status)
                .cacheControl(CacheControl.noStore())
                .body(new ApiError(
                        code,
                        "Request data is invalid.",
                        errorId,
                        issues));
    }
}
~~~

### 12.12. Security Review of the Code

1. Never calls getRejectedValue() or getDefaultMessage() when building responses.
2. Never returns MethodArgumentNotValidException, ObjectError, or FieldError directly in the body.
3. Field names are filtered through PUBLIC_FIELDS and a list-index pattern.
4. Internal error codes map to a fixed set of public codes.
5. Messages come from a static dictionary with zero input interpolation.
6. Global errors do not reflect Java objectName or exception messages.
7. Results are sorted, deduplicated, and capped at 20 to bound response bloat.
8. HTTP 400, 415, and 500 are distinguished per known exception types.
9. @ExceptionHandler does not catch generic Exception and convert it to 400.
10. Cache-Control: no-store reduces error body caching, though it does not replace CDN/proxy log policies or client-side storage hygiene.
11. errorId supports operational correlation **if** the system logs the same ID; the example generates an ID without configuring distributed tracing yet.
12. Does not echo the request body in successful responses.

**Intentional limitation:** For HandlerMethodValidationException, the project returns a generic request-level error so internal method parameter names do not need to be exposed. If per-field details are needed for method validation, use Spring Framework's visitor API, map each parameter to the public contract, and never echo rejected values. When an exception comes from return-value validation, it is a server bug so the handler returns 500 rather than blaming the client.

## 13. MockMvc Testing: Asserting Sensitive Data Absence

The most important test checks not just HTTP 400, but also verifies that **the response body contains none of the sensitive strings submitted**. Use dummy values with distinctive markers unlikely to collide accidentally.

File src/test/java/example/validation/CheckoutApiTests.java:

~~~java
package example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.hasItem;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CheckoutApiTests {

    @Autowired
    MockMvc mvc;

    @Test
    void nestedFieldErrorsDoNotEchoSensitiveValues()
            throws Exception {

        String sensitiveToken = "tok_PRIVATE_example_314";
        String sensitiveEmailInput = "private_input_not_an_email";
        String sensitiveZip = "private_bad_zip_314";

        String json = """
                {
                  "email":"private_input_not_an_email",
                  "paymentToken":"tok_PRIVATE_example_314",
                  "shipping":{
                    "city":"",
                    "postalCode":"private_bad_zip_314"
                  },
                  "items":[
                    {"sku":"","quantity":0}
                  ]
                }
                """;

        MvcResult result = mvc.perform(
                        post("/api/checkouts")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.errors[*].field",
                        hasItem("email")))
                .andExpect(jsonPath("$.errors[*].field",
                        hasItem("shipping.city")))
                .andExpect(jsonPath("$.errors[*].field",
                        hasItem("items[0].quantity")))
                .andReturn();

        String response = result.getResponse()
                .getContentAsString();

        assertFalse(response.contains(sensitiveToken));
        assertFalse(response.contains(sensitiveEmailInput));
        assertFalse(response.contains(sensitiveZip));
        assertFalse(response.contains("rejectedValue"));
        assertFalse(response.contains("stackTrace"));
        assertTrue(response.contains("errorId"));
    }

    @Test
    void validRequestDoesNotEchoPaymentToken()
            throws Exception {

        String json = """
                {
                  "email":"sample@example.test",
                  "paymentToken":"tok_PRIVATE_VALID_159",
                  "shipping":{
                    "city":"Da Nang",
                    "postalCode":"550000"
                  },
                  "items":[
                    {"sku":"BOOK-1","quantity":2}
                  ]
                }
                """;

        MvcResult result = mvc.perform(
                        post("/api/checkouts")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status")
                        .value("accepted"))
                .andReturn();

        String response = result.getResponse()
                .getContentAsString();

        assertFalse(response.contains("tok_PRIVATE_VALID_159"));
        assertFalse(response.contains("sample@example.test"));
    }

    @Test
    void malformedJsonHasOnlyGenericError()
            throws Exception {

        String broken = """
                {"email":"private_example",
                 "paymentToken":"tok_PRIVATE_42",
                 "shipping":
                """;

        MvcResult result = mvc.perform(
                        post("/api/checkouts")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(broken))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"))
                .andReturn();

        String response = result.getResponse()
                .getContentAsString();

        assertFalse(response.contains("tok_PRIVATE_42"));
        assertFalse(response.contains("private_example"));
    }

    @Test
    void unsupportedMediaTypeRetainsStatus415()
            throws Exception {

        mvc.perform(
                        post("/api/checkouts")
                                .contentType(MediaType.TEXT_PLAIN)
                                .content("secret-forbidden-input"))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code")
                        .value("UNSUPPORTED_MEDIA_TYPE"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

When run for real, the test suite must PASS to provide evidence that responses contain no markers. This lesson provides only source code and test expectations; it does not claim Gradle was executed in the current environment.

### 13.1. Why Test the Valid Response Too?

Data leaks do not occur only in error handlers. A controller might echo the request DTO on success, accidentally serializing paymentToken or internal fields. Testing valid requests confirms the response contains only intended public data.

### 13.2. Why Test Each Nested Field?

If you only test email, a list validator might still leak rejectedValue on items[0].sku. With nested collections, test child objects, list elements, and password/token fields alike.

## 14. Testing Real HTTP Responses and MockMvc Limitations

MockMvc verifies Spring MVC routing, validation, exception handlers, and serialization in a test application context, yet **does not open a real TCP port**. For risks involving reverse proxies, headers, and connector-level error handling, add integration tests using @SpringBootTest(webEnvironment = RANDOM_PORT) and a real HTTP client.

Levels:

- Unit tests for publicCode/publicField/publicMessage: fast, verify dictionaries/allowlists.
- @WebMvcTest: verifies the controller slice and imported advice.
- @SpringBootTest + @AutoConfigureMockMvc: verifies the web layer in a full context.
- @SpringBootTest(RANDOM_PORT): verifies real HTTP listeners/connectors.
- Staging tests through ingress/gateway: verify proxy caching, logging, WAF, and leaking headers.

For a security policy, helper unit tests alone are insufficient; **black-box HTTP tests** are needed to prove sensitive data is absent from bodies, headers, and key error paths.

## 15. Nested Paths and Lists: Don't Let Indexes Become an Information Leak Vector

Field paths like items[0].quantity help forms, yet can also leak list lengths or backend structure if overly detailed.

To reduce risk:

1. Support only documented public API field names.
2. Cap indexes, e.g., 0–999, and limit total returned errors.
3. For paths outside the allowlist, return field=request.
4. Never evaluate regexes over raw input without bounding length first.
5. Never expose arbitrary nested object names or inner class names.
6. If the API uses polymorphic fields, define explicit public path mappings per variant.
7. Ensure deterministic error ordering so frontends do not depend on Hibernate Validator order.

In multi-item forms, the frontend may need the index to highlight the right row. In that case, public indexes are part of the API contract; weigh the privacy tradeoff deliberately instead of hiding everything or emitting unbounded output.

## 16. Field-Level Errors vs. Query/Path Parameter Errors

Besides JSON bodies, an API can receive:

~~~http
GET /api/orders?page=abc&size=2000 HTTP/1.1
Host: localhost:8080
~~~

When page expects int, type conversion failures can raise MethodArgumentTypeMismatchException. When size has @Min/@Max, method validation can throw HandlerMethodValidationException on Spring Framework 6.1+.

Never take exception.getValue(), raw query strings, or exception messages and send them to clients. Define a public code such as INVALID_PARAMETER, an allowlist of fields like page/size, and a static message "Invalid parameter." If no trusted public mapping exists, return field=request.

Path variables can also carry sensitive data; avoid printing raw URLs into responses, logs, or metric labels. For legacy URLs carrying tokens, redesign so tokens are not placed in paths/queries whenever possible.

## 17. Error Messages and i18n

Frontends often require multiple languages. A safe approach is mapping public codes through a dictionary:

~~~properties
validation.REQUIRED=Field is required.
validation.FORMAT=Invalid format.
validation.RANGE=Value is out of the allowed range.
validation.TYPE=Invalid data type.
validation.INVALID=Invalid value.
~~~

This is an **example messages.properties file** for an i18n strategy, not a file required inside the demo project to run. In production, MessageSource can select the right language, provided you:

- Resolve keys from fixed public codes.
- Never interpolate rejectedValue or raw exception parameters.
- Restrict allowed/available Locales with a safe fallback.
- Never let clients pass expression templates to evaluate against input.
- Test translations to confirm they contain no user input values.

To let clients display UI-tailored text, you can also return codes alone and let the frontend maintain its own dictionary. In that case, codes must remain stable and versioned.

## 18. ProblemDetail and RFC 9457

Spring Framework 6.x supports ProblemDetail, ErrorResponse, and ResponseEntityExceptionHandler to standardize HTTP errors per RFC 9457. You can use type/title/status/detail/instance and extend properties with a sanitized list of field errors.

Illustrative structure:

~~~json
{
  "type": "https://example.org/problems/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "Request validation failed",
  "errorId": "c8b3913d-5ea7-4a6e-85ed-f2b24fc75ef0",
  "errors": [
    {
      "field": "shipping.city",
      "code": "REQUIRED"
    }
  ]
}
~~~

Do not assume ProblemDetail or ResponseEntityExceptionHandler automatically guarantees security. If detail includes raw exception messages, or extensions contain rejectedValue, the response still leaks data. Filter data before putting it into ProblemDetail.

**Schema choice:** a custom ApiError as in the sample project or ProblemDetail are both valid; consistency with your API contract and leak testing are what matter.

## 19. WebFlux: Same Principles, Different Exception Types

In Spring WebFlux annotated controllers, binding validation for @Valid @RequestBody typically raises WebExchangeBindException; method validation can raise HandlerMethodValidationException. With WebFlux.fn, bodyToMono(Dto.class) primarily decodes, so you must invoke Validator.validate(...) explicitly to validate the DTO; MVC exception handlers cannot be copied verbatim into WebFlux.fn.

Illustrative WebFlux.fn handler snippet:

~~~java
return request.bodyToMono(CreateCheckoutRequest.class)
        .flatMap(dto -> {
            Set<ConstraintViolation<CreateCheckoutRequest>> violations =
                    validator.validate(dto);

            if (!violations.isEmpty()) {
                return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(sanitizeViolations(violations));
            }

            return service.process(dto)
                    .flatMap(result -> ServerResponse.ok()
                            .bodyValue(result));
        });
~~~

This snippet requires a real CreateCheckoutRequest, validator, sanitizeViolations, and service. It is **not a standalone source file**. sanitizeViolations must emit only public fields/codes/messages; never read ConstraintViolation.getInvalidValue() or ConstraintViolation.getMessage() unchecked.

Similarly, WebExchangeBindException exposes field errors conceptually like BindingResult, yet responses must be built with reactive-friendly mechanisms. When handling JSON decoder errors such as ServerWebInputException, never emit raw causes or Jackson messages.

### 19.1. Why Not Share the Exact Same Advice for MVC and WebFlux?

- Exception classes and threading/request models differ.
- Reactor Context is not Servlet ThreadLocal request context.
- MVC uses HttpMessageConverter for @RequestBody; WebFlux uses reactive codecs.
- WebFlux.fn lacks the @Valid parameter resolver of annotated controllers.
- HTTP responses have a reactive lifecycle, so never block()/subscribe() manually when creating error responses.

You can share the **ApiError schema, field allowlist, and public-code dictionary** in a common library, while giving each web stack its own exception-handling adapter.

## 20. Security, Privacy, and Error Logging

### 20.1. HTTP Responses Are Not the Only Leak Point

Data can leak into:

- Servlet access logs (especially query strings).
- Application logs if logging request DTO.toString().
- APM/tracing tags if recording raw request bodies, headers, or URLs.
- HTTP reverse proxy/WAF logs.
- Error tracking software automatically capturing exception context.
- Browser consoles, analytics, and screenshots.
- HTTP response caches in proxies/clients.
- Uncontrolled dead-letter queues or event payloads.

Even when ApiError is sanitized, a global filter enabling request/response body logging can still expose tokens. Audit the entire pipeline.

### 20.2. Minimal Logging

A safe log event might record:

~~~text
event=request_validation_failed errorId=<uuid> route=/api/checkouts status=400 code=VALIDATION_FAILED count=4
~~~

Never log email, paymentToken, raw body, rejectedValue, or stack traces for normal 4xx input errors. For 5xx errors, internal stack traces may be logged per security policy without sending them to clients.

The example project generates errorId without logging it yet. For real correlation, log the same errorId and, if distributed tracing is enabled, tie it to infrastructure-generated traceId/spanId rather than trusting client-supplied headers.

### 20.3. Caches and Proxies

Cache-Control: no-store is a sensible defense for error responses carrying request metadata, yet does not guarantee proxies/SDKs purge logged copies. Audit reverse proxy/CDN configurations and observability tools.

### 20.4. Privacy Under System Policies

Input data may be subject to internal policies or applicable data protection laws. Follow retention, access controls, consent/lawful basis, and data minimization requirements for your context. Sanitization reduces risk, though it does not by itself confer legal compliance.

## 21. Limiting Excessive Errors and Resource Exhaustion Attacks

A client can submit a request with 50,000 items, each failing multiple rules. Building/serializing every FieldError wastes CPU/memory and can expose structure.

Defense layers:

1. Limit request body size at proxies/servers and the web framework.
2. Limit collection lengths, nesting depth, and field lengths before or during validation per contract.
3. Cap public errors, e.g., maximum 20.
4. Sort/deduplicate for deterministic responses.
5. Apply rate limits/throttling to endpoints abused with error spam.
6. Cap field path count and message lengths.
7. Never log every error and raw value of oversized requests.
8. Emit aggregated metrics (counts/rates) without raw input as labels.
9. Never turn normal 4xx errors into massive stack-trace logs on every request.

Capping returned errors **does not automatically limit how many constraint violations the validator computes**. To defend against huge payloads, reject oversized data earlier before deserializing and validating everything.

## 22. Avoiding Leaks Through Custom Validation Messages

Built-in annotations have fairly generic defaultMessages, yet a custom constraint might build a message like:

~~~java
context.buildConstraintViolationWithTemplate(
        "Value " + inputValue + " is not accepted")
        .addConstraintViolation();
~~~

This snippet illustrates an **unsafe design**; it requires the variables/context of a real ConstraintValidator. If an error handler returns getDefaultMessage() to the client, inputValue is immediately leaked.

Instead of embedding values in messages:

- Custom validators should emit a stable code, e.g., FORMAT_INVALID.
- The public error handler maps codes to static sentences.
- Log sanitized metadata to track error types.
- If the frontend needs bounds such as min/max for display, expose only **allowlisted non-sensitive configuration parameters**, never user-supplied input.
- Test with marker secrets to catch unintended template interpolation.

Never assume getDefaultMessage() is safe across all teams, since different developers may author validators over time.

## 23. Avoiding User Enumeration and Authorization Logic Leaks

Even a response with no rejectedValue can leak data through **differences in error codes or messages**.

Examples:

- "This email already exists" returned only when a user has an account.
- "Incorrect recovery code" vs. "Account does not exist".
- "This card number belongs to another user" revealing account linkage.
- "You lack permission for tenant X" revealing an internal tenant.

For sensitive endpoints, uniform statuses/messages, rate limiting, and timing policies may be needed to prevent enumeration. That depends on your threat model; do not apply verbose field-level error rules to login, recovery, or authorization endpoints.

A normal API may report that an email field has an invalid format, without confirming whether that email is registered. Distinguish **format validation** from **identity verification or account existence**.

## 24. Common Mistakes

| Mistake | Risk | Fix |
| --- | --- | --- |
| Returning FieldError directly | Leaks rejectedValue, codes, objectName | Map to public FieldIssue |
| Returning getRejectedValue() | Leaks tokens/PII | Never echo input |
| Returning getDefaultMessage() unconditionally | Custom validators may embed values | Static public-code dictionary |
| Returning exception.getMessage() | Leaks JSON fragments/classes/paths | Return a generic message |
| Returning the request DTO on validation failure | Leaks all fields | Construct an independent ApiError |
| Returning stackTrace for frontend debugging | Leaks internals | Log internally with access control only |
| Exposing raw field paths | Leaks backend property names | Allowlist public fields |
| Unbounded error lists | Response bloat, overload | Limit/sort/dedup |
| Advice catching Exception -> 400 | Hides server bugs | Classify exceptions and statuses |
| Forcing 415 into INVALID_JSON 400 | Breaks media type contract | Preserve 415 |
| Returning ConstraintViolation.getInvalidValue() | Leaks nested data | Never read invalidValue |
| Logging raw request bodies | Data still leaks via logs | Redact/disable raw-body logging |
| Generating errorId without logging it | Hard to investigate | Tie to logs/traces per policy |
| Testing only HTTP status 400 | Misses echoed secrets | Assert absence of markers |
| Missing cascade @Valid | Skips nested errors | Place @Valid on objects/list elements |
| Testing only one top-level field | Misses nested list leaks | Test shipping/items/missing/null |
| Mixing 422/400 inconsistently | Hard for clients to handle | Define one unified API contract |
| Overly detailed login error responses | User enumeration | Generic errors and rate limits |

## 25. Pre-Production Review Checklist

An API validation response is far more trustworthy when it meets these checks:

- [ ] Every endpoint has a documented request DTO and public fields.
- [ ] No serializer receives raw BindingResult/FieldError/ObjectError in error responses.
- [ ] rejectedValue/invalidValue never appear in responses or public logs.
- [ ] getDefaultMessage/exception.getMessage are never sent directly to clients.
- [ ] Public error codes and messages come strictly from allowlists/dictionaries.
- [ ] Nested field paths are allowlisted, index-bounded, and capped in error count.
- [ ] 400/401/403/404/409/413/415/5xx are distinguished per contract.
- [ ] Method validation and JSON decoding errors have safe fallbacks.
- [ ] Responses contain no raw request, email, token, password, or address markers.
- [ ] Success responses also never echo credentials accidentally.
- [ ] Proxies/CDNs/ingress and observability tools do not log sensitive requests/responses.
- [ ] Rate limits and payload size constraints protect against validation abuse.
- [ ] errorId/log correlation actually works with safe trace/metadata.
- [ ] Regression tests cover top-level, nested, list, and malformed JSON errors.
- [ ] If using ProblemDetail, all extension properties are sanitized.
- [ ] If using i18n, templates never interpolate raw input.
- [ ] Security review covers user enumeration, not only body contents.

No checklist replaces threat modeling and testing in real deployments, yet these items establish a crisp technical boundary between request data and publicly disclosable information.

## 26. Comprehensive Practice Exercises

**Exercise 1 — Test nested errors:** Use the section 12 project. Send a dummy paymentToken, invalid email, blank shipping.city, and items[0].quantity=0. Capture the status, field list, and verify no token/email/zip markers appear in the response.

**Exercise 2 — Non-public field name:** Add an internal field used only during validation and intentionally trigger a FieldError; verify publicField returns request instead of the internal name.

**Exercise 3 — Swap messages:** Create a custom constraint embedding dummy input in its message and verify the handler still returns only static dictionary messages. Then fix the constraint so it never embeds input values internally either.

**Exercise 4 — Error cap:** Send a request with many invalid list elements; verify at most 20 errors are returned without exceeding the body-size budget. Distinguish response caps from payload validation limits.

**Exercise 5 — Malformed JSON:** Send syntax-broken JSON, an invalid enum, contentType text/plain, and an oversized body. Compare HTTP 400/415/413; if the environment behaves differently, adjust layer mapping properly.

**Exercise 6 — Query validation:** Add a GET endpoint with @Min/@Max on parameters and verify HandlerMethodValidationException behavior; ensure rejected parameter values are not echoed.

**Exercise 7 — ProblemDetail:** Replace ApiError with RFC 9457 ProblemDetail, attach sanitized errors, and test that JSON contains no raw exception messages.

**Exercise 8 — WebFlux:** Write an equivalent endpoint using a WebFlux annotated controller or WebFlux.fn, handling WebExchangeBindException/Validator properly while keeping the same public error contract.

**Exercise 9 — Logs:** Inspect gateway, tracing, and application logs when sending sensitive markers; ensure markers never appear in any operational log output.

**Exercise 10 — Deployment verification:** Run on staging with real HTTP integration tests, recording Spring Boot version, standard error bodies, rate-limiting policies, and behavior when older clients send extra fields.

Complete when you have source code, passing tests, real HTTP responses, and a verified non-leakage check. Never report tests as passing without running the test command in the target environment.

## 27. Self-Assessment Questions

1. What categories of sensitive data can FieldError.getRejectedValue() contain?
2. Why is getDefaultMessage() not safe by default?
3. At which layer do JSON mapping errors and Bean Validation differ?
4. When does MethodArgumentNotValidException occur in MVC?
5. What scenario does HandlerMethodValidationException relate to?
6. Why must method return-value validation errors be distinguished from client errors?
7. When should an error be returned under field=request instead of a specific path?
8. Why must field paths—especially nested arrays—be allowlisted?
9. How should response codes and messages stay stable when changing validator implementations?
10. Why is asserting only HTTP status 400 insufficient?
11. Why must success responses with paymentToken also be tested?
12. Does Cache-Control: no-store completely stop data leakage through logs?
13. How does a 415 error differ from a 400 error?
14. Why shouldn't catch(Exception) turn every exception into a validation failure?
15. Does ProblemDetail automatically sanitize extension properties?
16. If a custom validator embeds input values into its message, how should the response layer handle it?
17. What can returning "email already exists" reveal even without echoing the email?
18. When does WebFlux require WebExchangeBindException instead of MVC advice?
19. Why is WebFlux.fn bodyToMono insufficient to replace explicit validation?
20. If a list contains thousands of invalid items, at which layers must resources be protected?
21. How does errorId differ from traceId, and should they be linked?
22. How can you protect response bodies, headers, app logs, and reverse proxy logs together?

## 28. Official Documentation

- [Spring Framework 6.1 — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-validation.html): @Valid, binding, MethodArgumentNotValidException, and method validation.
- [Spring Framework — MVC Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ErrorResponse, ProblemDetail, ResponseEntityExceptionHandler, and MessageSource.
- [Spring Framework — Controller Advice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html): @RestControllerAdvice and @ExceptionHandler.
- [Spring Framework — BindingResult API](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/validation/BindingResult.html): field/global errors and rejected-value risks.
- [Spring Framework — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): WebExchangeBindException and HandlerMethodValidationException.
- [Spring Boot 3.3 — Validation](https://docs.spring.io/spring-boot/3.3/reference/io/validation.html): Jakarta Bean Validation integration.
- [Jakarta Bean Validation 3.0](https://jakarta.ee/specifications/bean-validation/3.0/): constraints, cascaded validation, and property paths.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): consistent error representation pattern.

**Conclusion:** field-level error responses are a public API contract, not a raw dump of BindingResult. Read validation metadata from the framework, **emit only approved field paths/codes/messages**, strip all rejected input, bound sizes, and test for non-leakage. Keeping this boundary crisp makes the API both helpful for frontends and far safer against data exposure.
