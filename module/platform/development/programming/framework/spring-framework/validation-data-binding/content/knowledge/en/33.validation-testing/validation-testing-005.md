# Testing Constructor Binding with Records and Incomplete Data in Spring Framework

## 1. Problem statement: request misses parameters while the record has no setters

Since Java 16, `record` has been a natural fit for modeling immutable structured data. In Spring MVC 6.1+, `@ModelAttribute` can use **constructor binding**: Spring reads HTTP parameters, converts their types, and passes them into the object's constructor (e.g., a record's canonical constructor) instead of requiring a no-argument constructor plus setters.

Suppose a signup form is modeled as:

```java
public record SignupForm(
        @NotBlank String displayName,
        @NotNull @Min(18) Integer age,
        @Email String email,
        String referralCode
) {}
```

A client may send all fields:

```http
POST /signup
Content-Type: application/x-www-form-urlencoded

displayName=Lan&age=22&email=lan%40example.org&referralCode=HELLO
```

Or send **incomplete data**:

```http
POST /signup
Content-Type: application/x-www-form-urlencoded

email=lan%40example.org
```

Testing questions go beyond "is the record created?" and include:

1. When `displayName` and `age` are missing, what values does Spring pass to construct the record?
2. Which rule reports "required": constructor binding, `@NotBlank`, `@NotNull`, or `setRequiredFields`?
3. If a parameter is present but **fails type conversion**, e.g., `age=abc`, where is the error recorded?
4. Why does `@Valid @ModelAttribute` with `BindingResult` behave differently from a handler method without `BindingResult`?
5. Why does the same record sent as JSON via `@RequestBody` not necessarily follow the same binding path as a form?
6. How do you write `MockMvc` tests covering complete data, missing fields, blank values, wrong types, parameters renamed with `@BindParam`, and extra parameters?

**Core principle:** constructor binding and Bean Validation are two **separate** phases. Spring can pass `null` for a missing reference-type component, while validation constraints like `@NotNull` and `@NotBlank` decide whether that case is an error. An immutable record **does not automatically require every component to be present**.

Scope of this lesson: **Java 17+, Spring Boot 3.3.6, Spring Framework 6.1.x, Servlet Spring MVC, and Jakarta Validation**. On Spring Boot 4 / Spring Framework 7 or different binder/provider configurations, re-run the test suite rather than assuming identical behavior down to every detail.

## 2. From form request to record constructor

### 2.1. @ModelAttribute has its own instance lookup and binding mechanism

With a handler:

```java
@PostMapping("/form")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult errors) {
    // ...
}
```

Spring MVC looks up or creates the model attribute; when creating it from an HTTP request, it can invoke the **primary constructor**, look up values by parameter name, and convert their types. A record has a canonical constructor tied to its record components; neither a no-arg constructor nor setters are needed.

Conceptual flow:

```text
Request parameters:
  displayName=Lan
  age=22
  email=lan@example.org
        |
        v
Spring MVC @ModelAttribute argument resolver
        |
        v
WebDataBinder / constructor binding
  String "Lan"  -> String displayName
  String "22"   -> Integer age
  String email  -> String email
  missing referralCode -> null
        |
        v
new SignupForm("Lan", 22, "lan@example.org", null)
        |
        v
@Valid -> Jakarta Bean Validation constraints
        |
        v
BindingResult:
  empty -> controller returns success
  errors -> controller/advice returns HTTP 400
```

The diagram illustrates the simple case with reference types and a constructor that does not reject `null` itself. If you write a custom compact constructor that throws exceptions or use complex nested/collection conversions, object-creation failures can happen **before** constraint validation runs.

### 2.2. Incomplete-data conditions table

With the constraints in use:

| Parameter | Component type | When absent | Validation |
| --- | --- | --- | --- |
| `displayName` | `String` | Can be passed as `null` to constructor | `@NotBlank` rejects `null` or whitespace-only strings |
| `age` | `Integer` | Can be `null` | `@NotNull` reports missing; `@Min(18)` **does not** forbid null by itself |
| `email` | `String` | Can be `null` | `@Email` normally allows null, making this field optional |
| `referralCode` | `String` | Can be `null` | No mandatory constraint |
| `age=abc` | `Integer` | Has a **value** that cannot convert | Binding/conversion error, typically code `typeMismatch` |

**Do not assume "records disallow null".** A record's immutability means no setters mutate components after construction; it **does not automatically perform null checking**.

### 2.3. Testing "absent" separately from "invalid" values

At least four scenarios must be tested:

- Parameter **not sent**: `age` key is missing.
- Parameter key present but **empty**: `age=`.
- Value present but **wrong format**: `age=abc`.
- Value convertible in type but **invalid**: `age=16`.

These can lead to different errors: `NotNull`, `typeMismatch`, or `Min`. For `String`, `displayName=` and `displayName=%20%20` both fail `@NotBlank`; a missing parameter may also fail `@NotBlank` when the constructor receives null.

Exact outcomes depend on the conversion service and binding setup; assert the **intentional** properties of the error response instead of hardcoding implicit assumptions about reflection or providers.

## 3. @ModelAttribute constructor binding and @RequestBody JSON are two mechanisms

