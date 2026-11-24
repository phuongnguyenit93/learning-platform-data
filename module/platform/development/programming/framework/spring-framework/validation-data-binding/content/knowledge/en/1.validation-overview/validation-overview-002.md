# What is validation and its role in protecting the data contract

Validation is the process of checking data against published rules before the system uses that data. In a Spring Framework application, validation is part of the **data contract** between the sender and the receiver: the receiver specifies which information is required, which formats and value ranges are allowed, and what happens when a request violates the contract.

For example, an account registration API may require the name to be 2–60 characters, the email to have a valid format, and the age to be at least 18. Without validation, a request missing an age or containing an invalid value could slip into the business layer, causing confusing errors or persisting corrupted data to the database. Validation helps detect violations early and return structured error information.

## 1. What does a data contract protect?

A data contract is not just a list of properties on a Java class. It also describes the meaning and invariants the system promises to uphold.

| Contract component | Question to answer | Example |
| --- | --- | --- |
| Presence | Is the field required? | `age` must not be `null` |
| Type and convertibility | Can the value be represented as the right type? | `age` must be an integer |
| Format | Does the string match the required pattern? | `email` has an email format |
| Length and value range | What range are allowed values within? | Name 2–60 characters long; age ≥ 18 |
| Cross-field relationship | Are the values consistent with each other? | `startDate` is no later than `endDate` |
| Contextual rule | Is the data valid at the time of the operation? | Do not register a duplicate email already in use |
| Failure response | How will the sender know how to fix the request? | HTTP 400 and list of violated fields |

From an API design perspective, the contract must be clear enough for clients to construct valid data, for the backend to protect business assumptions, and for tests to verify both valid and invalid cases. Merely declaring a Java type, such as `String email`, does not by itself establish requiredness or maximum length.

**Validation is not synonymous with:**

- **Parsing/deserialization:** reading JSON or converting strings into numbers, dates, or enums. Syntactically invalid JSON may be rejected before Bean Validation runs.
- **Data binding:** assigning input data into a Java object or properties. Binding may report type-conversion errors; validation checks constraints on the resulting object.
- **Normalization/sanitization:** trimming whitespace, changing case, or cleaning content. These transformations require an explicit policy and must not silently alter the meaning of data.
- **Authorization:** checking whether a user has permission to perform the action or modify that resource.
- **SQL injection/XSS protection:** parameterized queries, context-appropriate output encoding, and dedicated security mechanisms are still required.

In other words, data that "passes validation" only proves it satisfies **the conditions that were checked**, not that it is safe in every context or that every business rule has been satisfied.

## 2. Where does validation sit in the Spring processing flow?

For a REST endpoint receiving JSON in Spring MVC, the general flow is:

~~~text
HTTP request
    |
    v
Read HTTP body and deserialize JSON (@RequestBody / HttpMessageConverter)
    |
    v
Create request DTO object
    |
    v
Check constraints (@Valid, @Validated, method validation if applicable)
    |
    +---- Invalid ---> Return handleable error, typically HTTP 400
    |
    v
Controller -> Service -> data access layer -> Database
~~~

The actual flow depends on parameter types, configuration, and which validation mechanism is activated. For form/query data bound with `@ModelAttribute`, Spring uses data binding; binding and validation results can be collected via `BindingResult`. With `@RequestBody`, JSON is typically converted into an object before constraints on the object are checked.

Defense layers reinforce each other:

1. **HTTP/controller boundary:** rejects malformed shapes, missing required fields, and invalid values; helps the API return consistent errors before invoking business logic.
2. **Service/domain:** checks rules that depend on state or multiple resources, such as booking quotas or state-transition permissions.
3. **Persistence/database:** `NOT NULL`, `CHECK`, `FOREIGN KEY`, and `UNIQUE` constraints ensure integrity on write, even when data arrives from jobs, queues, or other flows.
4. **Non-HTTP consumers:** must trigger validation at their respective entry points; annotations on a DTO do not automatically cause every object to be validated whenever instantiated.

Boundary validation catches errors early, but does not replace business checks or database constraints. For example, merely checking "email does not exist yet" in a controller still leaves a race condition when two concurrent requests create the same email; a `UNIQUE` constraint in the database is the final line of defense.

## 3. Which mechanisms does Spring provide?

