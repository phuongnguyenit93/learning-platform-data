# Errors, BindingResult, and Error Parameter Placement in Spring MVC

## 1. The Problem to Solve

Suppose a registration page receives the following input:

```text
name=
age=abc
email=ada@example.com
```

The controller expects `age` to be an integer and `name` to be non-empty. Without error handling, the request can end with a 400 error without telling the user which fields need fixing. Spring MVC provides `Errors` and `BindingResult` so controllers can inspect **errors recorded while binding and validating a request object**.

This lesson focuses on four questions:

1. How `Errors` differs from `BindingResult`; how to read `FieldError`, `ObjectError`, error codes, rejected values, and object names.
2. Why the `Errors`/`BindingResult` parameter must **immediately follow** the `@ModelAttribute`, `@RequestBody`, or `@RequestPart` parameter it corresponds to.
3. When an error-receiving parameter is present vs. absent, whether Spring invokes the controller or throws an exception; distinguishing type conversion errors, Bean Validation errors, JSON deserialization errors, and method validation.
4. How to return clear HTTP errors, display errors in HTML forms, and verify behavior with `MockMvc`.

**Context:** Spring MVC on the Servlet stack, Spring Framework **6.x** / Spring Boot **3.x**, Java **17+**. The `@Valid` examples use `jakarta.validation.Valid` from Jakarta Bean Validation (not the legacy `javax.validation` package).

## 2. From Request to Object and Error List

When a controller declares a form object:

```java
@PostMapping("/register")
String register(@Valid @ModelAttribute("signup") SignupForm form,
                BindingResult result) {
    if (result.hasErrors()) {
        return "register-form";
    }
    return "register-success";
}
```

*This illustrates a controller signature returning a view name; a runnable REST example is in Section 8.*

General processing flow:

```text
Request: name="", age="abc", email="ada@example.com"
  │
  ▼
RequestMappingHandlerAdapter / method argument resolver
  │
  ├── Create or retrieve SignupForm in the model
  ├── WebDataBinder receives values by property name
  │     ├── name="" → String (bound)
  │     ├── age="abc" → Integer (conversion FAILED)
  │     └── email="ada@example.com" → String (bound)
  │
  ├── BindingResult records typeMismatch error on age
  ├── @Valid requests Bean Validation
  │     └── @NotBlank on name → NotBlank error
  │
  ├── Is BindingResult parameter immediately after SignupForm?
  │     ├── Yes → controller can inspect result.hasErrors()
  │     └── No → error handled via the appropriate exception path
  ▼
Controller or exception handling mechanism
```

**Binding fails** when input cannot be converted to the expected type (e.g., `"abc"` → `Integer`). **Validation fails** when processed data violates rules (e.g., `age=15` against `@Min(18)`). Both can be observed through `BindingResult` for form objects.

`@Valid` does not perform type conversion; it requests constraint evaluation after the object is bound/deserialized. To enable Bean Validation in a Spring Boot 3 project, add `spring-boot-starter-validation` or provide an equivalent Jakarta Validation provider. `spring-boot-starter-web` alone should not be assumed to include a validation provider.

For JSON `@RequestBody`, decoding is performed first by `HttpMessageConverter` (usually Jackson), **not** HTML form property binding. If JSON fails to parse or a value fails to deserialize, the error can occur **before creating the object and `BindingResult` for the controller to handle**. `Errors` placed after `@RequestBody` is useful for validation errors on an object that deserialized successfully.

## 3. Errors and BindingResult: Relationship and API

### 3.1. Inheritance Relationship

`Errors` and `BindingResult` are two **interfaces** in package `org.springframework.validation`:

```text
org.springframework.validation.Errors
                   ▲
                   │ extends
org.springframework.validation.BindingResult
```

`BindingResult extends Errors`. Therefore, any object implementing `BindingResult` also provides all methods of `Errors`.

- **`Errors`**: inspects, registers, and looks up object-level or field-level errors; use when code only needs error handling.
- **`BindingResult`**: adds binding-specific details such as the target object, raw field values, suppressed field names, and model integration.