A common confusion is using the term "constructor binding" loosely for every way a record is instantiated. Both paths may end up calling the canonical constructor, yet **the instantiating component and conversion rules are not the same**.

| | `@ModelAttribute` | `@RequestBody` |
| --- | --- | --- |
| Common data source | Query/form parameters, path variables, and headers within MVC resolver scope | HTTP body read by an `HttpMessageConverter` (usually Jackson for JSON) |
| Mechanism | Spring `WebDataBinder` and primary constructor binding | JSON deserialization via Jackson |
| Parameter names | Constructor parameter names, customizable via Spring `@BindParam` | JSON property names, Jackson annotations/configuration |
| Type conversion | Spring conversion service, property editors/formatters | Jackson deserializers |
| Conversion failure | Binding errors or exceptions depending on phase | Typically `HttpMessageNotReadableException` |
| Bean Validation | `@Valid` / `@Validated` after binding | `@Valid` / `@Validated` after deserialization |
| Completely missing body | Not a required-body concept for form parameters | `@RequestBody(required=true)` may report an unreadable body |
| Typical validation error | `BindingResult` or `MethodArgumentNotValidException` | `MethodArgumentNotValidException` once the object deserializes |

**Important:** `@BindParam("display-name")` is a naming rule for Spring constructor binding; it is not equivalent to Jackson's `@JsonProperty("display-name")`. The runnable project separates two request DTOs to highlight this boundary.

### 3.1. Incomplete JSON data

With:

```java
public record JsonSignup(
        @NotBlank String displayName,
        @NotNull Integer age
) {}
```

and JSON:

```json
{"displayName":"Lan"}
```

in Spring Boot's typical Jackson setup, the record can be constructed with `age=null`, and `@Valid` then catches `@NotNull`. However, if a project enables Jackson features requiring creator properties to be present, or writes a constructor throwing on null, the request may be rejected during **deserialization** before validation.

Therefore tests should cover:

- Missing a JSON property.
- Property present with JSON `null`.
- Empty body or unparseable JSON.
- JSON with all properties and valid types.

Do not assume every missing JSON property becomes `NotNull`; parsing must succeed before Bean Validation inspects the object.

## 4. Three "required" mechanisms not to confuse

### 4.1. Bean Validation on record components

Example:

```java
public record SignupForm(
        @NotBlank String displayName,
        @NotNull @Min(18) Integer age
) {}
```

- `@NotBlank` detects `null`, empty strings, or whitespace-only strings.
- `@NotNull` requires a non-null reference.
- `@Min(18)` checks the value when non-null. `@Min` treats `null` as valid per Jakarta Validation.
- `@Email` checks email format when a value is present; it does not make email mandatory on its own.

If `age` is missing, expect `NotNull` rather than `Min`. If `age=16`, expect `Min`. If `age=abc`, the error is conversion and there may not yet be an object with a valid `Integer` for `@Min` to evaluate.

### 4.2. @RequestParam(required=true) does not apply automatically to record components

`@RequestParam(required=true)` attaches directly to a **controller method argument**:

```java
@GetMapping("/simple")
public String simple(@RequestParam String name) {
    return name;
}
```

It does not trigger automatically just because a record component is named `name`. A record bound with `@ModelAttribute` has its own semantics. Do not use a `@RequestParam` example to assume every missing constructor parameter will throw `MissingServletRequestParameterException`.

### 4.3. DataBinder#setRequiredFields is not a constructor-binding policy

`DataBinder#setRequiredFields("age")` is designed for property binding via `bind(PropertyValues)`; the Spring Framework 6.1 Javadoc explicitly states it **does not apply** to constructor binding via `construct(ValueResolver)`.

Do not write:

```java
@InitBinder("signupForm")
void requireFields(WebDataBinder binder) {
    binder.setRequiredFields("displayName", "age");
}
```

and conclude that missing canonical constructor parameters are guaranteed to produce error code `required`. On the constructor-binding path, use Bean Validation such as `@NotBlank`/`@NotNull` and test the actual behavior. The snippet above is a **counter-example snippet**, not part of the runnable demo.

## 5. @BindParam renames the input source for the constructor

HTTP clients may send hyphenated parameter names:

```text
display-name=Lan&age=22
```

In Java, record components typically use camelCase:

```java
public record FormSignup(
        @BindParam("display-name") @NotBlank String displayName,
        @NotNull Integer age
) {}
```

`@BindParam` lives in:

```java
org.springframework.web.bind.annotation.BindParam
```

It is supported in Spring Framework 6.1 for constructor parameters/fields used in `@ModelAttribute` binding. For Java records, an annotation with an appropriate target can be propagated by the compiler to the canonical constructor parameter or backing field. Tests in this lesson verify `display-name` is accepted while `displayName` does not replace the alias on the configured constructor path.

Key points to watch:

- `@BindParam` **is not** `@JsonProperty`. In a `@RequestBody` endpoint, use the appropriate Jackson annotation/configuration to rename JSON fields.
- Do not confuse the HTTP name `display-name` with the field path in `BindingResult`: errors may still refer to the Java property `displayName`.
- When using `@BindParam` on record components with reflection/AOT tooling, write integration tests instead of only calling the constructor via `new`.
- If a client sends both the alias and the Java name, define a precedence or duplicate-rejection policy instead of guessing which value the parser picks.