### 3.1. Jakarta Bean Validation

Spring Framework supports the **Jakarta Bean Validation** standard. You declare rules with annotations on fields, properties, record components, or parameters as appropriate; a provider such as Hibernate Validator executes those rules. With Spring Boot 3.x, typically add dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Imports use the `jakarta.validation.*` namespace. Older Spring Boot 2.x documentation may use `javax.validation.*`; do not mix the two namespaces when working with Boot 3.x.

| Constraint | Main meaning | Note |
| --- | --- | --- |
| `@NotNull` | Value is not `null` | Does not forbid empty strings or whitespace-only strings |
| `@NotEmpty` | String/collection/array/map is non-empty and non-null | A string containing only spaces can still pass |
| `@NotBlank` | String is non-null and has at least one non-whitespace character | Suitable for required names and descriptions |
| `@Size(min, max)` | Limits length/size | Do not use to check the range of a number |
| `@Min` / `@Max` | Limits numeric value | Combine with `@NotNull` if the value is required |
| `@Positive` / `@PositiveOrZero` | Positive number / non-negative number | Choose according to the specific contract |
| `@Email` | Checks email format according to the validator | Does not verify that the mailbox exists or can receive mail |
| `@Pattern(regexp = ...)` | String matches regular expression | Does not replace a parser for complex data structures |
| `@Past` / `@Future` | Temporal value is in the past/future | Must consider time zone and evaluation instant |

Most content-checking constraints like `@Email`, `@Size`, or `@Min` allow `null`. If a field is required, add `@NotNull` or a null-forbidding constraint like `@NotBlank`. That way, "required" and "valid when present" are declared independently and clearly.

### 3.2. `@Valid`, `@Validated`, and actually triggering checks

- `@Valid` is the standard Jakarta annotation used to request validating an object and cascading into nested objects marked `@Valid`. On a controller DTO parameter, it is the standard way to trigger request validation.
- `@Validated` is Spring's annotation supporting **validation groups** and is used in some Spring method validation mechanisms. If groups are not needed, most simple DTO cases only need `@Valid`.
- Constraints directly on **method parameters or return values** fall under method validation, which has different execution and exceptions from validating a DTO.
- Simply placing `@NotBlank` on a field without a corresponding validator invocation does not guarantee any check will occur.

In Spring MVC since Framework 6.1, the built-in method validation mechanism can handle constraints placed directly on method parameters. When it does, errors usually surface via `HandlerMethodValidationException`; whereas validating a single `@Valid @RequestBody` DTO usually produces `MethodArgumentNotValidException`. You must choose exception handling according to the mechanism actually triggered, and note that `@Validated` at the controller class level may use an AOP mechanism distinct from built-in MVC support.

Spring also has the `org.springframework.validation.Validator`, `Errors`, `BindingResult`, and `DataBinder` interfaces. These are Spring's validation/binding APIs; `LocalValidatorFactoryBean` can act as an adapter between them and Jakarta Bean Validation. Both approaches can work together, but you must distinguish `org.springframework.validation.Validator` from `jakarta.validation.Validator`.

## 4. Example: protecting a registration contract

Suppose an endpoint only validates a registration request, **without persisting data**. Rules: name 2–60 characters, email required and well-formed, age 18 or older. The classes below use Java 17+, Spring Boot 3.x (Spring Framework 6.x), and the two dependencies from Section 3.

Create `src/main/java/com/example/validationdemo/ValidationDemoApplication.java`:

~~~java
package com.example.validationdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }
}
~~~

Create `src/main/java/com/example/validationdemo/RegistrationRequest.java`:

~~~java
package com.example.validationdemo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record RegistrationRequest(
        @NotBlank(message = "Name is required")
        @Size(min = 2, max = 60, message = "Name must be between 2 and 60 characters")
        String name,

        @NotBlank(message = "Email is required")
        @Email(message = "Invalid email format")
        String email,

        @NotNull(message = "Age is required")
        @Min(value = 18, message = "Minimum age is 18")
        Integer age
) {}
~~~

Create `src/main/java/com/example/validationdemo/RegistrationController.java`:

~~~java
package com.example.validationdemo;

import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @PostMapping("/check")
    public Map<String, String> check(@Valid @RequestBody RegistrationRequest request) {
        return Map.of("status", "accepted", "email", request.email());
    }
}
~~~