You can use `Errors` instead of `BindingResult` when you only need `hasErrors()`, `getFieldErrors()`, or `rejectValue(...)`. Choose `BindingResult` when you need `getTarget()`, `getSuppressedFields()`, `getModel()`, or other binding details.

### 3.2. Key Methods to Remember

| API | Meaning | Scenario |
| --- | --- | --- |
| `errors.hasErrors()` | Any object or field error exists | Decide whether to proceed or return errors |
| `errors.getErrorCount()` | Total number of recorded errors | Error statistics |
| `errors.hasFieldErrors("age")` | Field `age` has errors | Highlight input needing correction |
| `errors.getFieldError("age")` | First error for field `age`, may be `null` | Get error code/message |
| `errors.getFieldErrors()` | List of all `FieldError`s | Return errors by field |
| `errors.getGlobalErrors()` | Object-level errors, not tied to a single field | Cross-field rules |
| `errors.getAllErrors()` | Both global and field errors | General handling |
| `errors.getObjectName()` | Bound object name, e.g., `signup` | Identify which form failed |
| `errors.reject("code")` | Register a global error by code | Whole-object rule |
| `errors.rejectValue("age", "code")` | Register an error on a specific field | Custom validator |
| `bindingResult.getTarget()` | Bound object, may be `null` | Debug/inspect target |
| `bindingResult.getRawFieldValue("age")` | Underlying raw value per binding implementation | Debug binding |
| `bindingResult.getSuppressedFields()` | Names of fields blocked during binding | Detect out-of-allowlist assignment attempts |
| `bindingResult.getModel()` | Map containing the object and its binding result | Support model/view and binding state |

Not every failure produces only a single `FieldError`. One field can violate multiple constraints, such as `@NotNull` and `@Min`, depending on the case. Thus `getFieldError("age")` returns one error while `getFieldErrors("age")` may contain several.

### 3.3. FieldError and ObjectError

`FieldError` extends `ObjectError`. Together they represent two error scopes:

- **`FieldError`:** tied to a specific property, e.g., `age` is non-numeric or below 18. Commonly used methods: `getField()`, `getRejectedValue()`, `getCode()`, `getCodes()`, `getDefaultMessage()`, and `isBindingFailure()`.
- **`ObjectError` (global):** tied to the whole object, e.g., start date must precede end date, where the rule spans multiple properties. See `getObjectName()`, `getCode()`, and `getDefaultMessage()`.

Example error-inspection snippet, used in a controller/validator where `BindingResult result` is available:

```java
for (FieldError e : result.getFieldErrors()) {
    System.out.println(
        e.getField() + ": " + e.getCode()
        + ", rejected=" + e.getRejectedValue());
}

for (ObjectError e : result.getGlobalErrors()) {
    System.out.println(
        "object=" + e.getObjectName()
        + ", code=" + e.getCode());
}
```

*This snippet illustrates reading errors; standalone compilation requires importing `FieldError`, `ObjectError`, and having a `BindingResult` variable `result`. In production, **do not log `getRejectedValue()` indiscriminately**, as it may contain personal data, tokens, or secrets.*

### 3.4. Error Codes and Display Messages

Error codes like `typeMismatch`, `NotBlank`, and `Min` are **message lookup keys**, not final display text required verbatim. `MessageCodesResolver` generates code sequences from specific to general. For instance, for form name `signup` when field `age` fails conversion to `Integer`, resolved codes may include:

```text
typeMismatch.signup.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
```

*These codes illustrate default resolution behavior; inspect `FieldError#getCodes()` for the exact active configuration and field type.*

When rendering messages, use `MessageSource` or Spring's form rendering integration to resolve by locale and error code. `getDefaultMessage()` works as a fallback, though it is not guaranteed to be localized or stable as an API contract. Real APIs should construct a response schema with stable `field` and `code` keys instead of returning raw exception messages.

## 4. Key Rule: Place Errors/BindingResult Adjacent to the Target Parameter

Spring MVC binds `Errors`/`BindingResult` to the result of the **request parameter resolved immediately before it**. Therefore, it **must sit immediately after** the `@ModelAttribute`, `@RequestBody`, or `@RequestPart` object whose binding/validation errors are being captured.