## 6. Why are records well suited for data-binding safety?

A mutable entity might expose setters for `isAdmin`, `balance`, or `ownerId`. Binding request parameters directly onto such an entity lets an attacker attempt to supply fields outside business intent.

A record form DTO:

```java
public record FormSignup(
        String displayName,
        Integer age,
        String email,
        String referralCode
) {}
```

only has its declared constructor parameters; it has no setters for `isAdmin` or `ownerId`. That is an advantage of **constructor binding with immutable DTOs**.

To state the policy of binding only declared inputs explicitly, Spring MVC 6.1+ supports:

```java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

`setDeclarativeBinding(true)` allows constructor binding and permits property binding only if matching `allowedFields` are configured. In the runnable example, there are no mutable setters; the flag still documents the binder policy explicitly.

**Warning:** not every record is automatically completely safe. If a record includes a `role` or `ownerId` component and the controller blindly trusts it for authorization, an attacker can still supply it. Design **input DTOs containing only client-controllable fields**, obtain identity/roles from server-side security context, and validate business rules and authorization separately.

If you must property-bind mutable objects, use `setAllowedFields(...)` with an allowlist rather than relying on a blacklist. Even then, `allowedFields` primarily governs property binding and does not replace designing the right constructor parameter list.

## 7. Runnable project: Spring Boot 3.3.6 + Java 17

The complete project exposes two paths:

- `POST /api/signup/form/checked`: form-urlencoded, Spring MVC record constructor binding, `@Valid`, adjacent `BindingResult`, controller constructs errors itself.
- `POST /api/signup/form/strict`: form-urlencoded, record constructor binding **without** `BindingResult`, errors handled via `@RestControllerAdvice`.
- `POST /api/signup/json`: JSON deserialized by Jackson into a separate record, then `@Valid`, allowing comparison of missing properties against forms.
- `MockMvc` tests covering full, incomplete, optional, blank, below-minimum, type-mismatch, alias, extra parameter, missing/null/malformed JSON, and error mapping.

### 7.1. Project structure

```text
record-binding-tests/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/recordbinding/
        RecordBindingApplication.java
        FormSignup.java
        JsonSignup.java
        SignupView.java
        FieldIssue.java
        ApiError.java
        ErrorMapper.java
        SignupController.java
        SignupExceptionAdvice.java
      resources/
        application.properties
    test/
      java/com/example/recordbinding/
        SignupBindingTest.java
```

### 7.2. Gradle

File `settings.gradle`:

```groovy
rootProject.name = 'record-binding-tests'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The `-parameters` flag preserves Java parameter names in runtime bytecode where Spring uses reflection/`ParameterNameDiscoverer`. For Java records, canonical constructor and component metadata help Spring resolve names; keeping `-parameters` is still a reliable configuration when a project also includes ordinary constructor-bound classes.

`spring-boot-starter-validation` is required so `@Valid` has a Jakarta Validation provider. Spring Boot 3 uses `jakarta.validation.*`; do not mix in `javax.validation.*` from older examples.

### 7.3. Main class

File `src/main/java/com/example/recordbinding/RecordBindingApplication.java`:

```java
package com.example.recordbinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RecordBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RecordBindingApplication.class, args);
    }
}
```

File `src/main/resources/application.properties`:

```properties
spring.application.name=record-binding-tests
spring.mvc.problemdetails.enabled=false
```

`spring.mvc.problemdetails.enabled=false` keeps the example focused on the custom payload. If a real application standardizes on `ProblemDetail` or `ResponseEntityExceptionHandler`, avoid declaring duplicate handlers for the same exceptions.

### 7.4. FormSignup: record using constructor binding and alias

File `src/main/java/com/example/recordbinding/FormSignup.java`:

```java
package com.example.recordbinding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.BindParam;

public record FormSignup(
        @BindParam("display-name")
        @NotBlank
        String displayName,

        @NotNull
        @Min(18)
        Integer age,

        @Email
        String email,

        String referralCode
) {}
```

Components:

- `displayName` is the Java name; form input uses `display-name`.
- `age` is `Integer` rather than `int` to represent an **unsent** value explicitly with null.
- `email` and `referralCode` are optional; they may be constructed with null.
- Avoid writing a compact constructor that throws on null; missing fields are reported via `@Valid` and `BindingResult`, rather than failing immediately during object construction.

### 7.5. JsonSignup: separate record for JSON

File `src/main/java/com/example/recordbinding/JsonSignup.java`:

```java
package com.example.recordbinding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record JsonSignup(
        @NotBlank String displayName,
        @NotNull @Min(18) Integer age,
        @Email String email
) {}
```

This record uses the Jackson JSON property `displayName` without `@BindParam`. Same Bean Validation rules, yet **the preceding object-creation path differs**.

### 7.6. Success response DTO

File `src/main/java/com/example/recordbinding/SignupView.java`:

```java
package com.example.recordbinding;

public record SignupView(
        String displayName,
        Integer age,
        String email,
        String referralCode
) {}
```