These classes are complete Java code within **a Spring Boot project configured with the appropriate plugins, Java toolchain, and dependencies**. Run the application with `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). When `@Valid` is placed on the `@RequestBody` parameter, Spring instructs the validator to check the DTO before invoking the method body. The `RegistrationRequest` object only returns "accepted" in this example; it is **not** confirmation that an account has been successfully registered.

Send a valid request:

~~~http
POST /registrations/check HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"name":"An","email":"an@example.com","age":21}
~~~

Result: HTTP 200; the JSON response has `status` as `"accepted"` and `email` as `"an@example.com"`. JSON key order is not part of the contract in this example.

Send a request violating all three conditions at once:

~~~http
POST /registrations/check HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"name":" ","email":"not-an-email","age":16}
~~~

Result: typically HTTP 400 in Spring MVC, without entering the `check(...)` body. The corresponding errors include blank name, malformed email, and age under 18. **The default error body is not fixed**: it depends on the Spring Boot version, Problem Details settings, and the application's exception handler; do not write tests depending on an error JSON structure you have not defined.

To define your application's own API error contract, you can add `src/main/java/com/example/validationdemo/ValidationErrorHandler.java`:

~~~java
package com.example.validationdemo;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationErrorHandler {

    public record FieldIssue(String field, String message) {}

    public record ErrorPayload(String code, List<FieldIssue> errors) {}

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorPayload> onInvalidRequest(
            MethodArgumentNotValidException exception) {

        List<FieldIssue> errors = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(), error.getDefaultMessage()))
                .toList();

        return ResponseEntity.badRequest()
                .body(new ErrorPayload("VALIDATION_FAILED", errors));
    }
}
~~~

When the error is of type `MethodArgumentNotValidException`, the handler above returns JSON in the form:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "age", "message": "Minimum age is 18"}
  ]
}
~~~

This is an **example of the data shape**, not a claim that a three-error request will only have one error or always appear in this order. In a real system, standardize error codes, client messages, localization, and correlation IDs; do not include stack traces, internal details, or sensitive values in responses. The handler above only handles one exception type; parse/binding errors and method validation need corresponding handling if they should share the same format.

## 5. Why are there multiple kinds of "bad requests"?

| Case | Where commonly detected | Handling approach |
| --- | --- | --- |
| JSON missing a brace, or `age` is a string that cannot convert to `Integer` | HTTP message conversion, typically `HttpMessageNotReadableException` | HTTP 400; report invalid body/syntax |
| DTO deserialized but `name` is blank or `age < 18` | Bean Validation on `@Valid @RequestBody`, typically `MethodArgumentNotValidException` | HTTP 400; return list of violations |
| `@ModelAttribute` form has field binding/validation errors | `BindingResult`/`Errors` if declared immediately after the bound parameter | Controller can handle errors itself |
| Constraint on method parameter, e.g., `@RequestParam @Min(18)` | Spring MVC method validation (Framework 6.1+), typically `HandlerMethodValidationException` | Classify input errors and return appropriate response |
| Email already registered or state-conflicting operation | Service/domain and/or DB constraint | Choose response per business contract, typically HTTP 409 for conflict |
| Caller lacks permission | Security/authorization layer | HTTP 401 or 403 depending on situation |

In some API designs, semantic errors may use HTTP 422 instead of 400, but there must be a consistent policy. Do not lump everything into "validation failed", because clients need to distinguish bad data, business conflicts, and missing permissions.

If you want to handle form errors explicitly, `BindingResult` must stand **immediately after** the bound/validated object, for example:

~~~java
@PostMapping("/profiles")
public String saveProfile(
        @Valid @ModelAttribute ProfileForm form,
        BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "profile-form";
    }
    return "profile-success";
}
~~~

The snippet above illustrates the **controller signature**, assuming a `ProfileForm` class and corresponding views already exist; it is not a standalone program. Once `BindingResult` is accepted, the code must actually handle errors. Do not treat Spring not throwing an exception as meaning the data is valid.

## 6. Choosing the right constraint location and scope

**Input DTOs are the contract boundary.** Prefer a request DTO with only allowed fields, rather than binding clients directly to a persistence entity containing `id`, `role`, `status`, or internal fields. This helps prevent unintended updates (mass assignment) and keeps the API more independent of storage schemas.

**Distinguish creation from updates.** Creation may require an email, whereas PATCH may allow omitting the email. Do not blindly reuse the same `@NotNull` for both requests. Use separate DTOs for create/update or intentional validation groups; clearly distinguish "field omitted" from "null sent" when defining PATCH.

**Nested objects need cascading when required.** For example, if `RegistrationRequest` contains `AddressRequest address`, constraints on `AddressRequest` are only checked along that path when an appropriate `@Valid` cascade is declared. Combine with `@NotNull` if the `address` attribute itself is required: `@Valid` does not mean "non-null".

**Cross-field checks and dynamic state need dedicated design.** A `startDate <= endDate` condition can live in a class-level custom constraint or domain service. "Email does not exist yet" is a rule that changes with system state: verify it in the service, combined with a unique constraint in the database to withstand concurrent access. Avoid creating validators that arbitrarily query the database for every DTO and treating that as a replacement for transactions and data-integrity mechanisms.

**Keep the contract stable and observable.** Standardize error codes, log enough for diagnostics without arbitrarily logging passwords/tokens/PII. User-facing messages can be localized; error codes remain stable for programmatic client handling. When changing constraints, review backward compatibility because older clients may send values that were previously accepted.

## 7. What should tests prove?

An HTTP or controller test suite should cover at least the following scenarios:

| Input data | Expectation |
| --- | --- |
| `name="An"`, valid email format, `age=21` | Success (200 on the sample check endpoint) |
| Missing `name` or `name="  "` | Rejected due to `@NotBlank` |
| `name` only one character | Rejected due to `@Size(min=2)` |
| Missing `email` or malformed email | Rejected by the corresponding constraint |
| Missing `age` or `age=17` | Rejected due to `@NotNull` or `@Min` |
| `age="abc"` or invalid JSON | Rejected at data conversion step before Bean Validation |
| Multiple fields violated together | All errors observable, independent of list order |
| Valid request shape violating dynamic rule | Service/DB still rejects according to business rules |

With Spring Boot, you can use `MockMvc` to verify the HTTP status and error content returned by **the application's handler**. In addition, service and database tests are needed for business rules; a 400 controller test does not prove integrity under multiple writers or concurrent access.

## 8. Common mistakes

1. **Forgetting the validator dependency.** Having `@Valid` and constraint annotations without a compatible provider leads to unmet validation expectations.
2. **Confusing annotations with execution.** Instantiating a DTO with `new` does not automatically run Bean Validation; you must call `jakarta.validation.Validator` or pass through an integration point with validation enabled.
3. **Using the wrong constraint.** `@NotNull` does not reject empty strings; `@Size` does not check numeric values; `@Email` does not guarantee an email address actually works.
4. **Using primitives for fields where "missing" has meaning.** `int` cannot represent null; for requests with optional or required fields needing to distinguish missing values, consider `Integer` and `@NotNull`.
5. **Not cascading validation for nested data.** Constraints on child objects can be skipped because `@Valid` is missing at the appropriate link.
6. **Validating only in the controller.** Imports, scheduled jobs, message consumers, or internal operations can bypass controllers; the service and database must still enforce key invariants.
7. **Returning vague errors or leaking internal details.** Clients need to know which field and rule failed, not stack traces, SQL statements, or sensitive data.
8. **Treating valid data as authorized.** Validation does not prove the principal may modify a resource, nor does it eliminate the need for transactions or write-concurrency protection.

## 9. Self-check questions

- How does a request with syntactically invalid JSON differ from a valid JSON request that violates `@NotBlank`?
- Why do we often have to combine `@NotNull` with `@Min`?
- How does `@Valid` differ from `@Validated`, and when is method validation needed?
- Why does "email does not exist yet" require both the service and a unique constraint in the database?
- If the same DTO enters both a controller and a message consumer, where is validation actually triggered?
- What information should an API return so clients can fix data without exposing internal details?

**Remember:** The data contract defines what the system accepts; validation enforces checkable constraints at appropriate boundaries; business logic, authorization, and the database continue protecting invariants beyond a single DTO. A reliable Spring application needs all three layers: **a clear contract, validation at ingestion points, and integrity protection when using/storing data**.

### References

- Spring Framework — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Java Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