### 4.1. Correct: BindingResult Immediately After @ModelAttribute

```java
@PostMapping("/save")
String save(@Valid @ModelAttribute("profile") ProfileForm profile,
            BindingResult errors,
            Model model) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "profile-saved";
}
```

Here `BindingResult errors` corresponds to `profile`. `Model model` can be placed **after** `BindingResult` without breaking the pair.

### 4.2. Wrong: Another Parameter Inserted Between Them

```java
// WRONG: Model sits between the bound object and the error result.
@PostMapping("/save")
String save(@Valid @ModelAttribute("profile") ProfileForm profile,
            Model model,
            BindingResult errors) {
    return "profile-saved";
}
```

The mistake can manifest as an exception about `Errors/BindingResult` ordering or an argument-resolution failure. Never assume "Spring will scan backward to the first failing object." Placing `BindingResult` immediately after `profile` is the right rule.

**Do not place** `BindingResult` at the start of the method or after an unrelated `@RequestParam` when it belongs to an earlier `@ModelAttribute`. Whether the Java parameter is named `errors` or `bindingResult` does not matter; **position** and the immediately preceding parameter are what matter.

### 4.3. Two Input Objects: Each Object Gets Its Own BindingResult

```java
@PostMapping("/compose")
String compose(@Valid @ModelAttribute("shipping") ShippingForm shipping,
               BindingResult shippingErrors,
               @Valid @ModelAttribute("billing") BillingForm billing,
               BindingResult billingErrors) {
    if (shippingErrors.hasErrors() || billingErrors.hasErrors()) {
        return "compose-form";
    }
    return "composed";
}
```

*This is an illustrative signature for a controller with two DTOs and corresponding views; not a standalone program.* The first result belongs to `shipping`; the second belongs to `billing`. Placing both `BindingResult` parameters at the end of the method can mis-bind or throw an error. Pairing each result immediately after its object matters more than variable naming.

### 4.4. @RequestBody and @RequestPart

Correct pairing for deserialized JSON:

```java
@PostMapping("/json")
ResponseEntity<?> json(@Valid @RequestBody CreateOrderRequest request,
                       Errors errors) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }
    return ResponseEntity.ok().build();
}
```

For a JSON part in multipart requests, you can similarly use `@Valid @RequestPart("metadata") Metadata metadata, BindingResult errors`. **Note:** an uploaded `MultipartFile` part is raw upload data; do not conflate file validation with Bean Validation on a deserialized part DTO.

Differences to keep in mind:

- With `@ModelAttribute`, form object **binding/conversion** errors and validation errors normally go together into `BindingResult`.
- With `@RequestBody`/`@RequestPart`, JSON/XML is read first by a message converter. An immediately following `Errors`/`BindingResult` gives you **Bean Validation errors** on the successfully deserialized object; it **does not** capture JSON syntax errors, missing request bodies, multipart parsing errors, or unsupported media types.
- `@RequestParam Integer age` and `@PathVariable Long id` are single parameters; conversion errors on them typically go through exception resolvers as `MethodArgumentTypeMismatchException`, rather than by placing a `BindingResult` right after them.

## 5. @Valid, @Validated, and Behavior Without an Error Parameter

### 5.1. Without an Adjacent Errors/BindingResult

```java
@PostMapping("/register")
String register(@Valid @ModelAttribute("signup") SignupForm form) {
    return "saved";
}
```

If input fails validation or binding, Spring MVC by default does not proceed into the method as if the form were valid. For parameter-level object validation/binding, `MethodArgumentNotValidException` is the common exception branch; MVC typically translates it to HTTP 400.

For `@Valid @RequestBody SignupForm form` without `Errors`, a deserialized JSON object violating constraints also commonly triggers `MethodArgumentNotValidException` and default HTTP 400.

**With an immediately following parameter:**

```java
@PostMapping("/register")
String register(@Valid @ModelAttribute("signup") SignupForm form,
                Errors errors) {
    if (errors.hasErrors()) {
        return "register-form";
    }
    return "saved";
}
```

