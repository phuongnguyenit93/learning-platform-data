# Customizing BindingErrorProcessor for a custom error contract

## 1. Problem statement and goal

In a Spring MVC API, a request might submit a form such as `age=abc` even though the Java property is `Integer age`. Spring attempts to convert `"abc"` into a number and records a binding error in `BindingResult`. Another request might omit the required field `email`. By default, Spring uses codes such as `required` and `typeMismatch`, which fit generic error-rendering flows.

However, a system with a custom **error contract** may specify client-facing codes:

| Scenario | Desired API error code |
| --- | --- |
| Missing required field during property binding | `INPUT_REQUIRED` |
| Cannot convert value to target type | `INPUT_TYPE` |
| Cannot assign property due to another error | `INPUT_PROPERTY` |
| Data bound successfully yet fails business rules | `VALIDATION_FAILED` |

Error codes must stay stable across releases and remain independent of display language. In such cases, you may customize **`org.springframework.validation.BindingErrorProcessor`**: the strategy interface that decides **how errors are recorded in `BindingResult`** when a required field is missing or a `PropertyAccessException` occurs.

This lesson walks through choosing the right extension point, implementing the processor, registering it on `DataBinder`/`WebDataBinder`, preserving error metadata, testing the contract, and distinguishing it from validation and JSON parsing. Examples use **Java 17+ and Spring Framework 6.2.x**. The Spring MVC section fits a Spring Boot 3.x project with Spring Web.

## 2. Where does BindingErrorProcessor sit in the binding lifecycle?

For a mutable JavaBean and `DataBinder.bind(PropertyValues)`, the overall flow is:

~~~text
Form/query parameters or PropertyValues
                 |
                 v
             DataBinder
                 |
       allowedFields / requiredFields
                 |
          +------+-------+
          |              |
   Missing field?  Assign property values
          |              |
          |        Convert type / call setter
          |              |
          |        PropertyAccessException?
          |              |
          v              v
processMissing...   processPropertyAccessException(...)
          |              |
          +------+-------+
                 |
                 v
            BindingResult
       FieldError / ObjectError
                 |
                 v
      Controller / API response
~~~

Under `DefaultBindingErrorProcessor`, Spring typically uses base codes:

- `required`: required field is missing.
- `typeMismatch`: value cannot convert to the property type.
- `methodInvocation`: invoking the setter/method failed.

A base code can be expanded into multiple candidates such as `typeMismatch.registration.age`, `typeMismatch.age`, and `typeMismatch` via `MessageCodesResolver`. This lets the application resolve tailored messages by object and field.

**Scope limitation:** `BindingErrorProcessor` does not handle all HTTP 400 errors. It does not directly process malformed JSON in `@RequestBody`, authentication exceptions, authorization errors, or constraints produced by Jakarta Bean Validation. Those follow separate mechanisms.

## 3. Interface and metadata to preserve

`BindingErrorProcessor` has two primary callbacks:

~~~java
void processMissingFieldError(
        String missingField,
        BindingResult bindingResult);

void processPropertyAccessException(
        PropertyAccessException exception,
        BindingResult bindingResult);
~~~

The snippet above shows API signatures, **not a standalone Java file**.

- `processMissingFieldError` receives the field name identified by `DataBinder` as missing based on `setRequiredFields(...)`.
- `processPropertyAccessException` receives the failure raised while accessing or assigning a property.
- Both receive `BindingResult` to add a `FieldError` or `ObjectError`. The implementation chooses the codes, rejected value, message, and error type.

Key attributes of a `FieldError`:

| Attribute | Meaning |
| --- | --- |
| `objectName` | Name of the model attribute, e.g. `registration` |
| `field` | Offending property, e.g. `age` |
| `rejectedValue` | Rejected input value, if retained |
| `bindingFailure` | `true` if the error occurred during binding |
| `codes` | Candidate code list for `MessageSource` lookup |
| `defaultMessage` | Fallback message |

Changing the error code while keeping the related metadata lets Spring MVC, template rendering, and error-checking utilities keep working. For instance, a controller can still call `result.hasFieldErrors("age")` even after the code changes to `INPUT_TYPE`.

**Avoid silently ignoring callbacks**: if the processor records no error, the controller may observe `hasErrors() == false` and process an invalid object.

## 4. Design the contract before coding

Suppose an endpoint accepts a form with `email` and `age`:

- Missing `email`: code `INPUT_REQUIRED`.
- `age=abc`: code `INPUT_TYPE`.
- Property assignment exception other than conversion: `INPUT_PROPERTY`.
- HTTP 400 body exposes only `field`, `code`, and `message`; never leak rejected values or stack traces.
- Codes remain stable, while messages can be localized across locales.
- Business validation (such as `age >= 18`) is handled separately by a validator.

Sample contract JSON:

~~~json
{
  "errors": [
    {
      "field": "email",
      "code": "INPUT_REQUIRED",
      "message": "Invalid input data"
    },
    {
      "field": "age",
      "code": "INPUT_TYPE",
      "message": "Invalid input data"
    }
  ]
}
~~~

This is an **application-chosen API contract**, not a default body provided by Spring. Clients should not depend on the ordering of two errors; if ordering is part of the contract, specify and test it explicitly.

## 5. Writing ApiBindingErrorProcessor

File `src/main/java/demo/ApiBindingErrorProcessor.java`:

~~~java
package demo;

import org.springframework.beans.PropertyAccessException;
import org.springframework.validation.BindingErrorProcessor;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

public final class ApiBindingErrorProcessor
        implements BindingErrorProcessor {

    public static final String INPUT_REQUIRED = "INPUT_REQUIRED";
    public static final String INPUT_TYPE = "INPUT_TYPE";
    public static final String INPUT_PROPERTY = "INPUT_PROPERTY";

    @Override
    public void processMissingFieldError(
            String field, BindingResult result) {

        String[] codes = result.resolveMessageCodes(
                INPUT_REQUIRED, field);

        result.addError(new FieldError(
                result.getObjectName(),
                field,
                null,
                true,
                codes,
                null,
                "Missing required field"
        ));
    }

    @Override
    public void processPropertyAccessException(
            PropertyAccessException exception,
            BindingResult result) {

        String field = exception.getPropertyName();

        if (field == null || field.isBlank()) {
            result.addError(new ObjectError(
                    result.getObjectName(),
                    new String[]{INPUT_PROPERTY},
                    null,
                    "Cannot assign object property"
            ));
            return;
        }

        String code = "typeMismatch".equals(
                exception.getErrorCode())
                ? INPUT_TYPE : INPUT_PROPERTY;

        result.addError(new FieldError(
                result.getObjectName(),
                field,
                exception.getValue(),
                true,
                result.resolveMessageCodes(code, field),
                null,
                "Invalid input value"
        ));
    }
}
~~~

This class implements both methods of Spring's `BindingErrorProcessor` and stores no per-request state in fields.

Design decisions explained:

1. `resolveMessageCodes(code, field)` lets Spring generate candidate codes by object/field/type so `MessageSource` can resolve specific messages.
2. `FieldError(..., true, ...)` marks this as a **binding failure**. `FieldError#isBindingFailure()` remains useful even when application code changes the code from `typeMismatch` to `INPUT_TYPE`.
3. `exception.getErrorCode()` separates `typeMismatch` from other property access failures. Not every `PropertyAccessException` is a type mismatch.
4. `exception.getValue()` preserves the rejected value **internally** if form re-rendering needs it. The sample controller will not send it over HTTP.
5. Cases without an identifiable property name become an `ObjectError`; a custom API response must decide how to serialize global errors.
6. The stateless processor can be shared across requests, while `BindingResult` is always scoped to the current invocation.

### Implementing the interface vs. extending the default implementation

If you only need minor changes to default behavior, you can `extends DefaultBindingErrorProcessor` and override a single method. That preserves Spring's other behaviors, such as wrapped exception metadata and message arguments. When implementing `BindingErrorProcessor` directly as above, you are responsible for preserving the required metadata.

This example intentionally focuses on the error-code contract. If your application needs to retain the underlying exception for operational diagnostics, study `FieldError.wrap(...)` and how `DefaultBindingErrorProcessor` manages diagnostics rather than exposing technical messages to clients.

## 6. Java 17+ program running without an HTTP server

To test the processor, you can use `DataBinder` directly.

### 6.1. Gradle configuration

File `settings.gradle`:

~~~groovy
rootProject.name = 'binding-error-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.BindingErrorDemo'
}
~~~

In a Spring Boot project, let Boot's BOM/plugin manage Spring versions rather than pinning an independent `spring-context` version.

### 6.2. JavaBean model

File `src/main/java/demo/RegistrationForm.java`:

~~~java
package demo;

public class RegistrationForm {
    private String email;
    private Integer age;

