# `BindingResult` Misplaced in Controller Signature: Diagnosing and Fixing Spring MVC Errors

## 1. Symptom: `BindingResult` Is Declared Yet the Controller Still Does Not Receive Errors

In Spring MVC, a handler can receive an object bound from the request and read errors via `BindingResult` or `Errors`. **Correctly positioned** syntax:

```java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("form") RegisterForm form,
        BindingResult result,
        Model model) {

    if (result.hasErrors()) {
        return "register-form";
    }
    return "success";
}
```

This is a **controller fragment**; classes/imports depend on the actual application. `BindingResult` stands **immediately after** the `form` argument.

A very similar-looking yet **wrong** signature:

```java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("form") RegisterForm form,
        Model model,
        BindingResult result) {

    if (result.hasErrors()) {
        return "register-form";
    }
    return "success";
}
```

The issue is that `Model model` is inserted in between. Spring MVC **does not use the parameter name** `result` to guess that it belongs to `form`, nor does it automatically move the parameter to a valid position. According to Spring MVC 6.2 documentation, `Errors`/`BindingResult` must be declared **immediately after the validated/bound method argument** it describes.

Consequences vary depending on argument type, data, and version/configuration:

- When an argument fails validation/binding and **lacks** a `BindingResult` immediately next to it, Spring typically switches to an exception path such as `MethodArgumentNotValidException`, preventing the handler from receiving control and returning HTTP 400 or a response handled by `@ControllerAdvice`.
- When Spring has to resolve a `BindingResult` separated from its argument, `ErrorsMethodArgumentResolver` may fail to find the expected binding result at the model position it anticipates, raising an `IllegalStateException` about declaring `Errors/BindingResult` directly after the model attribute.
- If the signature also has **direct constraints** on method parameters, Spring MVC 6.1+ may use **method validation** and `HandlerMethodValidationException`; do not diagnose every HTTP 400 as the same error.
- If a JSON request body cannot be read, Jackson/HTTP message converter may throw `HttpMessageNotReadableException` **before the Bean Validation step**; even placing `BindingResult` correctly will not turn a JSON syntax error into a field error on a valid DTO.

**Article focus:** the bug is in **parameter ordering inside the controller signature**, not a missing Jakarta Validation dependency, not a mistyped `@NotBlank`, and not a message-translation failure. To fix it, place `BindingResult` (or `Errors`) **right after the object** whose binding/validation result you want to receive.

This article belongs to the **Diagnostics** section of the **Spring Framework — validation-data-binding** module. Examples use Java 17+, Spring Boot 3.4.5, Spring Framework 6.x, Jakarta Validation, and MockMvc.

## 2. The Official Spring MVC Rule

### One-Sentence Rule

**`Errors` or `BindingResult` must stand immediately after the argument it describes.**

| Argument receiving errors | Correct position | Example |
| --- | --- | --- |
| `@ModelAttribute` | Immediately after the model attribute | `@Valid @ModelAttribute("form") Form form, BindingResult result` |
| `@RequestBody` | Immediately after the body object | `@Valid @RequestBody Input input, BindingResult result` |
| `@RequestPart` | Immediately after the part object | `@Valid @RequestPart("meta") Meta meta, Errors errors` |
| Multiple `@ModelAttribute`s | Each object has its own adjacent result | `FormA a, BindingResult aErrors, FormB b, BindingResult bErrors` |
| No need to read errors in handler | BindingResult may be omitted | Let Spring exception resolver handle errors |
| Direct `@Min`/`@NotBlank` error on method parameter | Depends on method validation | May require handling `HandlerMethodValidationException` |

**Do not insert between them** any `Model`, `Locale`, `Principal`, `HttpServletRequest`, `@RequestParam`, `@RequestHeader`, or another DTO, even though all of those arguments are valid when placed **after** `BindingResult`.

### 2.1. Exact Ordering Example

Correct:

```java
public ResponseEntity<?> save(
        @Valid @ModelAttribute("account") AccountForm account,
        BindingResult errors,
        @RequestParam(defaultValue = "web") String source,
        Locale locale) {
    // ...
}
```

Wrong:

```java
public ResponseEntity<?> save(
        @Valid @ModelAttribute("account") AccountForm account,
        @RequestParam(defaultValue = "web") String source,
        BindingResult errors,
        Locale locale) {
    // ...
}
```

Simply move `source` **after** `errors`. There is no need to remove `@RequestParam` or `Locale`; just follow the ordering rule.

### 2.2. How Do `Errors` and `BindingResult` Differ?

`org.springframework.validation.Errors` defines operations for inspecting/recording errors, such as:

- `hasErrors()`.
- `getAllErrors()`.
- `getFieldErrors()`.
- `getGlobalErrors()`.
- `reject(...)` / `rejectValue(...)`.

`org.springframework.validation.BindingResult` **extends** `Errors`, adding binder-related metadata such as:

- `getTarget()`.
- `getRawFieldValue(...)`.
- `getFieldValue(...)`.
- `getSuppressedFields()`.
- `getModel()`.

A signature can use:

```java
@Valid @ModelAttribute("form") Form form,
Errors errors
```

or:

```java
@Valid @ModelAttribute("form") Form form,
BindingResult errors
```

Both **must be in the adjacent position**. Changing the parameter type from `BindingResult` to `Errors` will not fix a misordered signature.

### 2.3. `@Valid` Does Not Make Positioning Flexible

`@Valid` triggers post-binding validation when an appropriate provider/configuration exists; it **does not assign a target** to a `BindingResult` placed arbitrarily in the signature. If the handler needs to handle errors itself, `BindingResult` must still stand immediately after the object.

Conversely, even without `@Valid`, data binding can still produce **type conversion** errors such as `age=abc` for `Integer age`. Placing `BindingResult` properly remains essential if the handler needs to inspect binding failures.

## 3. Why Does Spring Require Adjacency?

Spring MVC resolves parameters using a chain of **HandlerMethodArgumentResolver**s. Each parameter is evaluated by its type/annotations and its position in the method signature.

For `@ModelAttribute`:

```text
HTTP request parameters
        |
        v
ModelAttributeMethodProcessor / ServletModelAttributeMethodProcessor
        |
        v
Create or retrieve command object
        |
        v
WebDataBinder binds and converts values
        |
        v
@Valid / @Validated if declared
        |
        v
BindingResult holds binding + validation errors
        |
        +--> Is the NEXT parameter Errors/BindingResult?
                 | Yes -> pass BindingResult to handler
                 | No  -> errors may follow the exception path
```

For `@RequestBody`:

```text
HTTP JSON body
        |
        v
HttpMessageConverter / Jackson
        |
        v
Create DTO from JSON (if parseable)
        |
        v
RequestResponseBodyMethodProcessor applies validation
        |
        +--> Is the next parameter Errors/BindingResult?
                 | Yes -> handler receives body and errors
                 | No  -> validation failure may throw
                            MethodArgumentNotValidException
```

The two pipelines are **not identical**: one uses property/constructor binding from request parameters, while the other uses deserialization via an HTTP message converter. Yet the rule **place result immediately after the object** applies wherever Spring supports local error handling.

### 3.1. Spring Does Not "Look Up by Variable Name `result`"

In Java, parameter names can be renamed, stripped, or retained by the compiler depending on configuration. The name `result` has no special meaning:

```java
@Valid @ModelAttribute("form") Form x,
BindingResult whateverName
```

Still works if the two parameters are adjacent. Conversely, placing a variable named `formErrors` at the end of the method is still wrong even though the name clearly suggests its owner.

### 3.2. Ordering Does Not Depend on Whether Errors Occur

A misordered signature can behave differently when:

- The request has validation errors.
- The request is completely valid.
- The request hits a type conversion error.
- The controller adds another `@ModelAttribute` in between.
- The application enables method validation or custom argument resolvers.

Therefore, do not test only "valid form returns 200." A test with invalid data is necessary to distinguish between **the controller handling errors locally** and **Spring throwing an exception before entering the controller**.

### 3.3. `BindingResult` in the Model

Spring MVC stores model attribute metadata under a conventional key:

```java
String key = BindingResult.MODEL_KEY_PREFIX + "form";
```

This is a **fragment**; the prefix value is published by Spring via a constant, yielding a key like `org.springframework.validation.BindingResult.form`.

When multiple model attributes exist, multiple binding result entries can exist. However, **do not assume** Spring will use Map keys to locate a `BindingResult` argument placed at an arbitrary position. The contract for handler arguments remains **adjacency**.

## 4. Recognizing the Bug Through Common Misordered Signatures

### 4.1. `Model` Inserted Between Form and `BindingResult`

Wrong:

```java
@PostMapping("/profile")
public String update(
        @Valid @ModelAttribute("profile") ProfileForm form,
        Model model,
        BindingResult errors) {
    // ...
    return "profile";
}
```

Correct:

```java
@PostMapping("/profile")
public String update(
        @Valid @ModelAttribute("profile") ProfileForm form,
        BindingResult errors,
        Model model) {
    if (errors.hasErrors()) {
        return "profile";
    }
    return "redirect:/profile";
}
```

`Model` is used to pass data to the view, not the form's `Errors`; `Model` can be placed after the result.

### 4.2. `Locale` or `Principal` Inserted in Between

Wrong:

```java
public String submit(
        @Valid @ModelAttribute("form") SignupForm form,
        Locale locale,
        BindingResult errors) {
    // ...
    return "done";
}
```

Correct:

```java
public String submit(
        @Valid @ModelAttribute("form") SignupForm form,
        BindingResult errors,
        Locale locale) {
    // ...
    return "done";
}
```

Even though `Locale` is language metadata unrelated to the form, it still must not be inserted between the object and its binding result.

### 4.3. `@RequestParam` Inserted in Between

Wrong:

```java
public String submit(
        @Valid @ModelAttribute("form") SignupForm form,
        @RequestParam String source,
        BindingResult errors) {
    // ...
    return "done";
}
```

Correct:

```java
public String submit(
        @Valid @ModelAttribute("form") SignupForm form,
        BindingResult errors,
        @RequestParam String source) {
    // ...
    return "done";
}
```

The order of parameters **that are not the validated data object** can be flexible, as long as the object/result pair stays adjacent.

### 4.4. Two DTOs, Only One `BindingResult` at the End

Wrong:

```java
public String save(
        @Valid @ModelAttribute("profile") ProfileForm profile,
        @Valid @ModelAttribute("contact") ContactForm contact,
        BindingResult errors) {
    // ...
    return "done";
}
```

Do not assume `errors` at the end aggregates both objects. If `profile` has errors, it **has no immediately adjacent result**, so Spring may throw an exception before processing the second object.

Correct:

```java
public String save(
        @Valid @ModelAttribute("profile") ProfileForm profile,
        BindingResult profileErrors,
        @Valid @ModelAttribute("contact") ContactForm contact,
        BindingResult contactErrors) {

    if (profileErrors.hasErrors() || contactErrors.hasErrors()) {
        return "edit";
    }
    return "done";
}
```

**Each object has its own result**; do not merge two objects into a single BindingResult. If you need one response containing errors from both, combine the data **after Spring has populated both BindingResults properly**.

### 4.5. JSON `@RequestBody` with an Intervening Parameter

Wrong:

```java
@PostMapping("/api/signup")
public ResponseEntity<?> create(
        @Valid @RequestBody SignupRequest request,
        @RequestHeader("X-Client") String client,
        BindingResult errors) {
    // ...
    return ResponseEntity.ok().build();
}
```

Correct:

```java
@PostMapping("/api/signup")
public ResponseEntity<?> create(
        @Valid @RequestBody SignupRequest request,
        BindingResult errors,
        @RequestHeader("X-Client") String client) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }
    return ResponseEntity.ok().build();
}
```

Spring MVC supports `BindingResult` immediately after `@RequestBody` for **validation errors of an object that has already been deserialized**. It is not a way to catch **malformed JSON**, missing required body, or unsupported media type, because those errors occur **before a valid DTO object exists**.

### 4.6. `@RequestPart` with Multipart JSON Metadata

Correct:

```java
@PostMapping(
        path = "/files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> upload(
        @Valid @RequestPart("metadata") UploadMetadata metadata,
        BindingResult metadataErrors,
        @RequestPart("file") MultipartFile file) {

    if (metadataErrors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }
    return ResponseEntity.ok().build();
}
```

This is a **fragment**; it needs controller imports and an appropriate `UploadMetadata` class. `@RequestPart` uses message conversion to read complex parts; validation errors can be handled via a result immediately following the part object.

Placing `MultipartFile file` between `metadata` and `metadataErrors` again violates the adjacency rule. Although named multipart parts may arrive in any order in the HTTP request, **the order of Java method arguments must still be right**.

### 4.7. `Errors` as the First Method Parameter

Wrong:

```java
public String save(
        BindingResult errors,
        @Valid @ModelAttribute("form") Form form) {
    // ...
    return "done";
}
```

Errors is not "immediately after" any object; Spring cannot use it as an error holder for the object after it. Put the object first, Errors right after.

## 5. Exceptions to Distinguish During Diagnosis

| Scenario | Typical exception/behavior | What to check |
| --- | --- | --- |
| `@Valid @ModelAttribute` invalid, no adjacent result | `MethodArgumentNotValidException` in modern MVC | Method signature and handler advice |
| `@Valid @RequestBody` invalid, no adjacent result | `MethodArgumentNotValidException` | Is the body DTO readable? |
| `@Valid @RequestPart` invalid, no adjacent result | `MethodArgumentNotValidException` | Multipart structure / part JSON |
| `BindingResult` misplaced and resolver cannot find result | Possible `IllegalStateException` | Method parameter position, nearby model attributes |
| Direct method constraints like `@Min` on `@RequestParam` | `HandlerMethodValidationException` (Spring MVC 6.1+) | Are constraints on the method signature? |
| Unreadable JSON syntax/type | `HttpMessageNotReadableException` | Message converter, not BindingResult |
| Unsupported Content-Type | `HttpMediaTypeNotSupportedException` | Content-Type and consumes |
| Missing Bean Validation provider | Constraints may not run as expected | Validation dependency/configuration |
| Missing `@Valid`/`@Validated` | Jakarta constraints may not be executed | Trigger validation |
| Binding failure with result properly present | Handler receives `BindingResult` | Inspect `isBindingFailure()` and field errors |

**Do not assert that every misplacement case throws the exact same `IllegalStateException`.** The path depends on the argument resolver involved, whether the object has errors, whether method validation is active, and registered handlers/advice. Several errors occur **before the controller method is invoked**; do not rely solely on a breakpoint at the start of the controller to conclude "the validator did not run."

### 5.1. When Does `MethodArgumentNotValidException` Appear?

In Spring MVC 6.x per-argument validation, a `@ModelAttribute`, `@RequestBody`, or `@RequestPart` with `@Valid`/`@Validated` and no `Errors/BindingResult` immediately after it may throw `MethodArgumentNotValidException` when validation fails. The default response is typically **400 Bad Request**, unless customized by an exception resolver/advice.

**Diagnostic pitfall:** a developer sees `BindingResult result` at the end of the signature and assumes it surely prevents the exception. Incorrect—Spring checks the **next parameter** right after the validated argument.

### 5.2. When Does `HandlerMethodValidationException` Appear?

Since Spring Framework 6.1, MVC supports built-in **method validation** when a method has direct constraint annotations such as:

```java
@GetMapping("/search")
public ResponseEntity<?> find(
        @RequestParam @Min(1) int page) {
    return ResponseEntity.ok().build();
}
```

This is a fragment. With `page=0`, `@Min(1)` is directly on the method parameter and can trigger `HandlerMethodValidationException`. Method validation can **replace** individual-argument validation and also cover nested constraints via `@Valid`.

Spring may still invoke the controller when **all** method-validation errors are on method parameters with `Errors` immediately following them and are handled locally. If other unhandled errors exist, the exception is still thrown. A class-level `@Validated` may switch to AOP method validation; check the exact configuration/version.

**Practical rule:** applications using both DTO validation and direct parameter constraints should design exception handling for both `MethodArgumentNotValidException` and `HandlerMethodValidationException`, while still placing `BindingResult` in the proper position wherever used.

### 5.3. Malformed JSON Produces No Useful `BindingResult` for the Body

Example of an invalid request body:

```text
{"email":,}
```

The message converter cannot construct a valid DTO for Jakarta Validator to run on. A `BindingResult` after `@RequestBody` cannot handle this parsing error. Use `@RestControllerAdvice`/`ResponseEntityExceptionHandler#handleHttpMessageNotReadable(...)` for that case.

### 5.4. Validation Errors Differ from Conversion Errors

With form-urlencoded:

```text
age=not-a-number
```

If the DTO has `Integer age`, the binder can record a `FieldError` with `isBindingFailure() == true`. With a JSON body containing `"age":"not-a-number"`, Jackson may fail to deserialize it into an Integer and throw `HttpMessageNotReadableException`.

The two pipelines can produce different API error codes. Do not assume every 400 comes from `result.getFieldErrors()`; and do not attribute a `@Min` constraint to a failure that occurred before type conversion succeeded.

## 6. Runnable Java 17 Demo: Three Valid Controller Declarations

The following Maven project demonstrates:

1. `@Valid @ModelAttribute` with `BindingResult` immediately after.
2. `@Valid @RequestBody` with `BindingResult` immediately after.
3. Two `@ModelAttribute`s in the same handler, each with its own `BindingResult`.
4. Intentionally **omitting** `BindingResult` with invalid data so errors route to `@RestControllerAdvice`.
5. Unreadable JSON routed to its own handler.
6. Valid data passes through; invalid data is classified without exposing rejected values.

**Why doesn't the demo put a broken signature directly into the main running controller?** An invalid handler signature can make outcomes depend on resolver order and input data, muddying the lesson. We keep a working project; the anti-patterns in Section 4 serve as comparison fragments, and Section 9 describes how to write regression tests to prevent recurrence.

### 6.1. Directory Structure