Spring invokes the method so you can handle errors directly in the controller. `@Valid` itself **does not** generate an HTML or JSON error response for you; the controller must inspect `hasErrors()` or the corresponding APIs. Never ignore errors and proceed to call a persistence service.

### 5.2. Not All Validation Is Single-Parameter Validation

Starting in Spring MVC **6.1**, if a controller method has constraints directly on method parameters, such as `@Min(1) @RequestParam int page`, validation can apply at the **method level** rather than per individual object. This can produce `HandlerMethodValidationException`, distinct from `MethodArgumentNotValidException`.

```java
@GetMapping("/search")
String search(@RequestParam @Min(1) int page) {
    return "page:" + page;
}
```

*This illustrative snippet requires a Jakarta Validation provider, MVC imports, and the `@Min` constraint.* When a client sends `page=0`, method-level validation has no `@ModelAttribute` form object for a traditional `BindingResult`. Adding a direct parameter constraint to a method that already has `@Valid @ModelAttribute` can change error handling because method validation encompasses nested constraints too.

In MVC 6.1+'s built-in method validation, the controller is invoked only when **all validation errors relate to parameters that have `Errors` immediately following them**. If another method parameter also has errors with no receiver, Spring throws `HandlerMethodValidationException`. Do not assume one form's `BindingResult` catches errors from other parameters in the same method.

`@Validated` can be used to select validation groups. However, class-level `@Validated` on a controller can trigger AOP method validation; in Spring MVC 6.1+, if you want MVC's built-in method validation, Spring docs recommend omitting class-level `@Validated`. Check both configuration and version before predicting exact exception behavior.

### 5.3. Diagnostic Table

| Scenario | Does controller receive results via adjacent Errors? | Typical outcome |
| --- | --- | --- |
| `@Valid @ModelAttribute Form`, invalid data | Yes | Controller runs and checks `errors.hasErrors()` |
| `@Valid @ModelAttribute Form`, invalid data | No | `MethodArgumentNotValidException` / 400 (if no other method validation) |
| `@Valid @RequestBody Dto`, valid JSON violating constraints | Yes | Controller receives validation errors |
| `@Valid @RequestBody Dto`, valid JSON violating constraints | No | `MethodArgumentNotValidException` / 400 |
| `@RequestBody`, invalid JSON syntax or undeserializable | Yes or No | `HttpMessageNotReadableException` / typically 400, before controller runs |
| `@RequestParam Integer age` receiving `age=abc` | Do not use BindingResult for single params | Typically `MethodArgumentTypeMismatchException` / 400 |
| Method-level `@Min(1) @RequestParam int page` | No per-param result | `HandlerMethodValidationException` in built-in MVC mechanism |
| Client sends field blocked by `allowedFields` | With `BindingResult` | Check `getSuppressedFields()`; may not appear in `hasErrors()` |

The HTTP statuses here are common defaults and can change via `@ExceptionHandler`, `@ControllerAdvice`, security, or custom exception resolvers. Distinguish **exceptions before the controller runs** from **errors recorded in `BindingResult` handled by the controller**.

## 6. Field Errors, Global Errors, and Returning Messages to the UI

### 6.1. Field Errors

Example request with `age=abc`, `name=""`:

```text
objectName: signup
FieldError(field=age, code=typeMismatch, rejectedValue=abc)
FieldError(field=name, code=NotBlank, rejectedValue="")
```

*This is a logical description, not a guaranteed verbatim `toString()` output; exact counts/codes depend on constraints and resolvers.* `errors.hasFieldErrors("age")` returns `true`, and `errors.getFieldErrors()` returns the list of field errors.

### 6.2. Global Errors

A rule like "start date must be before end date" depends on a **pair** of fields. A validator or controller can register a whole-object error:

```java
if (!startDate.isBefore(endDate)) {
    errors.reject("dateRange.invalid", "Start date must be before end date");
}
```

*This is an illustrative logic snippet; `startDate` and `endDate` must come from the request object inside a validator or controller.* Global errors appear in `getGlobalErrors()`. If you want the error displayed under a specific field, you can use `rejectValue("endDate", "dateRange.invalid", "...")` when that field exists on the binding target. Display placement is a UX choice, while rule evaluation belongs in the appropriate layer and should be tested.