    public RegistrationForm() {}

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

This DTO exposes setters for property binding and uses `Integer` instead of `int` so an unsubmitted field can be represented.

### 6.3. Creating the binder, attaching the processor, and reading errors

File `src/main/java/demo/BindingErrorDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class BindingErrorDemo {

    public static void main(String[] args) {
        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(
                form, "registration");

        binder.setAllowedFields("email", "age");
        binder.setRequiredFields("email");
        binder.setBindingErrorProcessor(
                new ApiBindingErrorProcessor());

        binder.bind(new MutablePropertyValues(
                Map.of("age", "abc")));

        BindingResult result = binder.getBindingResult();

        for (String field : List.of("email", "age")) {
            FieldError error = result.getFieldError(field);
            if (error != null) {
                System.out.println(
                        error.getField() + ":"
                        + error.getCode() + ":"
                        + error.isBindingFailure());
            }
        }

        System.out.println("hasErrors=" + result.hasErrors());
    }
}
~~~

All files above are in the `demo` package. Run using the included Gradle Wrapper:

~~~bash
./gradlew run
~~~

On Windows:

~~~powershell
.\gradlew.bat run
~~~

Stdout of the **Java class**, excluding Gradle task logs:

~~~text
email:INPUT_REQUIRED:true
age:INPUT_TYPE:true
hasErrors=true
~~~

Interpretation:

- `email` is omitted while `setRequiredFields("email")` requires it. The binder calls `processMissingFieldError`.
- `age=abc` cannot convert to `Integer`. The binder routes the property access error through `processPropertyAccessException`; the processor returns `INPUT_TYPE`.
- Both errors are added to `BindingResult` with `bindingFailure=true`.
- Under the default `DefaultMessageCodesResolver`, `getCode()` returns the last base code in the resolved code list, outputting `INPUT_REQUIRED`/`INPUT_TYPE`.

The program intentionally reads the two fields in `List.of(...)` order so stdout ordering is deterministic and independent of how the binder sorts errors.

## 7. Required field, conversion error, and suppressed field are three different things

| Input | Outcome |
| --- | --- |
| Missing `email`, `setRequiredFields("email")` configured | Missing field → `INPUT_REQUIRED` |
| `email=mai@example.com` provided | No missing-field error |
| `age=abc`, target is `Integer` | Type mismatch → `INPUT_TYPE` |
| `age=20` provided | Type conversion succeeds |
| Send `role`, while allowing only `email`/`age` | Excluded from binding; processor not necessarily invoked |
| `email=not-an-email` provided | String conversion succeeds; validator needed for format check |

`setRequiredFields(...)` checks **that a field is present during `bind(PropertyValues)`**, whereas Bean Validation such as `@NotBlank` and `@Email` validates **values or object state after binding**. If both mechanisms apply to the same field, decide whether duplicate semantic errors should be avoided.

### Do not apply requiredFields to constructor binding

`DataBinder#setRequiredFields(...)` is a mechanism for **property binding via `bind(PropertyValues)`**, **not for `construct(ValueResolver)`**. If the model is a record and requests use constructor binding, missing parameters must be handled via constructor/validation policies. Do not expect the processor to be called for every missing constructor parameter.

### Suppressed fields are not FieldErrors from the processor

When `binder.setAllowedFields("email", "age")` is configured, an input field like `role=ADMIN` can be excluded from binding. The list is recorded via:

~~~java
String[] suppressed =
        binder.getBindingResult().getSuppressedFields();
~~~

This is a **fragment** executed after `bind(...)`, not a standalone Java class. It reports fields rejected by the binder's allowed-fields policy. Spring **does not automatically turn every suppressed field into a `FieldError` via `BindingErrorProcessor`**.

If the API contract requires **rejecting requests with disallowed fields**, the controller/service must inspect `getSuppressedFields()` and assign a dedicated error code such as `INPUT_FIELD_NOT_ALLOWED`. Never assume `hasErrors()` is `true` when only suppressed fields exist.

### Unknown fields also follow a separate path

Under normal settings, `DataBinder` may ignore unknown properties. If `ignoreUnknownFields` is changed, a non-existent property path can trigger an exception different from a standard type mismatch. Test your actual binder configuration; **`BindingErrorProcessor` is not a catch-all exception handler**.

## 8. Using the processor in Spring MVC

In Spring MVC, `WebDataBinder` extends `DataBinder`, so you can configure the processor in `@InitBinder` for the right model attribute.

Assuming you copy `RegistrationForm.java` and `ApiBindingErrorProcessor.java` into a Spring Boot 3.x project with `spring-boot-starter-web`, add `src/main/java/demo/RegistrationController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {

    private final ApiBindingErrorProcessor processor =
            new ApiBindingErrorProcessor();

    @InitBinder("registration")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields("email", "age");
        binder.setRequiredFields("email");
        binder.setBindingErrorProcessor(processor);
    }

    @PostMapping(
            path = "/registrations",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> create(
            @ModelAttribute("registration") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            var problems = errors.getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "code", Objects.toString(
                                    error.getCode(), "INPUT_PROPERTY"),
                            "message", "Invalid input data"
                    ))
                    .toList();

            return ResponseEntity.badRequest()
                    .body(Map.of("errors", problems));
        }

        return ResponseEntity.ok(
                Map.of("status", "accepted"));
    }
}
~~~

This is a complete controller class; the app still needs a `@SpringBootApplication` bootstrap. Because the processor holds no per-request mutable fields, the instance held by the controller can be reused safely. Spring manages a separate binder per request/object and never shares `BindingResult` across requests.

**`BindingResult` must appear immediately after `@ModelAttribute`** so the controller receives binding errors for that exact object. `@InitBinder("registration")` scopes configuration to the model attribute named `registration`. The controller also calls `setAllowedFields` to prevent binding properties outside the API.

Test calling the endpoint:

~~~bash
curl -i -X POST http://localhost:8080/registrations -H "Content-Type: application/x-www-form-urlencoded" --data "age=abc"
~~~

Expect HTTP 400 and both codes `INPUT_REQUIRED` and `INPUT_TYPE` (order may vary). Valid request:

~~~bash
curl -i -X POST http://localhost:8080/registrations -H "Content-Type: application/x-www-form-urlencoded" --data "email=mai%40example.com&age=22"
~~~

Expect HTTP 200 and body:

~~~json
{"status":"accepted"}
~~~

This example only verifies the **binding error contract**. It does not yet use `@Valid`; to catch malformed emails or age outside business bounds, add Bean Validation and separate validation-code mapping rules.

## 9. Testing stable error codes

### 9.1. Unit testing via DataBinder

In a project with JUnit Jupiter, create `src/test/java/demo/ApiBindingErrorProcessorTest.java`:

~~~java
package demo;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

import static org.junit.jupiter.api.Assertions.*;

class ApiBindingErrorProcessorTest {

    private BindingResult bind(Map<String, ?> input) {
        DataBinder binder = new DataBinder(
                new RegistrationForm(), "registration");
        binder.setAllowedFields("email", "age");
        binder.setRequiredFields("email");
        binder.setBindingErrorProcessor(
                new ApiBindingErrorProcessor());
        binder.bind(new MutablePropertyValues(input));

        return binder.getBindingResult();
    }

    @Test
    void usesStableCodesForMissingAndTypeMismatch() {
        BindingResult errors = bind(Map.of("age", "abc"));

        FieldError missing = errors.getFieldError("email");
        FieldError wrongType = errors.getFieldError("age");

        assertNotNull(missing);
        assertNotNull(wrongType);
        assertEquals("INPUT_REQUIRED", missing.getCode());
        assertEquals("INPUT_TYPE", wrongType.getCode());
        assertTrue(missing.isBindingFailure());
        assertTrue(wrongType.isBindingFailure());
    }

    @Test
    void validValuesProduceNoBindingErrors() {
        BindingResult errors = bind(Map.of(
                "email", "mai@example.com",
                "age", "22"));

        assertFalse(errors.hasErrors());
    }

    @Test
    void disallowedFieldIsSuppressed() {
        BindingResult errors = bind(Map.of(
                "email", "mai@example.com",
                "age", "22",
                "role", "ADMIN"));

        assertFalse(errors.hasErrors());
        assertArrayEquals(
                new String[]{"role"},
                errors.getSuppressedFields());
    }
}
~~~

With the Gradle `application` setup from Section 6, add the test dependencies:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

The third test intentionally demonstrates that **a suppressed field is not automatically treated as a FieldError**. If the API must error on rejected fields, the response layer must explicitly handle `getSuppressedFields()`.

### 9.2. MockMvc HTTP testing

With Spring Boot 3.x and `spring-boot-starter-test`, you can write an MVC slice test:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
class RegistrationControllerTest {

    @Autowired MockMvc mvc;

    @Test
    void missingEmailGetsContractCode() throws Exception {
        mvc.perform(post("/registrations")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("age", "22"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("email"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("INPUT_REQUIRED"));
    }

    @Test
    void validInputIsAccepted() throws Exception {
        mvc.perform(post("/registrations")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "mai@example.com")
                    .param("age", "22"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }
}
~~~

The first test triggers only one binding error, so checking `errors[0]` causes no ordering issues. When multiple errors exist, assert by `field`/`code` without relying on array position. This test does not prove all exception types pass through the processor; add cases for failing setters and JSON if your API uses them.

If the application uses Spring Security, configure authentication and CSRF in MockMvc per your active policy. This minimal example assumes only the Spring Web and Test starters.

## 10. Choosing the right extension point: code, message, or JSON

Not every custom error contract needs a custom `BindingErrorProcessor`. Distinguish:

| Requirement | Appropriate extension point |
| --- | --- |
| Changing how binding `FieldError`/`ObjectError` instances are created | `BindingErrorProcessor` |
| Adjusting candidate code lists by object/field/type | `MessageCodesResolver` |
| Translating messages per locale | `MessageSource` and message bundles |
| Turning Spring errors into JSON/ProblemDetail responses | Controller / `@RestControllerAdvice` |
| Enforcing business rules on a bound object | Spring `Validator` or Jakarta Bean Validation |

If you only need to remap codes **when serializing HTTP responses**, you can keep `typeMismatch` internally in Spring and map it at the response layer:

~~~java
String apiCode = "typeMismatch".equals(error.getCode())
        ? "INPUT_TYPE" : "INPUT_PROPERTY";
~~~

This is a fragment where `error` is a `FieldError`. If the API does not require changing internal errors, this limits the blast radius.

### Difference between base code and candidate codes

`BindingErrorProcessor` sets the base code, e.g. `INPUT_TYPE`. `MessageCodesResolver` expands it into a list such as:

~~~text
INPUT_TYPE.registration.age
INPUT_TYPE.age
INPUT_TYPE.java.lang.Integer
INPUT_TYPE
~~~

This is an example code structure **when using DefaultMessageCodesResolver** with the matching field type; verify ordering and variants in your actual configuration.

Example `messages_vi.properties` content:

~~~properties
INPUT_REQUIRED.registration.email=Vui lòng nhập email
INPUT_TYPE.registration.age=Tuổi phải là số hợp lệ
INPUT_REQUIRED=Trường bắt buộc
INPUT_TYPE=Kiểu dữ liệu không hợp lệ
~~~

`MessageSource` can use `FieldError` as a `MessageSourceResolvable` to pick the specific message and fall back cleanly. Clients should rely solely on `code`, while `message` is display text that can vary by locale.

## 11. Limitations you must know

### 11.1. Constructor binding

`setRequiredFields` serves `bind(PropertyValues)` and does not act as a missing-parameter enforcer inside `construct(ValueResolver)`. When accepting records/immutable DTOs, pair appropriate constraints with constructor binding's error-handling path.

### 11.2. JSON request body

With `@RequestBody`, Jackson/`HttpMessageConverter` processes JSON before Bean Validation. If JSON fails to read or deserialize, `HttpMessageNotReadableException` can be thrown. A `BindingErrorProcessor` configured on the binder **does not automatically convert all such exceptions** into `INPUT_TYPE`. You need appropriate exception/response mappers.

### 11.3. Business validation

`@Email`, `@NotNull`, `@Min`, or custom `Validator`s check data after the binder finishes conversion. Those errors enter `BindingResult`, yet they are not created by the two `BindingErrorProcessor` callbacks. For a field that is both missing in `requiredFields` and annotated with constraints, consider a policy to avoid duplicate errors.

### 11.4. Field and global errors

If the processor creates an `ObjectError` (global error), controller code reading only `getFieldErrors()` will omit it from the response. A complete HTTP contract must decide how to serialize `getGlobalErrors()` or `getAllErrors()` too—for instance, using `field=null` or `field=""` consistently. In `RegistrationController`, the global error branch is not triggered by the two sample curl requests.

### 11.5. Software bugs vs. input errors

A setter throwing an exception can be a server bug rather than bad input. Never unconditionally map every `methodInvocation` to HTTP 400 without evaluating the cause. If it is a programming or infrastructure error, log safely and return an appropriate 5xx status in the exception-handling layer.

## 12. Security and concurrency

A processor can be a singleton if it **stores no per-request state**. In Section 5's class, all variables are parameters or locals; there are no `lastError`, `currentRequest`, or `currentBindingResult` fields. This prevents mixing errors across concurrent requests.

Securing the error contract:

1. Define codes from a finite catalog and version them when semantics change.
2. Never concatenate raw client data into error codes.
3. Never return `exception.getMessage()` or `rejectedValue` in HTTP bodies by default.
4. Keep `allowedFields`/DTOs restricted to client-editable attributes.
5. Enforce authorization in the service/domain layer; binding error codes do not replace authorization.
6. Bound request size and nested collection inputs.
7. Group metrics/logs by code and endpoint, minimizing sensitive data.
8. Assert on codes and the `bindingFailure` flag rather than comparing Vietnamese messages.

If sensitive data must not even be retained inside `BindingResult`, the implementation can pass `null` instead of `exception.getValue()` and adjust form re-rendering UX accordingly. That is a policy choice and should not be forced blindly on every form.

## 13. Common implementation mistakes

**Forgetting `setBindingErrorProcessor`:** defining a custom class without registering it on the binder leaves Spring using `DefaultBindingErrorProcessor`.

**Forgetting required fields:** `processMissingFieldError` does not automatically scan all properties. Configure `setRequiredFields(...)` in property binding if a field must be present in the request.

**Using `rejectValue(...)` expecting `bindingFailure=true`:** that helper is for convenient validation error reporting and does not populate full binding-failure metadata like `FieldError`'s full constructor. When your contract relies on that flag, construct `FieldError` directly.

**Turning every property exception into INPUT_TYPE:** many errors belong to `methodInvocation` or other categories. Map `typeMismatch` to `INPUT_TYPE` only when it is genuinely a type conversion failure.

**Concatenating field names into a single code:** skipping `resolveMessageCodes` loses object/field/type-specific message lookup. If you do not want candidate codes, make that an intentional choice.

**Treating suppressed fields as binding errors:** fields excluded by `allowedFields` usually require checking `getSuppressedFields()`; the processor's callbacks do not report all blocked fields automatically.

**Ignoring global errors:** processors can emit `ObjectError`s; response mappers must read them when contracts include global errors.

**Using the processor to handle all HTTP errors:** JSON body errors, method validation, authentication, authorization, and business exceptions follow different paths.

**Returning raw rejected values:** secrets like passwords, tokens, and personal data must not leak through responses or logs.

**Customizing globally when only one form has a custom contract:** apply `@InitBinder("registration")` locally where appropriate; configure globally only when all controllers share that contract.

## 14. Adoption checklist

- [ ] Error code catalog, scope, and semantics are clearly documented.
- [ ] Processor implements both `BindingErrorProcessor` callbacks.
- [ ] `FieldError` preserves object, field, `bindingFailure`, and candidate codes.
- [ ] `setRequiredFields(...)` configured for missing fields in property binding.
- [ ] `setAllowedFields(...)` / input DTOs aligned with actual permissions.
- [ ] `BindingResult#getSuppressedFields()` checked if the contract rejects disallowed fields.
- [ ] Controller places `BindingResult` immediately after `@ModelAttribute`.
- [ ] Responses do not leak exception messages, rejected values, or stack traces.
- [ ] Unit tests cover binding error codes, and MockMvc tests verify HTTP status/JSON.
- [ ] Error mapping for JSON, validation, and business errors is designed at the proper layers.

## 15. Key takeaway

`BindingErrorProcessor` governs **how errors are represented during data binding**. When you have a custom error contract, you can map `required`, `typeMismatch`, and `methodInvocation` to stable codes like `INPUT_REQUIRED`, `INPUT_TYPE`, and `INPUT_PROPERTY` while keeping Spring's standard `BindingResult`.

If you only need to change **messages** or the **JSON response**, `MessageSource` and the response mapping layer are usually better fits. When you need to alter **`FieldError`/`ObjectError` right at the source**, register a custom processor on `DataBinder` or `WebDataBinder`, test both missing fields and conversions, and account for error paths outside the processor's scope.

### Official further reading

- [BindingErrorProcessor API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/BindingErrorProcessor.html)
- [DefaultBindingErrorProcessor API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DefaultBindingErrorProcessor.html)
- [DataBinder API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DataBinder.html)
- [FieldError API, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring MVC @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