```text
binding-result-order-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── BindingResultOrderApplication.java
    │   ├── SignupForm.java
    │   ├── SignupJson.java
    │   ├── ProfileForm.java
    │   ├── ContactForm.java
    │   ├── InputError.java
    │   ├── SignupController.java
    │   └── InputErrorAdvice.java
    └── test/java/demo/
        └── BindingResultOrderMvcTest.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>binding-result-order-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

`spring-boot-starter-validation` is required for the Jakarta Validation provider in Boot 3.x. The Maven parent manages dependency versions; `spring-boot-starter-test` provides JUnit 5/MockMvc. No database is needed: the lesson focuses on **argument binding and validation routing**.

### 6.3. `src/main/java/demo/BindingResultOrderApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingResultOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                BindingResultOrderApplication.class, args);
    }
}
```

### 6.4. `src/main/java/demo/SignupForm.java`

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

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
```

This is a JavaBean used for `@ModelAttribute`. With `application/x-www-form-urlencoded` requests, `name=` triggers a `@NotBlank` violation, `age=abc` can trigger a type conversion error, and `age=16` triggers a `@Min` violation.

### 6.5. `src/main/java/demo/SignupJson.java`

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record SignupJson(
        @NotBlank String name,
        @NotBlank @Email String email,
        @NotNull @Min(18) Integer age) {
}
```

This is a record for `@RequestBody`. Jackson deserializes JSON into an object before Spring applies Bean Validation. Place `@Valid` on the method parameter to trigger constraints on the record.

### 6.6. `src/main/java/demo/ProfileForm.java`

```java
package demo;

import jakarta.validation.constraints.NotBlank;

public class ProfileForm {