### 6.3. Reusing Errors in HTML Views

With view-returning controllers (not `@RestController`), Spring typically exposes `@ModelAttribute("signup")` and `BindingResult` in the model for re-rendering the form. The corresponding model key for `BindingResult` takes the form:

```text
org.springframework.validation.BindingResult.signup
```

This is the prefix `BindingResult.MODEL_KEY_PREFIX` concatenated with object name `signup`. Template engines like Thymeleaf and Spring form tags use this binding state to highlight invalid inputs and show messages.

When a form has errors, normally **return the view name** to preserve form state and errors within the same request:

```java
@PostMapping("/register")
String register(@Valid @ModelAttribute("signup") SignupForm form,
                BindingResult result) {
    if (result.hasErrors()) {
        return "register-form";
    }
    return "redirect:/registered";
}
```

*This is a controller signature example with a view resolver; do not apply it to `@RestController`.* Redirecting immediately on error loses the old `BindingResult` in the new request unless you explicitly pass flash attributes properly. Avoid accidental redirects on errors that wipe out user input and validation messages.

### 6.4. JSON APIs: Returning Structured Errors

For REST APIs, you can construct responses such as:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    { "field": "age", "code": "typeMismatch", "message": "Age must be a number" },
    { "field": "name", "code": "NotBlank", "message": "Name must not be blank" }
  ]
}
```

This schema is a **suggested API contract**, not Spring Boot's default response. You can aggregate from `FieldError` and resolve messages by `Locale`. Never expose stack traces, SQL, internal converter details, or sensitive rejected values. Avoid treating `getDefaultMessage()` as a stable API code; frontends should rely on normalized `code`/`field` identifiers for long-term compatibility.

## 7. Three Signatures to Remember Before Practicing

```java
// 1. Form binding + Bean Validation: capture errors right in the method.
@PostMapping("/form")
ResponseEntity<?> form(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {
    // ...
}

// 2. Successful JSON deserialization + Bean Validation: capture errors in the method.
@PostMapping("/json")
ResponseEntity<?> json(
        @Valid @RequestBody SignupForm form,
        Errors errors) {
    // ...
}

// 3. WRONG: Errors is separated from the object being validated.
@PostMapping("/wrong")
ResponseEntity<?> wrong(
        @Valid @ModelAttribute("signup") SignupForm form,
        @RequestParam(required = false) String trace,
        BindingResult errors) {
    // ...
}
```

*These are illustrative signatures and do not compile standalone; see the complete application right below.* In both valid signatures, even though the parameter is named `errors`, the interface type can be either `Errors` or `BindingResult`. For JSON, remember that parse errors occur in an earlier layer.

## 8. Runnable Spring Boot 3 and Java 17 Example

This application demonstrates `@ModelAttribute`, `@RequestBody`, `Errors`, `BindingResult`, field errors, global errors, and exact HTTP status/body tests. Uses Spring Boot **3.3.13**, JDK **17+**, and Maven.

Layout:

```text
mvc-binding-errors/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── BindingErrorsApplication.java
    │   ├── SignupForm.java
    │   └── SignupController.java
    └── test/java/example/
        └── SignupControllerTest.java
```

### 8.1. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>mvc-binding-errors</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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
```

The validation starter supplies a Bean Validation implementation such as Hibernate Validator in a Spring Boot 3 environment. Code imports `jakarta.validation.*` and `jakarta.validation.constraints.*`.

### 8.2. File BindingErrorsApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingErrorsApplication.class, args);
    }
}
```

### 8.3. File SignupForm.java

```java
package example;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {
    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    @NotBlank
    @Email
    private String email;

    public SignupForm() {}

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

Explanation:

- `@NotBlank` rejects `null`, empty strings, or whitespace-only strings.
- `@NotNull` ensures `age` has a value after binding.
- `@Min(18)` applies to a numeric value that converted successfully; `"abc"` is a `typeMismatch` error rather than a numeric comparison below 18.
- `@Email` checks the string against the provider's email rule; e.g., `not-an-email` is rejected.

### 8.4. File SignupController.java

```java
package example;

import java.util.stream.Collectors;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/signup")
public class SignupController {

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> form(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult errors) {

        // Example whole-object business rule.
        if (!errors.hasErrors() && "admin".equalsIgnoreCase(form.getName())) {
            errors.reject("signup.nameReserved", "Name is already reserved");
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(describe(errors));
        }

        return ResponseEntity.ok(describeSuccess(form));
    }

    @PostMapping(path = "/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> json(
            @Valid @RequestBody SignupForm form,
            Errors errors) {

        // Validation errors on an already-deserialized JSON DTO.
        // Malformed JSON can be rejected before this method is called.
        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(describe(errors));
        }

        return ResponseEntity.ok(describeSuccess(form));
    }

    private static String describe(Errors errors) {
        String fields = errors.getFieldErrors().stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .collect(Collectors.joining(","));

        if (!fields.isEmpty()) {
            return "invalid:" + fields;
        }

        if (errors.hasGlobalErrors()) {
            return "invalid:global";
        }

        return "invalid:unknown";
    }

    private static String describeSuccess(SignupForm form) {
        return "created:" + form.getName()
                + "|" + form.getAge()
                + "|" + form.getEmail();
    }
}
```

Because `Errors` exposes `hasErrors`, `getFieldErrors`, and `hasGlobalErrors`, the `describe(Errors)` helper works for both `BindingResult` on forms and `Errors` on JSON. Only the form controller demonstrates `reject(...)` for a global error; this illustrates the API, while real systems typically place multi-step rules in a custom `Validator` or service.

The helper returns only sorted **field names** for deterministic output; it does not expose `rejectedValue`. A production API should also return safe codes and messages, such as the structure in Section 6.

### 8.5. Run Commands and Verifiable Output

In the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

From another terminal, send these four form requests (on Linux/macOS or shells supporting `\` line continuation; in PowerShell, use `curl.exe` on one line if needed):

```bash
curl -s -X POST http://localhost:8080/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Ada" \
  --data-urlencode "age=21" \
  --data-urlencode "email=ada@example.com"

curl -s -X POST http://localhost:8080/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=" \
  --data-urlencode "age=abc" \
  --data-urlencode "email=ada@example.com"

curl -s -X POST http://localhost:8080/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Ada" \
  --data-urlencode "age=15" \
  --data-urlencode "email=ada@example.com"

curl -s -X POST http://localhost:8080/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=admin" \
  --data-urlencode "age=22" \
  --data-urlencode "email=admin@example.com"
```

Expected response bodies in order (none adds a trailing newline):

```text
created:Ada|21|ada@example.com
invalid:age,name
invalid:age
invalid:global
```

Why?

1. Valid form produces an object with numeric `age=21` and returns HTTP **200**.
2. Empty `name` violates `NotBlank` and `age=abc` causes a type conversion error; both are recorded in `BindingResult` and return **400** with both field names.
3. `age=15` converts successfully but violates `Min(18)`; returns **400** with field `age`.
4. `name=admin` passes Bean Validation, but the controller registers a global error via `reject`; returns **400** `invalid:global`.

Send valid JSON and parseable JSON with an invalid email:

```bash
curl -s -X POST http://localhost:8080/signup/json \
  -H "Content-Type: application/json" \
  -d '{"name":"Ada","age":21,"email":"ada@example.com"}'

curl -s -X POST http://localhost:8080/signup/json \
  -H "Content-Type: application/json" \
  -d '{"name":"Ada","age":21,"email":"not-an-email"}'
```

Expected body:

```text
created:Ada|21|ada@example.com
invalid:email
```

A JSON request with `"age":"abc"` that cannot deserialize into `Integer` normally gets HTTP **400** via `HttpMessageNotReadableException` **before** `SignupController.json` is called. Do not expect `invalid:age` from `describe` for that failure: that is a critical difference between JSON deserialization and form property binding.

### 8.6. MockMvc Tests: Proving Behavior Rather Than Guessing Exceptions

File `src/test/java/example/SignupControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validFormIsAccepted() throws Exception {
        mvc.perform(post("/signup/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Ada")
                    .param("age", "21")
                    .param("email", "ada@example.com"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    "created:Ada|21|ada@example.com"));
    }

    @Test
    void bindingAndBeanValidationErrorsAreCollected() throws Exception {
        mvc.perform(post("/signup/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "")
                    .param("age", "abc")
                    .param("email", "ada@example.com"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("invalid:age,name"));
    }

    @Test
    void numericConstraintIsDifferentFromConversionError() throws Exception {
        mvc.perform(post("/signup/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Ada")
                    .param("age", "15")
                    .param("email", "ada@example.com"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("invalid:age"));
    }

    @Test
    void globalErrorCanBeAddedToBindingResult() throws Exception {
        mvc.perform(post("/signup/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "admin")
                    .param("age", "22")
                    .param("email", "admin@example.com"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("invalid:global"));
    }

    @Test
    void requestBodyValidationCanBeHandledLocally() throws Exception {
        mvc.perform(post("/signup/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"name\":\"Ada\",\"age\":21,"
                        + "\"email\":\"not-an-email\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("invalid:email"));
    }

    @Test
    void malformedJsonConversionFailsBeforeControllerErrors() throws Exception {
        mvc.perform(post("/signup/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"name\":\"Ada\",\"age\":\"abc\","
                        + "\"email\":\"ada@example.com\"}"))
            .andExpect(status().isBadRequest());
    }
}
```

Use `mvn test` to run the six tests. They verify: receiving errors in the controller when `BindingResult` sits right after the argument, distinguishing type mismatch from constraints, custom object errors, Bean Validation after JSON deserialization, and JSON parse/conversion failure in the message converter layer. The final test asserts only HTTP status because the default error body depends on Spring Boot's error handling rather than `describe()`.

Do not put the **intentionally invalid** signatures from Section 4 into the demo project: they are shown to teach how to spot mistakes, not as application code to deploy.

## 9. How to Check Errors in Production Code

Minimal correct handling pattern:

```java
if (bindingResult.hasErrors()) {
    // For HTML forms: re-render the view with inputs and messages.
    // For APIs: normalize FieldError/ObjectError into a safe body.
    return ...; // Pick the return type fitting the actual controller.
}

// Only invoke the service after the DTO passes binding/validation.
```

*This is illustrative pseudocode, not standalone Java; replace `...` with a valid return value.*

Recommended sequence:

1. **Bind** data into a dedicated DTO. Avoid binding directly into an entity with sensitive properties.
2. **Validate** using `@Valid`/`@Validated` or configured validators; for multi-field rules, record global/field errors intentionally.
3. **Check for errors** before calling the service. `hasErrors()` covers both field and global errors.
4. **Check suppressed fields** when using `allowedFields`: `getSuppressedFields()` is separate info on `BindingResult` that may require rejecting the request even when `hasErrors()` is false.
5. **Build the response/view** with appropriate codes and messages; never expose sensitive rejected values and never rely on natural error list order as an API contract.
6. **Handle exceptions outside binding results** in the proper place: malformed JSON, single-parameter type mismatches, method-level validation errors, unsupported media types, etc.

For RFC Problem Details style error responses, standardize via `ProblemDetail`, `ResponseEntityExceptionHandler`, and `@RestControllerAdvice`. If writing custom `@ExceptionHandler` methods for `MethodArgumentNotValidException` or `HandlerMethodValidationException`, keep the format consistent with errors returned from controllers; each exception carries slightly different data structures.

## 10. Common Mistakes When Learning Errors and BindingResult

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Putting `Model` or `@RequestParam` between form and `BindingResult` | Fails to associate binding result properly | Place `BindingResult` **immediately after** the form DTO |
| Two forms with only one `BindingResult` at the end of the method | Cannot capture separate error results per form | Pair each object/result adjacent to each other |
| Adding `@Valid` while skipping `errors.hasErrors()` | Can proceed to persist an invalid DTO | Check before business logic |
| Thinking `Errors` and `BindingResult` are completely separate objects | Awkward or incorrect API usage | `BindingResult extends Errors`; pick the interface you need |
| Calling `getFieldError("x")` and invoking methods without null checks | `NullPointerException` when the field is valid | Check `hasFieldErrors` or `null` |
| Assuming `getFieldErrors()` includes global errors | Misses cross-field rules | Also inspect `getGlobalErrors()`/`getAllErrors()` |
| Assuming `BindingResult` catches every JSON error | Misses parse failures | Handle `HttpMessageNotReadableException` separately |
| Expecting `BindingResult` to catch malformed `@RequestParam int` | Wrong placement/mechanism | Use exception handling for single-parameter mismatches |
| Omitting the validation starter | Constraints do not execute as expected | Install a Bean Validation provider, test with MockMvc |
| Returning `getRejectedValue()` in public errors | Leaks raw input data | Return only normalized metadata/messages |
| Using `hasErrors()` to detect suppressed fields | Misses blocked fields | Call `getSuppressedFields()` when using an allowlist |
| Redirecting immediately on HTML form error | Loses binding state/messages on the new request | Re-render the form or use flash attributes properly |
| Relying on `getFieldErrors()` order in response tests | Tests become flaky across providers/configs | Sort and/or normalize error codes |

## 11. Practice Scenarios

**Scenario A.** Method:

```java
@PostMapping("/register")
String register(@Valid @ModelAttribute("form") Form form,
                @RequestParam(required = false) String campaign,
                BindingResult result) {
    // ...
}
```

What is wrong? **Answer:** `BindingResult` is separated from `Form` by `campaign`. Move `BindingResult result` immediately after `Form form`, followed by `@RequestParam`.

**Scenario B.** A form submits `age=seventeen` to a DTO with `Integer age` and `@Min(18)`. What kind of error is this? **Answer:** a conversion/type mismatch when turning `String` into `Integer`, happening before `@Min` can evaluate a valid number.

**Scenario C.** A JSON DTO has `@Email`; JSON `{"email":"invalid"}` still deserializes to `String`. If the method has `@Valid @RequestBody Dto dto, Errors errors`, what happens? **Answer:** the method can inspect Bean Validation errors via `Errors`. Without `Errors`, `MethodArgumentNotValidException` is normally thrown.

**Scenario D.** JSON `{"age":"not-number"}` targets a DTO with `Integer age`. Will a `BindingResult` right after `@RequestBody` reliably catch it? **No.** Jackson can fail during deserialization and Spring throws `HttpMessageNotReadableException` before the method runs.

**Scenario E.** There are no field errors, yet `errors.reject("dateRange")` ran. What does `hasErrors()` return? **`true`**, because a global error counts as an error. `getFieldErrors()` can still be empty.

**Scenario F.** `@Min(1) @RequestParam int page` is violated in Spring MVC 6.1+. Should you add a `BindingResult` after `page` as if it were a form object? **No.** That is a method-parameter constraint; look at `HandlerMethodValidationException` and method validation handling.

## 12. Key Takeaways and Reference Links

- `Errors` is the API for working with errors; `BindingResult extends Errors`, adding binding-specific details.
- In a controller signature, **each `Errors`/`BindingResult` must immediately follow the argument whose errors it captures**.
- Form property binding and JSON HTTP message conversion are separate input pipelines; failures occurring before the controller runs do not automatically flow into a controller's `BindingResult`.
- `@Valid` triggers constraint validation; `BindingResult` determines whether errors are delivered to the controller in supported cases; the controller must check for errors.
- Use `FieldError` for fields and `ObjectError` for objects; design stable, safe, localizable error responses.

Official documentation for Spring Framework 6.2:

1. [Spring MVC — Supported Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html): placement rules for `Errors`/`BindingResult` relative to validated objects.
2. [Spring MVC — @ModelAttribute Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding and error handling for command objects.
3. [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): message converters, Bean Validation, and `Errors`.
4. [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException`, `HandlerMethodValidationException`, and method validation from 6.1.
5. [Errors Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html): `hasErrors`, `getFieldErrors`, `reject`, and `rejectValue`.
6. [BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html): `getTarget`, `getSuppressedFields`, `getModel`.