Using a response record lets Jackson emit JSON without returning a domain entity. Null optional fields remain valid in the example; production apps can configure their own serialization policy.

### 7.7. Error response DTOs

File `src/main/java/com/example/recordbinding/FieldIssue.java`:

```java
package com.example.recordbinding;

public record FieldIssue(
        String field,
        String code
) {}
```

File `src/main/java/com/example/recordbinding/ApiError.java`:

```java
package com.example.recordbinding;

import java.util.List;

public record ApiError(
        String code,
        List<FieldIssue> errors
) {}
```

The payload intentionally **omits rejectedValue** and exception stack traces. In constructor-binding tests, the key distinction is **field** and **error type**. If localized messages are required, add `MessageSource#getMessage(FieldError,Locale)` and an explicit default-message policy; do not drive client logic from provider text.

### 7.8. ErrorMapper: shared by controller and advice

File `src/main/java/com/example/recordbinding/ErrorMapper.java`:

```java
package com.example.recordbinding;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

final class ErrorMapper {

    private ErrorMapper() {}

    static ApiError invalid(BindingResult result) {
        List<FieldIssue> errors = result.getAllErrors()
                .stream()
                .map(ErrorMapper::toIssue)
                .sorted(
                        Comparator.comparing(FieldIssue::field)
                                .thenComparing(FieldIssue::code)
                )
                .toList();

        return new ApiError("VALIDATION_ERROR", errors);
    }

    private static FieldIssue toIssue(ObjectError error) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        String code = Objects.toString(
                error.getCode(), "invalid"
        );

        return new FieldIssue(field, code);
    }
}
```

`BindingResult#getAllErrors()` retrieves both `FieldError` and `ObjectError` (such as class-level constraints). Sorting by `field` then `code` gives the HTTP error array an application-defined order, independent of Jakarta Validator or binder ordering. `field=""` is the demo convention for object-level errors.

### 7.9. Controller with three endpoints

File `src/main/java/com/example/recordbinding/SignupController.java`:

```java
package com.example.recordbinding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/signup")
public class SignupController {

    @InitBinder("signupForm")
    void initSignupBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    @PostMapping(
            path = "/form/checked",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> checked(
            @Valid @ModelAttribute("signupForm") FormSignup input,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(
                    ErrorMapper.invalid(errors)
            );
        }

        return ResponseEntity.ok(new SignupView(
                input.displayName(),
                input.age(),
                input.email(),
                input.referralCode()
        ));
    }

    @PostMapping(
            path = "/form/strict",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public SignupView strict(
            @Valid @ModelAttribute("signupForm") FormSignup input) {

        // If invalid, Spring MVC handles the exception
        // before executing this method body.
        return new SignupView(
                input.displayName(),
                input.age(),
                input.email(),
                input.referralCode()
        );
    }

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public SignupView json(
            @Valid @RequestBody JsonSignup input) {

        return new SignupView(
                input.displayName(),
                input.age(),
                input.email(),
                null
        );
    }
}
```

**Two key points:**

1. `BindingResult errors` sits **immediately after** `@Valid @ModelAttribute(...) FormSignup input`. Spring can pass errors into the controller so the controller decides the HTTP response itself.
2. `/form/strict` has no `BindingResult`, so on validation failure Spring MVC typically throws `MethodArgumentNotValidException`, handled by the advice.

At `/json`, data is handled by Jackson; `@InitBinder("signupForm")` only applies to the binder for the attribute named `signupForm` and does not turn JSON deserialization into `WebDataBinder.construct`.

### 7.10. Global advice for strict/form and JSON

File `src/main/java/com/example/recordbinding/SignupExceptionAdvice.java`:

```java
package com.example.recordbinding;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class SignupExceptionAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body(
                ErrorMapper.invalid(exception.getBindingResult())
        );
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError("INVALID_JSON", List.of())
        );
    }
}
```

`MethodArgumentNotValidException` fits `@Valid` when an object has bound/deserialized and has violations on the standard MVC argument-validation path. `HttpMessageNotReadableException` represents an unreadable JSON request body, such as truncated JSON. Exceptions thrown by a constructor directly or by method validation can follow other types; they do **not automatically** fall into the two handlers above.

## 8. MockMvc: complete test suite for records with missing data

File `src/test/java/com/example/recordbinding/SignupBindingTest.java`:

```java
package com.example.recordbinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupBindingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void completeFormBindsToRecordConstructor() throws Exception {
        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("display-name", "Lan")
                .param("age", "22")
                .param("email", "lan@example.org")
                .param("referralCode", "HELLO"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.age").value(22))
            .andExpect(jsonPath("$.email").value("lan@example.org"))
            .andExpect(jsonPath("$.referralCode").value("HELLO"));
    }

    @Test
    void missingRequiredFieldsProduceTwoValidationErrors()
            throws Exception {

        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "lan@example.org"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors.length()").value(2))
            .andExpect(jsonPath("$.errors[0].field").value("age"))
            .andExpect(jsonPath("$.errors[0].code").value("NotNull"))
            .andExpect(jsonPath("$.errors[1].field")
                    .value("displayName"))
            .andExpect(jsonPath("$.errors[1].code")
                    .value("NotBlank"));
    }

    @Test
    void missingOptionalFieldsDoNotFailValidation()
            throws Exception {

        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("display-name", "Lan")
                .param("age", "22"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.age").value(22));
    }

    @Test
    void blankNameAndTooYoungAgeAreNotMissingFields()
            throws Exception {

        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("display-name", "  ")
                .param("age", "16"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors.length()").value(2))
            .andExpect(jsonPath("$.errors[0].field").value("age"))
            .andExpect(jsonPath("$.errors[0].code").value("Min"))
            .andExpect(jsonPath("$.errors[1].field")
                    .value("displayName"))
            .andExpect(jsonPath("$.errors[1].code")
                    .value("NotBlank"));
    }

    @Test
    void invalidNumericFormFieldIsABindingFailure()
            throws Exception {

        mvc.perform(post("/api/signup/form/strict")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("display-name", "Lan")
                .param("age", "not-a-number"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void aliasIsNotTheSameAsJavaComponentName()
            throws Exception {

        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("age", "22"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors.length()").value(1))
            .andExpect(jsonPath("$.errors[0].field")
                    .value("displayName"))
            .andExpect(jsonPath("$.errors[0].code")
                    .value("NotBlank"));
    }

    @Test
    void extraFieldCannotMutateNonExistentRecordProperty()
            throws Exception {

        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("display-name", "Lan")
                .param("age", "22")
                .param("isAdmin", "true"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.isAdmin").doesNotExist());
    }

    @Test
    void missingFormFieldsWithoutBindingResultReachAdvice()
            throws Exception {

        mvc.perform(post("/api/signup/form/strict")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors.length()").value(2));
    }

    @Test
    void jsonMissingRecordPropertiesCanBeValidationErrors()
            throws Exception {

        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"email":"lan@example.org"}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors.length()").value(2));
    }

    @Test
    void explicitJsonNullIsRejectedByNotNull()
            throws Exception {

        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"displayName":"Lan","age":null}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field").value("age"))
            .andExpect(jsonPath("$.errors[0].code").value("NotNull"));
    }

    @Test
    void malformedJsonHasDifferentErrorCode()
            throws Exception {

        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Lan\",\"age\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void validJsonDoesNotUseFormBindParamAlias()
            throws Exception {

        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"displayName":"Lan","age":25}
                        """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.age").value(25));
    }
}
```

There are **12 test methods** grouped by scenario:

- **Complete form:** verifies `@BindParam("display-name")` and conversion of `age="22"` to `Integer 22`.
- **Missing required form fields:** verifies `@NotBlank` and `@NotNull` run after constructor binding.
- **Missing optional form fields:** verifies omitting `email`/`referralCode` does not raise errors.
- **Blank and below-minimum values:** distinguishes `NotBlank`/`Min` from "parameter absent".
- **Invalid type conversion:** confirms the request is rejected instead of processing an invalid record.
- **Alias name:** tests `display-name` vs `displayName`.
- **Extra data:** sends `isAdmin` and confirms no corresponding field exists in the public response.
- **No BindingResult:** confirms global advice handles the errors.
- **Missing/null/malformed JSON:** distinguishes Jakarta validation from Jackson parsing.
- **Valid JSON:** proves Jackson uses its own property name, not the form record's `@BindParam` alias.

### 8.1. Running tests

From a project directory containing the Gradle wrapper:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If no Gradle wrapper has been generated yet, use an installed Gradle binary to create the wrapper, or run:

```bash
gradle test
```

**Expected:** 12 tests PASS in an environment matching Spring Boot 3.3.6/Java 17 and the declared classpath. Expected results represent the intended design of the test suite; **no claim is made that they were executed** while authoring this lesson. To confirm exact behavior on your application's version, run them in CI.

### 8.2. Do not depend on provider ordering

`ErrorMapper` intentionally sorts by `field` then `code`. That is why tests can assert:

```text
age        -> NotNull
displayName -> NotBlank
```

Do not call `BindingResult#getFieldErrors().get(0)` to assume which field always errors first. Bean Validation providers do not guarantee evaluation order. If the response needs ordering by UI form order instead of alphabetical order, define a dedicated comparator and test it.

### 8.3. Why is testing missing optional fields important?

Only testing requests with missing required fields can create the false impression that "a record constructor requires every argument". The `missingOptionalFieldsDoNotFailValidation` test disproves that: **a missing reference type with no mandatory constraint** can be valid.

Conversely, if the business contract requires email, add `@NotBlank` (and `@Email`) and update the expected result. Do not write a test asserting "missing email must fail" when the code only uses `@Email`, because that conflicts with Jakarta Validation.

## 9. Missing-data test matrix

A useful matrix for code review:

| Case | Example | What to check | Outcome with demo |
| --- | --- | --- | --- |
| All required fields present | `display-name=Lan&age=22` | Constructor bind + validation | HTTP 200 |
| Missing name and age | `email=lan@example.org` | Both constraints | HTTP 400, `NotBlank` and `NotNull` |
| Missing optional fields | No `email`, `referralCode` | Optional fields cause no error | HTTP 200 |
| Whitespace-only name | `display-name=%20%20` | `@NotBlank` | HTTP 400 |
| Age below minimum | `age=16` | `@Min(18)` | HTTP 400 |
| Unconvertible age | `age=abc` | Conversion/binding | HTTP 400 |
| Java name instead of alias | `displayName=Lan` | `@BindParam` | HTTP 400 when `display-name` missing |
| Extra input | `isAdmin=true` | Record immune to mass assignment | Does not create `isAdmin` |
| JSON missing property | `{"age":22}` | Jackson creates record + Bean Validation | Depends on missing fields |
| Explicit JSON `null` | `{"displayName":"Lan","age":null}` | `@NotNull` | HTTP 400 |
| Malformed JSON | `{"age":` | Jackson parsing | HTTP 400, `INVALID_JSON` |
| No request body | POST JSON without body | `@RequestBody(required=true)` | HTTP 400 / unreadable body |

Additional business-specific cases should also be tested when required by the app, such as duplicate params, multiple values for a scalar parameter, Unicode whitespace, numbers exceeding `Integer` range, invalid email formats, nested forms, and group-specific validation.

## 10. Why is Integer better than int when detecting missing values?

Using `int` for a required field easily blurs "no input provided" with "value 0 provided". A Java primitive cannot hold null; depending on the binding path, conversion, and constructor invocation, a default value or conversion error may occur. Do not rely on implicit binder behavior when you actually need to represent **missing**.

Prefer:

```java
public record QuantityForm(
        @NotNull @Min(1) Integer quantity
) {}
```

rather than relying on:

```java
public record QuantityForm(
        @Min(1) int quantity
) {}
```

With `Integer`, when an absent parameter yields null, `@NotNull` catches the missing requirement. With `int`, 0 can conflate "client sent 0" and "no input"; if you need to distinguish these two states, avoid primitives for that input DTO component.

**You do not always need Integer:** if the domain permits defaulting to 0 and absence clearly means the same as 0, a primitive may fit. Decide based on the API contract, not syntactic convenience.

## 11. Record compact constructor: validation before or after?

Java allows compact constructors:

```java
public record StrictForm(String displayName, Integer age) {
    public StrictForm {
        if (displayName == null) {
            throw new IllegalArgumentException("Missing displayName");
        }
    }
}
```

With this constructor, if `displayName` is missing and Spring/Jackson passes null, the constructor can throw an exception **during object creation**. When the object fails to instantiate, you cannot assume `@Valid` on the object will produce a `FieldError NotBlank`.

This creates a major difference in testing:

- **Bean Validation on record components:** fits cases where you want to collect multiple field errors in a single `BindingResult`.
- **Constructor guard clauses:** fits invariants that must never allow an invalid domain object to exist, but requires a clear exception-mapping strategy. Do not automatically treat every `IllegalArgumentException` from a constructor as an HTTP 400 input error.
- **Controller DTO vs domain record:** you can use an input record that allows temporarily invalid state (to collect errors), and after validation map it into a domain type with strong invariants.

Example pipeline:

```text
HTTP -> FormSignup DTO (may contain nulls)
     -> @Valid / BindingResult
     -> if valid: mapping + domain constructor
     -> service / persistence
```

Do not use throwing domain constructors to replace whole-input error collection if the UI expects multiple errors returned at once.

## 12. Nested records and missing child data

Constructor binding can construct nested objects via nested paths. **Illustrative snippet**:

```java
public record Address(
        @NotBlank String city,
        String postalCode
) {}

public record CheckoutForm(
        @Valid @NotNull Address address,
        @NotNull Integer quantity
) {}
```

A form client can send:

```text
address.city=Hanoi&address.postalCode=100000&quantity=2
```

Spring constructor binding supports nested objects and collection parameters, but when an **entire nested object is missing**, instantiation/null behavior and errors can depend on types, resolvers, and configuration. Therefore test:

1. Neither `address` nor `address.*` present.
2. `address.city` present while `address.postalCode` is missing.
3. `address.city=`.
4. Multi-level nested `address`.
5. Collection keys `items[0].sku`, `items[1].sku`.
6. An indexed field containing an unconvertible value.

If `address` is truly required, `@NotNull` is needed on the parent, while `@Valid` cascades to inner constraints when the nested object exists. `@Valid` does not substitute for `@NotNull` on a null reference.

`DataBinder#setAutoGrowNestedPaths` is an option for bean property binding and **should not be used as the default explanation for constructor binding**. In Spring Framework 6.1, the Javadoc distinguishes auto-growing setter/field paths from recursive constructor binding. The two techniques work differently.

## 13. Parameter renaming, formatters, and type conversion errors

### 13.1. @BindParam does not rename the Java property

In the demo form:

```java
@BindParam("display-name") String displayName
```

Spring looks up request parameter `display-name` for constructor component `displayName`. `FieldError#getField()` typically references the Java property `displayName`. Do not let the frontend match error fields directly against HTML input names without mapping when aliases are used.

### 13.2. ConversionService handles form data types

Form data is all text; Spring MVC uses the conversion service and formatters to convert:

- `"22"` → `Integer 22`.
- `"2026-11-06"` → `LocalDate` when formatting rules match.
- `"ACTIVE"` → enum when supported by converters/formatters.
- `"true"` → Boolean when the representation is accepted.
- List/map keys via indexed paths, subject to size/complexity limits.