    @NotBlank
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

### 6.7. `src/main/java/demo/ContactForm.java`

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public class ContactForm {

    @NotBlank
    @Email
    private String contactEmail;

    public String getContactEmail() {
        return contactEmail;
    }

    public void setContactEmail(String contactEmail) {
        this.contactEmail = contactEmail;
    }
}
```

The two forms in sections 6.6–6.7 have **distinct field names** so they can receive request parameters together without conflict. They have separate `BindingResult` parameters in the handler; an error on `profile` is not silently merged into `contact`.

### 6.8. `src/main/java/demo/InputError.java`

```java
package demo;

import java.util.Comparator;
import java.util.List;

import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

public record InputError(
        String code,
        List<FieldIssue> fields,
        int objectErrors) {

    public record FieldIssue(String field, String kind) {
    }

    public static InputError from(
            String code, BindingResult result) {

        List<FieldIssue> issues = result.getFieldErrors()
                .stream()
                .map(e -> new FieldIssue(
                        e.getField(),
                        e.isBindingFailure()
                                ? "TYPE_MISMATCH"
                                : "CONSTRAINT_VIOLATION"
                ))
                .sorted(Comparator
                        .comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::kind))
                .toList();

        return new InputError(
                code, issues, result.getGlobalErrorCount());
    }
}
```

`InputError` exposes only:

- `code`: application code such as `FORM_INVALID`, `JSON_INVALID`, or `AUTO_VALIDATION_FAILED`.
- `fields[]`: field name and generic error category.
- `objectErrors`: whole-object error count, illustrating that global errors should not be ignored.

Do not serialize raw `FieldError`, `getRejectedValue()`, stack traces, or converter messages. For a production API you can add detailed codes per constraint, localization, or `ProblemDetail`; here, this is sufficient to verify routing and adjacency.

### 6.9. `src/main/java/demo/SignupController.java`

```java
package demo;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SignupController {

    @PostMapping(
            path = "/forms/signup",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> formSignup(
            @Valid @ModelAttribute("signupForm")
                    SignupForm form,
            BindingResult errors,
            @RequestParam(
                    name = "source",
                    defaultValue = "browser")
                    String source) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(InputError.from(
                            "FORM_INVALID", errors));
        }

        return ResponseEntity.ok(Map.of(
                "status", "accepted",
                "source", source));
    }

    @PostMapping(
            path = "/json/signup",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> jsonSignup(
            @Valid @RequestBody SignupJson request,
            BindingResult errors,
            @RequestHeader(
                    name = "X-Client",
                    required = false)
                    String client) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(InputError.from(
                            "JSON_INVALID", errors));
        }

        return ResponseEntity.ok(Map.of(
                "status", "accepted"));
    }

    @PostMapping(
            path = "/forms/paired",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> pairedForms(
            @Valid @ModelAttribute("profile")
                    ProfileForm profile,
            BindingResult profileErrors,
            @Valid @ModelAttribute("contact")
                    ContactForm contact,
            BindingResult contactErrors) {

        if (profileErrors.hasErrors()
                || contactErrors.hasErrors()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "PAIRED_INVALID",
                    "profileErrors",
                            profileErrors.getErrorCount(),
                    "contactErrors",
                            contactErrors.getErrorCount()
            ));
        }

        return ResponseEntity.ok(Map.of(
                "status", "accepted"));
    }

    // No local BindingResult:
    // Spring will follow the exception path when validation fails.
    @PostMapping(
            path = "/forms/automatic",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> formAutomatic(
            @Valid @ModelAttribute("signupForm")
                    SignupForm form) {

        return ResponseEntity.ok(Map.of(
                "status", "accepted"));
    }

    @PostMapping(
            path = "/json/automatic",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> jsonAutomatic(
            @Valid @RequestBody SignupJson request) {

        return ResponseEntity.ok(Map.of(
                "status", "accepted"));
    }
}
```

**Points to examine in the signatures:**

- `formSignup`: right after `SignupForm form` comes **`BindingResult errors`**, and only then `@RequestParam source`.
- `jsonSignup`: right after `SignupJson request` comes **`BindingResult errors`**, followed by `@RequestHeader X-Client`. Adding the header does not alter the request/errors pair.
- `pairedForms`: two adjacent pairs **`ProfileForm / profileErrors`** and **`ContactForm / contactErrors`**. Errors do not merge into one.
- `formAutomatic` and `jsonAutomatic` **have no BindingResult** to intentionally illustrate Spring routing validation errors to `MethodArgumentNotValidException`; this is a valid choice when centralizing error handling in advice.
- `ResponseEntity<?>` allows returning different bodies on the success and error branches; production code may choose a more strongly typed response schema.

**Do not mix the two strategies:** an endpoint can either handle errors right inside the controller via BindingResult, or let global advice handle the validation exception. Both are valid. The bug happens when you **intend local handling yet misorder the result**, causing Spring not to treat it as the DTO's immediate partner.

### 6.10. `src/main/java/demo/InputErrorAdvice.java`

```java
package demo;

import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler;

@RestControllerAdvice
public class InputErrorAdvice
        extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object>
            handleMethodArgumentNotValid(
                    MethodArgumentNotValidException ex,
                    HttpHeaders headers,
                    HttpStatusCode status,
                    WebRequest request) {

        return new ResponseEntity<>(
                InputError.from(
                        "AUTO_VALIDATION_FAILED",
                        ex.getBindingResult()),
                headers,
                status);
    }

    @Override
    protected ResponseEntity<Object>
            handleHttpMessageNotReadable(
                    HttpMessageNotReadableException ex,
                    HttpHeaders headers,
                    HttpStatusCode status,
                    WebRequest request) {

        return new ResponseEntity<>(
                Map.of("code", "UNREADABLE_BODY"),
                headers,
                status);
    }
}
```

Spring MVC's `ResponseEntityExceptionHandler` provides built-in integration for many web exceptions. Override the two methods above to **set the response code/schema** for:

- `MethodArgumentNotValidException`: DTO parsed successfully, but binding/validation failed and the handler lacks a properly positioned local result.
- `HttpMessageNotReadableException`: JSON request could not be read/deserialized.

Do not declare an extra `@ExceptionHandler(MethodArgumentNotValidException.class)` overlapping `ResponseEntityExceptionHandler`'s built-in method in the same advice without understanding the mapping, as it can cause ambiguity. Overriding is appropriate for this example.

## 7. MockMvc Tests: Proving `result` Attaches to the Right Object

### 7.1. `src/test/java/demo/BindingResultOrderMvcTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BindingResultOrderMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidFormIsHandledLocally() throws Exception {
        mvc.perform(post("/forms/signup")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "")
                        .param("email", "lan@example.org")
                        .param("age", "22"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("FORM_INVALID"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("name"))
                .andExpect(jsonPath("$.fields[0].kind")
                        .value("CONSTRAINT_VIOLATION"));
    }

    @Test
    void formBindingTypeFailureIsAvailableLocally()
            throws Exception {
        mvc.perform(post("/forms/signup")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("email", "lan@example.org")
                        .param("age", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("FORM_INVALID"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("age"))
                .andExpect(jsonPath("$.fields[0].kind")
                        .value("TYPE_MISMATCH"));
    }

    @Test
    void validFormCanHaveRequestParamAfterBindingResult()
            throws Exception {
        mvc.perform(post("/forms/signup")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("email", "lan@example.org")
                        .param("age", "22")
                        .param("source", "mobile"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"))
                .andExpect(jsonPath("$.source")
                        .value("mobile"));
    }

    @Test
    void invalidJsonIsHandledLocally() throws Exception {
        mvc.perform(post("/json/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {"name":"","email":"lan@example.org",
                             "age":22}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("JSON_INVALID"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("name"));
    }

    @Test
    void validJsonCanHaveHeaderAfterBindingResult()
            throws Exception {
        mvc.perform(post("/json/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("X-Client", "mobile")
                        .content("""
                            {"name":"Lan","email":"lan@example.org",
                             "age":22}
                            """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }

    @Test
    void malformedJsonIsHandledByConverterAdvice()
            throws Exception {
        mvc.perform(post("/json/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":,}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }

    @Test
    void eachOfTwoFormsOwnsItsBindingResult()
            throws Exception {
        mvc.perform(post("/forms/paired")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "")
                        .param("contactEmail", "not-an-email"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("PAIRED_INVALID"))
                .andExpect(jsonPath("$.profileErrors")
                        .value(1))
                .andExpect(jsonPath("$.contactErrors")
                        .value(1));
    }

    @Test
    void bothFormsCanBeValid() throws Exception {
        mvc.perform(post("/forms/paired")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Lan")
                        .param("contactEmail", "lan@example.org"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }

    @Test
    void formWithoutBindingResultUsesAdvice()
            throws Exception {
        mvc.perform(post("/forms/automatic")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "")
                        .param("email", "lan@example.org")
                        .param("age", "22"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("AUTO_VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("name"));
    }

    @Test
    void jsonWithoutBindingResultUsesAdvice()
            throws Exception {
        mvc.perform(post("/json/automatic")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {"name":"","email":"lan@example.org",
                             "age":22}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("AUTO_VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("name"));
    }

    @Test
    void automaticHandlerAlsoAcceptsValidJson()
            throws Exception {
        mvc.perform(post("/json/automatic")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {"name":"Lan","email":"lan@example.org",
                             "age":22}
                            """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }
}
```

These are **11 integration tests** using a real Spring Boot context:

1. Form with constraint error → local `BindingResult` returns `FORM_INVALID`.
2. Form with type conversion error → local `BindingResult` contains `TYPE_MISMATCH`.
3. Valid form → `@RequestParam` after the result resolves normally.
4. JSON constraint error → local `BindingResult` returns `JSON_INVALID`.
5. Valid JSON → `@RequestHeader` after the result works properly.
6. Malformed JSON → dedicated handler returns `UNREADABLE_BODY`, not confused with constraints.
7. Two invalid forms → each object owns its result, with two independent error counts.
8. Two valid forms → controller processes successfully.
9. Form without BindingResult → `MethodArgumentNotValidException` is converted by advice to `AUTO_VALIDATION_FAILED`.
10. JSON without BindingResult → same advice path.
11. Valid JSON without BindingResult → controller processes normally.

**Note:** the tests above verify **valid signatures** and the local/advice distinction. To test that a misordered signature produces a specific error, use a separate isolated test controller, because the exception type and resolution behavior can vary across Spring versions.

### 7.2. Running Tests and Server

From the `binding-result-order-demo` directory on a machine with JDK 17+ and Maven:

```bash
mvn -q clean test
```

**Expected result:** 11 tests pass, Maven exit code 0 when dependencies are fully resolved and the environment is suitable. This is an expectation read from code, **not stdout from an executed build**.

Start the server:

```bash
mvn spring-boot:run
```

Send an invalid form:

```bash
curl -i -X POST 'http://localhost:8080/forms/signup' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'age=22'
```

HTTP 400 response matching the demo schema:

```json
{
  "code": "FORM_INVALID",
  "fields": [
    {
      "field": "name",
      "kind": "CONSTRAINT_VIOLATION"
    }
  ],
  "objectErrors": 0
}
```

Send JSON violating a constraint:

```bash
curl -i -X POST 'http://localhost:8080/json/signup' \
  -H 'Content-Type: application/json' \
  --data '{"name":"","email":"lan@example.org","age":22}'
```

Response:

```json
{
  "code": "JSON_INVALID",
  "fields": [
    {
      "field": "name",
      "kind": "CONSTRAINT_VIOLATION"
    }
  ],
  "objectErrors": 0
}
```

If `/json/signup` is replaced with `/json/automatic` using the same JSON, the advice returns code `AUTO_VALIDATION_FAILED`. That **does not prove the forms/DTOs differ**, it proves **where errors are handled** (local `BindingResult` vs. exception advice) changed.

### 7.3. Why Not Assert the Validator's Default Message?

Hibernate Validator may interpolate messages according to locale/resource bundles. Testing BindingResult ordering should focus on:

- HTTP status.
- **Application-defined codes**.
- Exact field errors.
- `isBindingFailure()` during type conversion.
- Whether the controller was invoked.
- Whether the exception advice was invoked.

Asserting the phrase "must not be blank" does not catch adjacency bugs as cleanly as asserting `FORM_INVALID` (local) versus `AUTO_VALIDATION_FAILED` (global).

## 8. Explaining Each Parameter Position in a Valid Method

Example:

```java
public ResponseEntity<?> save(
        @Valid @ModelAttribute("form") SignupForm form,
        BindingResult errors,
        @RequestParam String source,
        Model model,
        Locale locale) {
    // ...
}
```

Position 1 — `SignupForm`: Spring instantiates/binds the object and validates Jakarta constraints.

Position 2 — `BindingResult`: Spring injects the binding/validation result of the **immediately preceding** object into this argument.

Position 3 — `source`: Spring resolves the request parameter after processing the form/errors pair.

Position 4 — `Model`: Spring supplies the model for rendering without sitting between the form/errors pair.

Position 5 — `Locale`: Spring resolves the locale, which can be used to interpolate messages once the result is obtained.

You may reorder parameters in positions 3–5 relative to each other subject to other constraints, but **never separate positions 1–2**.

### 8.1. Multiple Result Pairs

```java
public ResponseEntity<?> save(
        @Valid @ModelAttribute("billing") BillingForm billing,
        BindingResult billingErrors,
        @Valid @ModelAttribute("shipping") ShippingForm shipping,
        BindingResult shippingErrors,
        Model model) {
    // ...
}
```

Each result belongs to the object directly before it. If `billing` has errors and `shipping` is valid, the handler can still be invoked to render both forms, provided both results are properly positioned and there are no validation errors outside local handler coverage.

### 8.2. Can `Model` Be Placed at the Start of the Method?

A signature like:

```java
public String save(
        Model model,
        @Valid @ModelAttribute("form") Form form,
        BindingResult errors) {
    // ...
    return "view";
}
```

still keeps `Form form, BindingResult errors` adjacent, satisfying this pair's ordering rule. `Model` does not always have to sit at the very end of the method. The exact rule is **no argument may come between the validated object and its corresponding result**.

## 9. Practical Step-by-Step Diagnosis

When the controller does not enter the `if (result.hasErrors())` branch as expected:

### Step 1 — Read the Entire Signature, Not Just Search for `BindingResult`

Ask:

- Which parameter has `@Valid`/`@Validated`?
- Is the bound object `@ModelAttribute`, `@RequestBody`, or `@RequestPart`?
- Is the **very next parameter** after the object of type `Errors`/`BindingResult`?
- Is a `Model`, `Locale`, `@RequestParam`, or `Principal` inserted in between?
- Are there multiple DTOs with only one BindingResult at the end?

If there is a misordering, fix the signature before digging into providers/constraints.

### Step 2 — Identify the Failure Phase

A request passes through:

```text
Request mapping
 -> Argument resolution
 -> Data binding / message conversion
 -> Validation
 -> Handler invocation (if eligible)
 -> Response rendering / exception handling
```

Place breakpoints/logs at appropriate points:

- `@RestControllerAdvice#handleMethodArgumentNotValid`.
- `handleHttpMessageNotReadable`.
- `@InitBinder` (if using form binding).
- Start of the controller method.
- `BindingResult#getFieldErrors()` after entering the handler.

If the controller is not called while the advice receives `MethodArgumentNotValidException`, inspect the parameter immediately following the DTO.

### Step 3 — Check Which Exception Type Occurred

- `MethodArgumentNotValidException`: a validated argument had errors not handled locally according to the signature.
- `HandlerMethodValidationException`: method-level constraints.
- `HttpMessageNotReadableException`: parsing/deserialization.
- `IllegalStateException` involving Resolver/BindingResult: signature/ability to locate the right binding result needs inspection.
- `HttpMediaTypeNotSupportedException`: Content-Type does not match the endpoint.

Do not change parameter order to fix a JSON syntax error, and do not alter advice to mask a broken signature.

### Step 4 — Verify the Intended Error-Handling Strategy

**Want the controller itself to re-render the form with errors:** use adjacent `@Valid @ModelAttribute form, BindingResult result` and return the form view.

**Want a REST API to return a uniform schema:** you can omit local BindingResult and use `@RestControllerAdvice`; then `MethodArgumentNotValidException` is intentional behavior, not a "missing BindingResult bug."

**Want controller-specific responses per error condition:** keep the pair adjacent and handle the result locally. Do not expect advice to catch every `MethodArgumentNotValidException` while also expecting the controller's local branch to run on the same request.

### Step 5 — Check Data, Provider, and Converter

If adjacency is already correct yet no errors appear:

- Does the DTO have constraints on fields/getters/record components?
- Does the method parameter have `@Valid` or `@Validated`?
- Is a Bean Validation implementation (e.g., Hibernate Validator from `spring-boot-starter-validation`) present?
- Is the request form params or a JSON body? Are the right annotations used?
- Does the form DTO have suitable constructors/setters/bindable properties?
- Does `@InitBinder` replace the validator or apply an overly strict `setAllowedFields`?
- Does JSON parse into the expected types?
- Are validation groups excluding constraints from the active group?
- Does the controller have direct method constraints shifting the exception path to `HandlerMethodValidationException`?

Correct ordering is a **necessary condition for a local result**, not a guarantee that constraints are active if provider/config is missing.

### Step 6 — Write a MockMvc Regression Test

Craft a request failing **a single field** and assert:

- HTTP 400.
- The expected **local handler** code, not the code from advice.
- The right field name.
- No rejected values exposed.
- A valid request still returns 200.

If the result was previously misplaced, such a test catches regressions if anyone later inserts `Locale` or `@RequestParam` between the pair.

## 10. `BindingResult` and Field Errors: Reading the Information Properly

Once inside the handler with a valid result:

```java
if (result.hasErrors()) {
    for (FieldError error : result.getFieldErrors()) {
        String field = error.getField();
        boolean bindingFailure = error.isBindingFailure();
        String springCode = error.getCode();
        String defaultMessage = error.getDefaultMessage();
    }
}
```

This is a fragment. Meaning:

- `getField()`: property path, e.g., `email` or `addresses[0].city`.
- `isBindingFailure()`: whether this was a binding/type conversion error.
- `getCode()` and `getCodes()`: Spring message lookup codes, not necessarily **stable API error codes**.
- `getDefaultMessage()`: fallback message; may already be interpolated by locale/provider.
- `getGlobalErrors()`: whole-object errors without a specific field path.
- `getSuppressedFields()`: fields excluded from property binding by WebDataBinder; does not automatically make `hasErrors()` true.

**Avoid serializing the entire result into a REST response.** Rejected values may contain emails, passwords, tokens, or personal information. The demo intentionally picks safe field names and generic codes.

### 10.1. One Field Can Have Multiple Errors

If `email=""` with `@NotBlank @Email`, the number of errors depends on the provider and triggered constraints. Do not assume `getFieldErrors()` holds only one FieldError per field. For tests targeting BindingResult positioning, use a payload violating **one clear constraint** so assertions depend less on the provider.

### 10.2. Global Errors Are Not Field Errors

A class-level constraint can produce an `ObjectError` that does not belong to a specific property. Do not conclude from `getFieldErrorCount() == 0` that there are no errors at all; use `hasErrors()` or `getErrorCount()` and handle `getGlobalErrors()` too.

### 10.3. `BindingResult#getModel` Does Not Replace Passing `Model`

`result.getModel()` returns a map containing the target and BindingResult metadata to add to a model; however, that is no reason to place `Model` between the argument and the result. `Model model` and `BindingResult result` are two distinct arguments; the adjacency rule still holds.

## 11. `@Valid`, `@Validated`, Groups, and Method Validation

### 11.1. `@Valid` Is a Cascade Marker, Not a Direct Constraint

`jakarta.validation.Valid` activates validation on an object and its nested properties. `@Valid` itself is not a `Constraint` like `@Min`. In Spring MVC 6.1+, when **direct constraints** appear on method parameters, method validation can apply and supersede individual parameter validation.

### 11.2. `@Validated` with Groups

Example:

```java
@PostMapping("/approval")
public String approve(
        @Validated(ApprovalGroup.class)
        @ModelAttribute("request") ApprovalForm form,
        BindingResult errors) {
    // ...
    return errors.hasErrors() ? "form" : "done";
}
```

This is a fragment; `ApprovalGroup` and `ApprovalForm` must exist in the application. Even when using validation groups, `BindingResult` must still immediately follow the object; group selection does not relax ordering.

### 11.3. Class-Level `@Validated` in Controllers

Depending on the Spring version/configuration, class-level `@Validated` may enable AOP method validation instead of built-in MVC method validation. Spring MVC 6.2 documentation notes paying attention when adopting built-in method validation (Spring 6.1+). If unusual errors are observed:

- Check whether the controller class has `@Validated`.
- Check for direct constraint annotations on method parameters.
- Check whether MVC handles `HandlerMethodValidationException`.
- Do not explain every validation exception as a misplaced `BindingResult`.

### 11.4. Do Not Confuse `BindingResult` with `@ExceptionHandler`

`BindingResult` is the local argument result for a **specific object**. `@ExceptionHandler`/`ResponseEntityExceptionHandler` provides global or controller-level exception routing. You can pick either for a given flow, or combine them across different endpoints, but never replace signature ordering with advice.

## 12. Common Misconceptions

### 12.1. "As long as `BindingResult` is anywhere in the method, it works"

False. It must sit **immediately after** its corresponding object. The Java compiler does not check this framework rule.

### 12.2. "Put `Model` before `BindingResult` to render the form"

No. Put `BindingResult` right next to the object, and `Model` after it or before the entire pair.

### 12.3. "Just rename the variable to `formBindingResult`"

No. Spring does not match a result to an object by Java parameter name.

### 12.4. "One `BindingResult` collects errors for two `@ModelAttribute`s"

No. Each DTO needs its own result immediately after it if local handling is wanted for both.

### 12.5. "`@RequestBody` can never use `BindingResult`"

False in Spring MVC for validation of a compatible object. `@Valid @RequestBody DTO dto, BindingResult result` is a documented pattern. However, errors when JSON **cannot be decoded** still bypass this local result.

### 12.6. "With `BindingResult`, every error goes into `result.hasErrors()`"

No. JSON parse failures, unsupported media types, missing required bodies, security failures, or unhandled method-validation errors can be processed before the controller is invoked. `hasErrors()` only describes binding/validation errors of the object it belongs to.

### 12.7. "Missing `BindingResult` is always a bug"

No. In REST APIs using global exception advice, you can intentionally **omit** the result. When validation fails, Spring throws an exception and advice returns a consistent error schema. The bug is **wanting local handling yet misplacing the result**.

### 12.8. "HTTP 400 proves the result is misplaced"

No. 400 also has many other causes such as missing parameters, malformed JSON, type mismatches, constraint violations, or malformed multipart payloads. Check the specific exception/log/argument signature.

### 12.9. "Changing the parameter type from `BindingResult` to `Errors` fixes the error"

No. `Errors` and `BindingResult` obey the exact same adjacency rule.

### 12.10. "Having `@NotBlank` in the DTO guarantees the validator runs"

Not if `@Valid`/`@Validated` is missing at the validation boundary, the provider is absent, groups do not match, or the controller uses a different argument resolver. Check configuration before blaming the constraints.

### 12.11. "Form binding and JSON deserialization fail identically"

No. Form property conversion can create `FieldError.isBindingFailure()`; JSON deserialization type failures typically occur in the message converter and may throw `HttpMessageNotReadableException`.

### 12.12. "Adding `@InitBinder` fixes a misplaced `BindingResult`"

No. `@InitBinder` configures WebDataBinder/validators; it does not reorder method arguments. Fix the signature first.

### 12.13. "Catching `IllegalStateException` globally is enough"

Not recommended. `IllegalStateException` also represents many other programming errors. A broad handler masks misconfigurations. Fix the controller signature and add tests, mapping only known exceptions to the error contract.

### 12.14. "Testing only valid requests is enough"

No. With valid input, a broken signature can behave differently than when validation fails. Always test at least one constraint violation and one binding type failure when forms involve conversion.

## 13. Quick Diagnostic Matrix

| Symptom | Check first | Fix |
| --- | --- | --- |
| `BindingResult` present yet handler misses invalid request | Is result right next to `@Valid` DTO? | Move result immediately after DTO |
| `Model` appears before result | Is Model inserted in between? | Put Model after result |
| `Locale`/`@RequestParam` in between | Gap between DTO and result | Reorder parameters |
| Two forms in one method with only one result | Does first DTO have an adjacent result? | One BindingResult per DTO |
| Invalid JSON throws `MethodArgumentNotValidException` | Do you want local handling? | Yes: result right after body; no: use advice |
| Malformed JSON skips local result | Could converter construct the object? | Handle `HttpMessageNotReadableException` |
| `page=0` with direct `@Min` throws different exception | Is method validation active? | Handle `HandlerMethodValidationException` |
| `age=abc` in form | Is `isBindingFailure()` true? | Check type conversion and field error |
| Correct signature yet constraints do not run | Provider and `@Valid`/groups | Fix validation setup |
| Correct signature yet errors are swallowed | Is there a `hasErrors()` branch? | Check result, response, and tests |
| Result belongs to wrong object | Multiple DTOs and pair ordering | Pair each result right after its DTO |
| Field errors missing from response | Reading only global or field errors? | Handle both groups |

## 14. Code Review Checklist Before Merging a Controller

- [ ] Every `BindingResult`/`Errors` stands **immediately after** the argument it describes.
- [ ] No `Model`, `Locale`, `Principal`, `@RequestParam`, or `@RequestHeader` sits in between.
- [ ] Multiple `@ModelAttribute`s needing local error handling have **multiple separate results**.
- [ ] `@Valid`/`@Validated` is placed in the right spot; validation provider is declared.
- [ ] Bean Validation is not expected on an undeserializable request body.
- [ ] Form binding errors, JSON converter errors, and method validation exceptions are distinguished.
- [ ] Contract is clear: local BindingResult or global exception advice.
- [ ] MockMvc tests cover invalid form and invalid JSON.
- [ ] At least one type-conversion failure test exists when using `@ModelAttribute`.
- [ ] Tests verify status, code, field name, and expected handler/advice branch.
- [ ] Raw rejected values, exception messages, or stack traces are never returned.
- [ ] Global/object errors are handled if class-level constraints are used.
- [ ] Tests cover two DTOs in the same handler if the feature supports it.
- [ ] When adding a new argument to a method, it is not inserted between a DTO/result pair.
- [ ] When upgrading to Spring Framework 6.1+, inspect the `HandlerMethodValidationException` path if direct constraints exist.
- [ ] Broad exception handlers are not used to hide `IllegalStateException` from broken signatures.

## 15. Conclusion

**A misplaced `BindingResult` in a controller signature** is a small framework-syntax error that can cause confusing behavior: the controller is never called, validation errors divert to exception advice, or the resolver reports not finding the result in the right place.

The fix always starts with the signature:

```java
@Valid @ModelAttribute("form") Form form,
BindingResult errors,
Model model
```

and correspondingly:

```java
@Valid @RequestBody RequestDto request,
BindingResult errors,
@RequestHeader("X-Client") String client
```

**Keep object and result adjacent.** When handling multiple objects, each object needs its own result. When local errors are not needed, omit the result intentionally and rely on global exception handling. Also distinguish `MethodArgumentNotValidException`, `HandlerMethodValidationException`, and HTTP message converter errors so you do not misdiagnose.

Combining parameter-order checks with **MockMvc regression tests** for invalid input is the simplest and most durable way to prevent this bug from returning.

## References

- [Spring Framework 6.2 — MVC Method Arguments: Errors and BindingResult](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework 6.2 — @ModelAttribute and BindingResult](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @RequestBody, @Valid and BindingResult](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — MVC Validation, MethodArgumentNotValidException and HandlerMethodValidationException](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — @RequestPart and Multipart Forms](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — ErrorsMethodArgumentResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/method/annotation/ErrorsMethodArgumentResolver.html)
- [Spring Framework 6.2 — MethodArgumentNotValidException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/MethodArgumentNotValidException.html)
- [Spring Framework 6.2 — HandlerMethodValidationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Boot 3.4 — Validation](https://docs.spring.io/spring-boot/3.4/reference/io/validation.html)