For dates, e.g.:

```java
public record AppointmentForm(
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate visitDate
) {}
```

this is an **illustrative snippet** requiring imports for `java.time.LocalDate` and `org.springframework.format.annotation.DateTimeFormat`. Test valid dates, missing dates, malformed formats, and invalid calendar dates. Do not treat format errors as `@NotNull` violations.

### 13.3. Do not assume all type errors yield the same exception

A conversion failure may be recorded in `BindingResult` as `typeMismatch`, or cause an earlier exception if object construction fails. The `@ModelAttribute` path differs from Jackson `@RequestBody`. When building production handlers:

- Use `BindingResult` if you want to return multiple field errors.
- Use advice for `MethodArgumentNotValidException` when `BindingResult` is absent.
- Handle malformed JSON via `HttpMessageNotReadableException`.
- Verify special constructor exceptions on your actual framework version.
- Do not catch all `RuntimeException` instances and return the same 400 error.
- Never echo raw exception messages or rejected values to clients.

## 14. Differences with validation groups and method validation

`@Valid` triggers Bean Validation's default `Default` group. If an application has Create/Update groups:

```java
public interface OnCreate {}
public interface OnUpdate {}

public record EditForm(
        @NotBlank(groups = OnCreate.class) String name,
        @NotNull(groups = OnUpdate.class) Long id
) {}
```

then `@Validated(OnCreate.class)` or `@Validated(OnUpdate.class)` is needed at the appropriate boundary to select the group. This is an illustrative snippet, not part of the runnable demo.

A record missing `id` can be valid on Create yet invalid on Update by design, **not because constructor binding knows how to distinguish the two workflows**. Test the right group for each endpoint.

Since Spring MVC 6.1, direct constraints on method parameters or return values can trigger **method validation** and `HandlerMethodValidationException` instead of `MethodArgumentNotValidException`. If you want to test an `@ModelAttribute` route like the demo, avoid accidentally adding `@Min` directly onto another handler parameter while assuming exception types stay unchanged.

### 14.1. BindingResult always sits right next to the argument

Correct:

```java
void submit(
        @Valid @ModelAttribute SignupForm form,
        BindingResult result) {
}
```

Incorrect:

```java
void submit(
        @Valid @ModelAttribute SignupForm form,
        @RequestParam String source,
        BindingResult result) {
}
```

These two snippets are **illustrative** method signatures, not standalone compilable files. `BindingResult` must appear **immediately after** the object it describes. Placing it elsewhere can cause argument-resolution failures instead of passing errors to the controller.

## 15. Testing errors goes beyond HTTP status

A test that only checks:

```java
.andExpect(status().isBadRequest())
```

is not enough to prove constructor binding works properly. HTTP 400 can come from:

- `@NotNull` for a missing field.
- `@NotBlank` for null/blank input.
- `typeMismatch` when a string cannot convert to a number.
- JSON parser failing to read the request.
- Unsupported content-type or another missing parameter.
- A custom exception from a constructor.

Therefore, for each scenario, tests should assert:

- Response-level `code` such as `VALIDATION_ERROR` / `INVALID_JSON`.
- The exact `field` indicated, especially with `@BindParam`.
- `FieldError#getCode()` or a stable business error code.
- Error count when multiple required fields are missing.
- Success output when data is complete.
- Optional data not causing rejection.
- Extra input not populating privileged fields.

### 15.1. Avoid depending on provider ordering

`BindingResult#getFieldErrors()` should not be interpreted as "the first error in record declaration order". If the HTTP contract requires ordering, sort in the adapter. In the demo, `ErrorMapper` sorts by `field` then `code`, and only then do tests index `errors[0]`/`errors[1]`.

### 15.2. One field with multiple constraints

If you declare:

```java
@NotBlank
@Size(min = 3, max = 30)
String displayName
```

and the client sends `" "`, both `NotBlank` and `Size` can fire. Do not use a `Map<String,String>` that overwrites errors on the same field if all errors must be surfaced. Return a `List<FieldIssue>` or define an explicit rule priority (e.g., required before length).

### 15.3. Test by "missing" state rather than always relying on message text

For `@NotNull`/`@NotBlank`, default messages can be interpolated by locale/provider. Assert stable codes and fields; i18n message testing belongs in a separate test suite when the product has a translation contract. Do not hardcode English text like `"must not be blank"` in every constructor-binding test.

## 16. Common mistakes in real Spring projects

**1. Thinking records automatically require every field.** Records have no setters, yet the canonical constructor can still receive null reference components.

**2. Missing @NotNull on Integer.** `@Min`/`@Max` do not forbid null by themselves; an object missing age might not be rejected.

**3. Using int when needing to distinguish "not sent" from "sent 0".** Primitives have no null, creating ambiguous semantics to test.

**4. Testing only the complete form.** Misses missing-field, blank-field, and type-conversion issues.

**5. Assuming @RequestParam(required=true) applies automatically to record components.** `@ModelAttribute` is a different binding mechanism.

**6. Relying on DataBinder#setRequiredFields for constructor binding.** The 6.1 Javadoc restricts this option to `bind(PropertyValues)`, not `construct(...)`.

**7. Expecting Bean Validation to catch malformed JSON syntax.** If deserialization fails, there is no object yet to validate.

**8. Confusing @BindParam with Jackson @JsonProperty.** An annotation customizing request parameter names for Spring's constructor binder does not govern JSON property names.

**9. Misplacing BindingResult.** It must be immediately adjacent to the `@ModelAttribute` argument.

**10. Assuming type-mismatch errors are always @NotNull.** Conversion failures have their own mechanism, such as `typeMismatch` or object-creation exceptions.

**11. Throwing IllegalArgumentException in a compact constructor while expecting @Valid to return all errors.** The constructor can abort object creation before validation runs.

**12. Binding directly onto JPA entities.** Risks mass assignment; use dedicated input DTO records/allowlists and authorization.

**13. Including privileged fields in the record.** Immutability does not stop a client from supplying role/ownerId if they are constructor parameters.

**14. Using @Email and assuming email is required.** `@Email` allows null; if required, add `@NotBlank`.

**15. Forgetting @Valid on the handler.** Constraint annotations on DTOs do not run automatically in every situation.

**16. Using javax.validation with Spring Boot 3.** Boot 3 uses the Jakarta namespace.

**17. Asserting only HTTP 400.** Does not tell whether it came from Bean Validation, conversion, or parsing.

**18. Hardcoding English messages from the provider.** Default messages vary by locale/version; assert field/code.

**19. Treating nested @Valid as @NotNull.** `@Valid` cascades when the object is present; null must be blocked separately if required.

**20. Relying on implicit @ModelAttribute in native images.** Declare it explicitly for better AOT reflection hints.

**21. Forgetting the -parameters flag for regular constructor-bound Java classes.** Spring 6.1 no longer reads local variable tables in the legacy way to infer parameter names.

**22. Adding direct method constraints while assuming exception types stay the same.** Spring MVC 6.1 has dedicated method validation.

**23. Returning FieldError#getRejectedValue() in JSON APIs.** Can leak sensitive data.

**24. Calling setAllowedFields and thinking it blocks unwanted constructor arguments.** Allowed fields mainly restrict property binding; the constructor input shape must be designed cleanly.

**25. Equating HTTP form params with JSON.** Jackson and WebDataBinder have different conversions, aliases, and failure modes.

## 17. Code review checklist for constructor-binding tests

1. Is the DTO a dedicated input record containing only client-controllable fields?
2. Is `@ModelAttribute` explicitly declared for form/query binding?
3. Does the record have a simple canonical constructor that avoids throwing when multiple input errors need collection?
4. Do required reference components have appropriate `@NotNull`/`@NotBlank` annotations?
5. Is there a clear distinction between `@Min` allowing null and `@Email` allowing null?
6. Are missing keys tested separately from empty keys, whitespace, and wrong types?
7. Is there a test confirming missing optional components remain valid?
8. Is the `@BindParam` alias tested using the actual input parameter name?
9. Are wrong aliases and extra inputs tested?
10. Does `BindingResult` sit immediately next to the validated argument?
11. Do endpoints without `BindingResult` have an accurate `MethodArgumentNotValidException` handler?
12. Do JSON endpoints have separate tests for incomplete/null/malformed payloads?
13. Is `DataBinder#setRequiredFields` avoided as a constructor requirement mechanism?
14. If `declarativeBinding` is used, is it understood that it does not alter constructor parameter allowlists?
15. Is `-parameters` configured and tested on the actual Spring Framework version?
16. Is sensitive data filtered out when constructing error responses?
17. Is error ordering tested deterministically if JSON array order is part of the contract?
18. For nested records, are `@Valid` and `@NotNull` placed at the right levels?
19. If validation groups exist, are Create/Update tested independently?
20. If method validation exists, is `HandlerMethodValidationException` classified properly?
21. Are JPA entities avoided as request DTOs merely for mapping convenience?
22. When upgrading Boot/Jackson, are regression tests run for missing creator properties?

**Conclusion:** Testing constructor binding with records must prove both **object creation from valid input** and **correct behavior for missing or invalid data**. Immutable records do not automatically make every field mandatory; `@NotBlank`/`@NotNull` express the required contract when using Bean Validation. `@ModelAttribute` and `@RequestBody` construct objects via different mechanisms. Test the two paths separately, assert error types and fields, keep `BindingResult` in the right position, guard against extra input, and avoid relying on unverified implicit defaults.

## 18. References

- [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): primary constructor binding, `@BindParam`, `BindingResult`, and validation.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html): `DataBinder.construct`, nested constructor binding, conversion errors.
- [Spring Framework — MVC Data Binding and Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html): immutable DTOs and constructor binding for data safety.
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): `declarativeBinding` and allowed fields.
- [Spring Framework 6.1 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html): `construct` and limitations of `setRequiredFields`.
- [Spring Framework 6.1 — BindParam Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/bind/annotation/BindParam.html): input name for constructor parameters.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException` and `HandlerMethodValidationException`.
- [Spring Framework 6.1 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes): constructor binding and `-parameters`.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): `@NotNull`, `@NotBlank`, `@Valid`, and validation groups.
