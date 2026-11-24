# Distinguishing Stable Error Codes from Translated Messages in Spring Validation

## 1. Why Does an API Need Both `code` and `message`?

A multilingual Spring MVC application must solve **two distinct responsibilities** when input data is invalid:

1. Provide a **stable error identifier that clients can process reliably**, such as `NAME_REQUIRED`, `EMAIL_INVALID`, `AGE_TOO_YOUNG`, or `INVALID_TYPE`.
2. Provide a **human-readable message in the user's language**, such as “Name is required” or “Tên không được để trống”.

The two must not be conflated. The error code belongs to the **client–server contract**; the message belongs to the **presentation layer, which can be interpolated and translated**. Updating phrasing, switching languages, fixing punctuation, or adding interpolation arguments should never force the frontend to rewrite error-handling branches.

Example of the same error:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "name",
      "code": "NAME_REQUIRED",
      "message": "Name is required"
    }
  ]
}
```

For Vietnamese users:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "name",
      "code": "NAME_REQUIRED",
      "message": "Tên không được để trống"
    }
  ]
}
```

**Invariant:** `VALIDATION_FAILED` and `NAME_REQUIRED` stay the same. **Variable:** the `message` string depends on `Locale`, translation resources, and how the application chooses wording. Clients should use `code` to decide UI state, navigation, or corrective actions; `message` is for human display.

This lesson sits within the **Internationalized Messages** topic of Spring Framework validation/data binding, focusing on **Spring `MessageSource`**, `Errors`/`BindingResult`, `FieldError`, `MessageCodesResolver`, Jakarta Validation, and stable API code design. Runnable examples use **Java 17, Spring Boot 3.x / Spring Framework 6.x, and MockMvc**.

## 2. Three Kinds of “Error Codes” Commonly Confused

In Spring, the word “code” can refer to **three different kinds of data**:

| Kind | Example | Owner | Should It Be Used Directly as a Permanent API Code? |
| --- | --- | --- | --- |
| **Business/API error code** | `NAME_REQUIRED` | Defined and versioned by the application | **Yes**, when published in the API contract |
| **Spring message lookup code** | `NotBlank.signup.name`, `NotBlank.name`, `NotBlank` | `DefaultMessageCodesResolver`, object name, and validator | Should not be coupled to directly |
| **Interpolated message** | `Tên không được để trống` | `MessageSource`, `Locale`, validation provider | **No**, because wording can change |

A `@NotBlank` error on field `name` of model attribute `signup` can carry an array of lookup codes ordered by specificity:

```text
NotBlank.signup.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
```

This example follows **`DefaultMessageCodesResolver`** and a `String` field type. The order and count of codes can vary depending on how the error was created, the object name, field path, property type, or a customized `MessageCodesResolver`. Spring uses those codes to **look up messages**; it does not promise that the first code is an immutable public identifier.

### Common Misconception: FieldError#getCode()

`ObjectError#getCode()` typically returns the **first code** from the `getCodes()` array. For the error above, that may be `NotBlank.signup.name`, **not necessarily** `NotBlank`. Consequently, two errors from the same `@NotBlank` constraint on differently named model attributes can yield different `getCode()` values.

Example:

```java
String firstCode = fieldError.getCode();
String[] candidates = fieldError.getCodes();
String defaultText = fieldError.getDefaultMessage();
```

This is a fragment where `fieldError` is provided inside a handler or validator. Meaning:

- `getCode()`: one prioritized lookup code, often specific to the object/field.
- `getCodes()`: ordered lookup codes for `MessageSource`.
- `getDefaultMessage()`: fallback message stored in the error object; with Jakarta Validation, this may already be the sentence interpolated at validation time.
- **None of these three fields guarantees a “stable API error code” by itself.** For a public contract, define a dedicated mapping layer or use application-owned codes and audit changes during refactoring.

## 3. MessageSource Uses Codes to Fetch Wording by Locale

`org.springframework.context.MessageSource` provides common lookup patterns:

```java
// Message key + arguments + locale:
String text = messageSource.getMessage(
        "api.error.NAME_REQUIRED",
        null,
        locale
);

// Explicit fallback if the key does not exist:
String safeText = messageSource.getMessage(
        "api.error.NAME_REQUIRED",
        null,
        "Invalid field",
        locale
);

// Directly accepting a Spring MessageSourceResolvable:
String resolved = messageSource.getMessage(
        fieldError, locale
);
```

This is a **fragment**. The three calls serve different goals:

1. Looking up an **application-defined** key: useful for keeping messages translatable while API codes stay fixed.
2. Looking up the same key with a **safe default message** if a translation has not been added yet.
3. Passing `FieldError#getCodes()` and its default message directly to resolve the validation framework's message; suitable for form rendering or places that adopt Spring's message-code conventions.

**Which approach to pick?** Both can coexist, yet a long-lived API design should draw clear boundaries:

- **Public code**: stable identifier such as `NAME_REQUIRED`, known to clients.
- **Internal lookup key**: resource bundle key such as `api.error.NAME_REQUIRED`; can maintain a 1-to-1 mapping for easy governance, without requiring clients to send that key.
- **Localized text**: result from `MessageSource` for a specific `Locale`.

### MessageSourceResolvable and DefaultMessageCodesResolver

`FieldError` implements `MessageSourceResolvable` via `ObjectError`. `MessageSource#getMessage(resolvable, locale)` checks candidate codes in order, then falls back to the default message if none match. By default, Spring can generate multiple codes of decreasing specificity, for example:

```text
typeMismatch.signup.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
```

This mechanism is helpful for writing a general type-conversion message or field-specific phrasing. However, renaming the command object from `signup` to `registration` changes the first code even though the business error is still **“age has the wrong type”**. Mapping the API error to `INVALID_TYPE` avoids that coupling.

**Never reverse-engineer errors from translated sentences**:

```java
// Anti-pattern:
if ("Name is required".equals(fieldError.getDefaultMessage())) {
    // ...
}
```

When the locale switches to Vietnamese, wording changes, or the annotation message is updated, this branch breaks. Rely on constraint/binding metadata, controlled internal codes, or error codes defined in the business layer.

## 4. Error Sources Do Not Always Share the Same Exception

In Spring MVC, input errors occur across multiple stages:

| Error Source | Example | Spring Signal | Suggested API Code |
| --- | --- | --- | --- |
| Property binding/type conversion | `age=abc` for `Integer age` | `FieldError.isBindingFailure() == true` | `INVALID_TYPE` |
| Jakarta constraint on model | `@NotBlank` with empty name | `FieldError.getCodes()` may contain `NotBlank` | `NAME_REQUIRED` |
| Jakarta constraint on model | `@Min(18)` with `age=16` | Candidate code `Min` | `AGE_TOO_YOUNG` |
| Custom Spring `Validator` | Reserved name `admin` | `rejectValue("name","signup.name.reserved")` | `NAME_RESERVED` |
| Field outside allowlist | `role=ADMIN` when blocked by `setAllowedFields` | `BindingResult#getSuppressedFields()` | `DISALLOWED_FIELDS` |
| Malformed JSON syntax | `{"age":,}` | `HttpMessageNotReadableException` | `REQUEST_BODY_UNREADABLE` |
| Method validation error | Direct `@Min` on `@RequestParam` | Potentially `HandlerMethodValidationException` | `METHOD_VALIDATION_FAILED` |
| Service business rule | Duplicate email in DB | Dedicated service exception/result | `EMAIL_ALREADY_EXISTS` |

This table shows **API design suggestions**, not built-in Spring constants. Codes must be documented by the application; never treat examples like `NAME_REQUIRED` as framework constants.

**Important:** JSON syntax errors do not necessarily pass through the same `BindingResult` as `@ModelAttribute`. A `@RequestBody` endpoint needs a corresponding converter exception handler. Do not lump every HTTP 400 into a “NotBlank” error or expect `MessageSource` to distinguish them automatically.

## 5. Designing an Error Contract That Stays Stable Over Time

A practical design covers three parts:

1. **Request-level code**: `VALIDATION_FAILED` for a group of field validations; or `REQUEST_BODY_UNREADABLE` for an unreadable body.
2. **Field-level code**: `NAME_REQUIRED`, `EMAIL_INVALID`, `INVALID_TYPE`; include `field` only when the error truly relates to a property.
3. **Translated message**: concise, understandable to users, without leaking implementation details.

Example:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Some submitted values are invalid",
  "errors": [
    {
      "field": "age",
      "code": "AGE_TOO_YOUNG",
      "message": "Age must be at least 18"
    }
  ]
}
```

In Vietnamese:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Một số giá trị gửi lên không hợp lệ",
  "errors": [
    {
      "field": "age",
      "code": "AGE_TOO_YOUNG",
      "message": "Tuổi phải từ 18 trở lên"
    }
  ]
}
```

Do not use the HTTP status as the sole business code. Two errors can share HTTP **400 Bad Request** while requiring different corrective actions from the client. Conversely, a business code can be paired with a contracted HTTP status; changing that status impacts clients, caches, retries, and monitoring.

### Traits of Good API Codes

- **Stable** across languages and message copy edits.
- **Specific enough** for the frontend to classify and guide users.
- **Never leaks** class names, stack traces, internal table names, emails, or rejected values.
- **Documentable** via a table mapping code → meaning → remediation.
- **Independent** of controller method names, JavaBean names, and internal `DefaultMessageCodesResolver` ordering.
- **Consistent** across frontend, backend, and logging/tracing.
- Includes a non-breaking fallback for unknown errors, such as `INVALID_FIELD` or `VALIDATION_FAILED`.

### What to Avoid

- Client writing `if (error.message === "Email is invalid")`.
- Server returning `getDefaultMessage()` in the `code` field.
- Server exposing `typeMismatch.signup.age` as a public contract without a versioning policy.
- Server serializing raw `FieldError` or `ConstraintViolation` objects into HTTP responses.
- Server changing `NAME_REQUIRED` to `TEN_BAT_BUOC` when the UI switches to Vietnamese.
- Each endpoint inventing a new error code for the exact same rule, forcing clients into unnecessary branches.

## 6. Complete Java 17 Example: One Code, Two Languages

We will build a Spring Boot MVC application with the endpoint:

`POST /signups` accepting `application/x-www-form-urlencoded` with fields `name`, `email`, and `age`.

Requirements:

- `name` must not be blank; `admin` is reserved by a Spring `Validator`.
- `email` must not be blank and must match email format.
- `age` must be a valid integer and at least 18.
- `role` must not be bound from the request even though the DTO intentionally has a setter, demonstrating suppressed-field handling.
- `Accept-Language: en` / `Accept-Language: vi` switches the messages.
- Request-level and field-level `code`s **never change with locale**.
- Errors are sorted so responses and tests are deterministic, independent of validator iteration order.

We intentionally choose **form-urlencoded / `@ModelAttribute`** to observe `BindingResult`, a custom Spring `Validator`, and `getSuppressedFields()`. With JSON `@RequestBody`, the conversion pipeline differs; Section 11/10 clarifies these boundaries.

### 6.1. Project Structure

```text
stable-error-code-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── StableCodeApplication.java
    │   │   ├── SignupForm.java
    │   │   ├── SignupNameValidator.java
    │   │   └── SignupController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── messages.properties
    │       └── messages_vi.properties
    └── test/java/demo/
        └── SignupLocalizationTest.java
```

### 6.2. pom.xml

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
    <artifactId>stable-error-code-demo</artifactId>
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

`spring-boot-starter-validation` adds the Jakarta Bean Validation provider. Do not assume `spring-boot-starter-web` alone always includes Bean Validation across all Spring Boot generations.

### 6.3. src/main/java/demo/StableCodeApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StableCodeApplication {
    public static void main(String[] args) {
        SpringApplication.run(StableCodeApplication.class, args);
    }
}
```

The main class sits in package `demo` to scan the controller. There is no need to declare `MessageSource` manually in this example because Spring Boot auto-configures it from `messages.properties` at the classpath root.

### 6.4. src/main/java/demo/SignupForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank(message = "{signup.name.required}")
    private String name;

    @NotBlank(message = "{signup.email.required}")
    @Email(message = "{signup.email.invalid}")
    private String email;

    @NotNull(message = "{signup.age.required}")
    @Min(value = 18, message = "{signup.age.min}")
    private Integer age;

    // Sensitive field with a setter solely to demonstrate mass-assignment protection.
    private String role = "USER";

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

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }
}
```

Annotations `@NotBlank`, `@Email`, `@NotNull`, and `@Min` declare Jakarta Validation constraints. `message = "{signup.name.required}"` is the validator's **message interpolation key**, **not an API code**.

In a Spring Boot application with a properly configured validation provider and `MessageSource`, Spring can integrate message bundles into Bean Validation interpolation. Yet even when the validator's default message has already been interpolated, the demo endpoint **does not use that prose verbatim as the error identifier**.

### 6.5. src/main/java/demo/SignupNameValidator.java

```java
package demo;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class SignupNameValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;

        if ("admin".equalsIgnoreCase(form.getName())) {
            errors.rejectValue(
                    "name",
                    "signup.name.reserved",
                    "Name is reserved"
            );
        }
    }
}
```

This is a **Spring `Validator`**, not `jakarta.validation.Validator`. When `name=admin`, it creates a `FieldError` with an application-chosen base code (`signup.name.reserved`). Spring can still generate object/field-specific variants from that code; the demo API maps this code group to **`NAME_RESERVED`**.

Do not call `String#equalsIgnoreCase` on a potentially null `form.getName()` without a null check. Here the code invokes the method on the **string literal** `"admin"`, which is safe when the user omits `name`.

### 6.6. src/main/java/demo/SignupController.java

```java
package demo;

import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import jakarta.validation.Valid;
import org.springframework.context.MessageSource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SignupController {

    private final MessageSource messages;

    public SignupController(MessageSource messages) {
        this.messages = messages;
    }

    @InitBinder("signup")
    public void initSignup(WebDataBinder binder) {
        binder.setAllowedFields("name", "email", "age");
        binder.addValidators(new SignupNameValidator());
    }

    public record FieldIssue(
            String field,
            String code,
            String message) {
    }

    public record ApiError(
            String code,
            String message,
            List<FieldIssue> errors) {
    }

    @PostMapping(
            path = "/signups",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> submit(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult result,
            Locale locale) {

        if (result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body(
                    new ApiError(
                            "DISALLOWED_FIELDS",
                            message("DISALLOWED_FIELDS", locale),
                            List.of()
                    ));
        }

        if (result.hasErrors()) {
            List<FieldIssue> issues = result.getFieldErrors().stream()
                    .map(error -> {
                        String code = stableCode(error);
                        return new FieldIssue(
                                error.getField(),
                                code,
                                message(code, locale)
                        );
                    })
                    .sorted(Comparator
                            .comparing(FieldIssue::field)
                            .thenComparing(FieldIssue::code))
                    .toList();

            return ResponseEntity.badRequest().body(
                    new ApiError(
                            "VALIDATION_FAILED",
                            message("VALIDATION_FAILED", locale),
                            issues
                    ));
        }

        return ResponseEntity.ok(Map.of(
                "status", "accepted",
                "name", form.getName()
        ));
    }

    private String message(String code, Locale locale) {
        return messages.getMessage(
                "api.error." + code,
                null,
                "Invalid input",
                locale
        );
    }

    private static boolean hasCode(
            FieldError error, String candidate) {
        String[] codes = error.getCodes();
        return codes != null
                && Arrays.asList(codes).contains(candidate);
    }

    private static String stableCode(FieldError error) {
        // Type conversion failed: do not confuse with @Min/@NotNull.
        if (error.isBindingFailure()) {
            return "INVALID_TYPE";
        }

        String field = error.getField();

        if ("name".equals(field)) {
            if (hasCode(error, "signup.name.reserved")) {
                return "NAME_RESERVED";
            }
            if (hasCode(error, "NotBlank")) {
                return "NAME_REQUIRED";
            }
        }

        if ("email".equals(field)) {
            if (hasCode(error, "NotBlank")) {
                return "EMAIL_REQUIRED";
            }
            if (hasCode(error, "Email")) {
                return "EMAIL_INVALID";
            }
        }

        if ("age".equals(field)) {
            if (hasCode(error, "NotNull")) {
                return "AGE_REQUIRED";
            }
            if (hasCode(error, "Min")) {
                return "AGE_TOO_YOUNG";
            }
        }

        // Public fallback code; do not expose internal codes.
        return "INVALID_FIELD";
    }
}
```

This is a **runnable controller** alongside the preceding files. Key highlights:

1. `@InitBinder("signup")` matches the exact `objectName` from `@ModelAttribute("signup")`.
2. `setAllowedFields(...)` prevents property binding outside `name/email/age`. If `role=ADMIN` is sent, `getSuppressedFields()` reports the blocked field; the endpoint returns `DISALLOWED_FIELDS`.
3. `@Valid` enables Jakarta Validation, while `addValidators(...)` appends the Spring `Validator` without replacing the global validator.
4. `BindingResult` immediately after the form object gives the controller access to field errors, global errors, and suppressed fields.
5. `stableCode(...)` maps Spring metadata into a **stable API-owned vocabulary**. This is the single place to update when constraints or policies change.
6. `message(...)` looks up `api.error.CODE` using `Locale`. Never translate `CODE` itself.
7. The error list is sorted by `field` then `code`, since validator error ordering is not guaranteed.
8. Never emit `getRejectedValue()` or full exceptions in responses.

**Note:** the example serializes only **field errors**, omitting global errors from `errors.reject(...)`. For forms with cross-field constraints, extend `ApiError` to hold object-level errors and define corresponding API codes. Never force an object-wide error onto an arbitrary field.

### 6.7. src/main/resources/application.properties

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Meaning:

- Spring Boot resolves `messages.properties` and `messages_vi.properties` according to `Locale`.
- UTF-8 supports Vietnamese diacritics in text resources.
- `fallback-to-system-locale=false` avoids depending on the host/CI server's implicit locale when a resource is missing. When a locale translation is absent, the system falls back to the base bundle as configured.

**Important:** Spring Boot auto-configures `MessageSource` from this basename only when the **base bundle file** (`messages.properties`) is present. If a project only has `messages_vi.properties`, do not assume auto-config will work as expected.

### 6.8. src/main/resources/messages.properties

```properties
# Message keys for annotations / Jakarta Bean Validation:
signup.name.required=Name is required
signup.email.required=Email is required
signup.email.invalid=Email must be valid
signup.age.required=Age is required
signup.age.min=Age must be at least 18
signup.name.reserved=This name is reserved

# Public API messages, driven by stable error code:
api.error.VALIDATION_FAILED=Some submitted values are invalid
api.error.DISALLOWED_FIELDS=This request contains fields that cannot be changed
api.error.INVALID_TYPE=Value has an invalid type
api.error.NAME_REQUIRED=Name is required
api.error.NAME_RESERVED=This name is reserved
api.error.EMAIL_REQUIRED=Email is required
api.error.EMAIL_INVALID=Email must be valid
api.error.AGE_REQUIRED=Age is required
api.error.AGE_TOO_YOUNG=Age must be at least 18
api.error.INVALID_FIELD=One field is invalid
```

Here there are **two namespaces serving translation with different purposes**:

- `signup.*`: used as interpolation keys for annotations and the custom Spring `Validator`; can evolve with form design.
- `api.error.*`: used to render explanations for **published stable error codes**; owned and versioned alongside the API.

Having identical text in both sets is intentional for this lesson. In real projects, you can organize resources across multiple files or reuse `MessageFormat` to reduce duplication, as long as you preserve the boundary: “invariant API code, customizable localized message”.

### 6.9. src/main/resources/messages_vi.properties

```properties
signup.name.required=Tên không được để trống
signup.email.required=Email không được để trống
signup.email.invalid=Địa chỉ email không hợp lệ
signup.age.required=Tuổi là bắt buộc
signup.age.min=Tuổi phải từ 18 trở lên
signup.name.reserved=Tên này đã được dành riêng

api.error.VALIDATION_FAILED=Một số giá trị gửi lên không hợp lệ
api.error.DISALLOWED_FIELDS=Yêu cầu chứa trường không được phép thay đổi
api.error.INVALID_TYPE=Giá trị không đúng kiểu dữ liệu
api.error.NAME_REQUIRED=Tên không được để trống
api.error.NAME_RESERVED=Tên này đã được dành riêng
api.error.EMAIL_REQUIRED=Email không được để trống
api.error.EMAIL_INVALID=Địa chỉ email không hợp lệ
api.error.AGE_REQUIRED=Tuổi là bắt buộc
api.error.AGE_TOO_YOUNG=Tuổi phải từ 18 trở lên
api.error.INVALID_FIELD=Một trường có giá trị không hợp lệ
```

Compare the two files: the **keys are completely identical**, while the **values are translated**. Do not rename `api.error.NAME_REQUIRED` to `api.error.TEN_BAT_BUOC` when creating Vietnamese resources. If a locale is missing a key, fallback behavior per `MessageSource` config must be tested.

**Unlike API codes**: `NAME_REQUIRED` has no diacritics, never changes by locale, and is typically used like an enum/string constant on clients. Messages are free to change for clarity, tone, or regional phrasing.

### 6.10. src/test/java/demo/SignupLocalizationTest.java

```java
package demo;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupLocalizationTest {

    private static final Locale VI = Locale.forLanguageTag("vi");
    private static final Locale EN = Locale.ENGLISH;

    @Autowired
    MockMvc mvc;

    private ResultActions signup(Locale locale, String... fields)
            throws Exception {
        MockHttpServletRequestBuilder request =
                post("/signups")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .locale(locale);

        for (int i = 0; i < fields.length; i += 2) {
            request.param(fields[i], fields[i + 1]);
        }
        return mvc.perform(request);
    }

    @Test
    void validRequestWorksInVietnamese() throws Exception {
        signup(VI,
                "name", "Lan",
                "email", "lan@example.org",
                "age", "22")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("accepted"))
                .andExpect(jsonPath("$.name").value("Lan"));
    }

    @Test
    void requiredNameHasEnglishMessage() throws Exception {
        signup(EN,
                "name", "",
                "email", "lan@example.org",
                "age", "22")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("NAME_REQUIRED"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Name is required"));
    }

    @Test
    void requiredNameHasSameCodeInVietnamese()
            throws Exception {
        signup(VI,
                "name", "",
                "email", "lan@example.org",
                "age", "22")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.message")
                        .value("Một số giá trị gửi lên không hợp lệ"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("NAME_REQUIRED"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tên không được để trống"));
    }

    @Test
    void invalidEmailUsesStableCode() throws Exception {
        signup(VI,
                "name", "Lan",
                "email", "not-an-email",
                "age", "22")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("email"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("EMAIL_INVALID"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Địa chỉ email không hợp lệ"));
    }

    @Test
    void ageBelowMinimumIsConstraintViolation()
            throws Exception {
        signup(EN,
                "name", "Lan",
                "email", "lan@example.org",
                "age", "16")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code")
                        .value("AGE_TOO_YOUNG"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Age must be at least 18"));
    }

    @Test
    void wrongAgeTypeIsNotMinConstraint() throws Exception {
        signup(VI,
                "name", "Lan",
                "email", "lan@example.org",
                "age", "abc")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code")
                        .value("INVALID_TYPE"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Giá trị không đúng kiểu dữ liệu"));
    }

    @Test
    void reservedNameIsLocalized() throws Exception {
        signup(VI,
                "name", "admin",
                "email", "admin@example.org",
                "age", "22")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code")
                        .value("NAME_RESERVED"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tên này đã được dành riêng"));
    }

    @Test
    void missingAgeMapsToRequiredCode() throws Exception {
        signup(EN,
                "name", "Lan",
                "email", "lan@example.org")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code")
                        .value("AGE_REQUIRED"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Age is required"));
    }

    @Test
    void disallowedFieldIsIndependentOfLocale()
            throws Exception {
        signup(EN,
                "name", "Lan",
                "email", "lan@example.org",
                "age", "22",
                "role", "ADMIN")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.message")
                        .value("This request contains fields that cannot be changed"))
                .andExpect(jsonPath("$.errors.length()")
                        .value(0));
    }

    @Test
    void localeFallbackKeepsStableCode() throws Exception {
        signup(Locale.FRENCH,
                "name", "",
                "email", "lan@example.org",
                "age", "22")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code")
                        .value("NAME_REQUIRED"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Name is required"));
    }
}
```

The ten tests demonstrate the essential behaviors:

- **Same error + different locales**: `NAME_REQUIRED` stays unchanged while `message` switches from English to Vietnamese.
- **Distinct errors**: `EMAIL_INVALID`, `AGE_TOO_YOUNG`, `AGE_REQUIRED`, `INVALID_TYPE`, and `NAME_RESERVED` have clearly differentiated codes.
- **Suppressed field**: dedicated request-level code without translating the code itself.
- **Locale fallback**: when no French bundle exists, the app uses the configured default resource.
- **Happy path**: when valid, the controller processes the form and returns 200.

Run with JDK 17+ and Maven:

```bash
mvn -q clean test
```

**Expected**: 10 tests pass, Maven exit code 0 when dependencies are available. No fixed Maven stdout is printed here because plugins, logs, and OS output vary. The tests assert **specific codes and messages defined by the application**, independent of Hibernate Validator's default wording.

Run the server:

```bash
mvn spring-boot:run
```

Send the same error in two languages from a POSIX shell:

```bash
curl -i -X POST 'http://localhost:8080/signups' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Accept-Language: en' \
  --data-urlencode 'name=' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'age=22'

curl -i -X POST 'http://localhost:8080/signups' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Accept-Language: vi' \
  --data-urlencode 'name=' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'age=22'
```

Expected English response:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Some submitted values are invalid",
  "errors": [
    {
      "field": "name",
      "code": "NAME_REQUIRED",
      "message": "Name is required"
    }
  ]
}
```

Expected Vietnamese response:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Một số giá trị gửi lên không hợp lệ",
  "errors": [
    {
      "field": "name",
      "code": "NAME_REQUIRED",
      "message": "Tên không được để trống"
    }
  ]
}
```

Key order inside a JSON object is not an API contract. `code` and `field` are what must stay stable; `message` must be translated accurately for the locale. Tests avoid matching default framework messages, which can change across bundles, providers, and versions.

## 7. Locale Selection Rules and Accept-Language

Spring MVC provides the `LocaleResolver` mechanism. In a typical Boot MVC app, `AcceptHeaderLocaleResolver` is used by default and reads language preferences from the `Accept-Language` header. Example:

```http
POST /signups HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Accept-Language: vi
```

This is a header fragment, not a complete HTTP request. A browser might send:

```text
Accept-Language: vi-VN,vi;q=0.9,en;q=0.8
```

The server should select a supported `Locale` via its resolver/configuration. You can configure supported locales, a default locale, or a user-account locale preference. **Do not force `Locale` from arbitrary query parameters** when the system contract specifies headers or saved preferences.

### 7.1. Validation Locale vs. API Message Locale

Messages are interpolated in at least two places:

1. **Validator**: the Jakarta validation provider can turn `{signup.name.required}` into a Vietnamese/English sentence when creating a `ConstraintViolation`.
2. **API rendering**: the controller calls `MessageSource.getMessage("api.error.NAME_REQUIRED", ..., locale)` to produce the public `message`.

If the two places use different `Locale`s or bundles, a single response can mix languages. Therefore, choose **one consistent locale strategy** and test with real request locales rather than only instantiating `new ResourceBundleMessageSource()` in isolation.

In the demo project, API messages are determined by `MessageSource` and the controller's `Locale locale` parameter. The validator can interpolate annotation messages, yet the **public response does not copy `defaultMessage` verbatim**, preserving full control over schema and wording.

### 7.2. Fallbacks and the Base File

With `messages.properties` as the English default and `messages_vi.properties` for Vietnamese, setting `spring.messages.fallback-to-system-locale=false` ensures unsupported locales (such as `fr`) use the base bundle instead of accidentally picking the host server's locale.

Define a clear policy:

- `en`: serve English.
- `vi`: serve Vietnamese.
- Unsupported locale: serve the default language or an error per policy, **while keeping API codes unchanged**.

If a key is missing in a translation file, the application can fall back to the corresponding key in the base bundle. Test critical keys and add CI checks so you never ship a locale missing large sets of keys.

### 7.3. MessageFormat and Interpolation Arguments

When a message takes arguments:

```properties
api.error.AGE_TOO_YOUNG=Age must be at least {0}
```

Lookup:

```java
String text = messageSource.getMessage(
        "api.error.AGE_TOO_YOUNG",
        new Object[]{18},
        Locale.ENGLISH
);
```

This is a fragment. The expected result is `Age must be at least 18`. In Vietnamese, you can use `Tuổi phải từ {0} trở lên` while `AGE_TOO_YOUNG` stays unchanged.

**Note:** `MessageFormat` uses curly braces for placeholders; single quotes have their own escaping rules. Never concatenate raw user input into message template files or responses to avoid formatting errors and data-leak risks. Test messages with arguments and pluralization when required by the product.

## 8. Must Every FieldError Map to Its Own Dedicated Code?

No. There are two design approaches:

### Approach A — General Codes Grouped by Constraint

For example `REQUIRED`, `INVALID_FORMAT`, `OUT_OF_RANGE`, `INVALID_TYPE`. The response includes `field` to pinpoint the location.

Pros: fewer codes to maintain, well suited for large form-heavy apps. Cons: clients must interpret a generic code per field and may miss nuanced business scenarios.

### Approach B — Business-Specific Codes

For example `NAME_REQUIRED`, `EMAIL_INVALID`, `AGE_TOO_YOUNG`, `NAME_RESERVED`. Pros: explicit and easy to bind to specific UX behaviors. Cons: more codes to govern and version carefully.

The runnable example uses **Approach B for common constraints**, while providing `INVALID_TYPE` and `INVALID_FIELD` as general codes to reduce coupling. In large systems, both can be combined:

```json
{
  "field": "age",
  "code": "OUT_OF_RANGE",
  "rule": "minimum",
  "message": "Age must be at least 18"
}
```

This is an **optional schema example**, not the output of the demo project. If `rule` is part of the public contract, it must also be versioned rather than changed arbitrarily.

### Avoid Mapping by Position in `getCodes()`

Wrong:

```java
String stable = fieldError.getCodes()[0];
```

Problem: the first code usually depends on `objectName` and `field`, such as `Min.signup.age`. Refactoring a form name can break clients even though the “minimum age 18” rule has not changed.

Better as in the example: check whether candidate `"Min"` exists in the array alongside field `"age"`. In systems needing high stability, map through a thoroughly unit-tested adapter/enum, or emit domain validation codes directly from services without relying on a message resolver.

**Do not over-rely on implicit mapping**: if you swap a Jakarta constraint for a custom validator, rename a field, or change `MessageCodesResolver`, update the adapter and tests. A stable API does not mean “the mapping is never touched”; it means **changing internals without arbitrarily breaking published codes**.

## 9. Distinguishing `defaultMessage`, Message Template, and Final Message

In Jakarta Bean Validation:

- `@NotBlank(message = "{signup.name.required}")`: the string in the annotation is the **message template**, which may reference a resource bundle.
- The Bean Validation provider interpolates the template into a **rendered message** according to locale and constraint attributes.
- The Spring adapter converts violations into `FieldError`/`ObjectError` inside `BindingResult`.
- `FieldError.getDefaultMessage()` usually receives the interpolated message; however, the exact outcome depends on the provider, adapter, and evaluation timing.

In Spring `Errors.rejectValue(...)`:

```java
errors.rejectValue(
        "name",
        "signup.name.reserved",
        "Name is reserved"
);
```

The third argument is the **`defaultMessage`** for that error. When calling `messageSource.getMessage(fieldError, locale)`, Spring tries candidate codes first and only falls back to the default. Thus, a resource bundle entry `signup.name.reserved=...` can override the default sentence per locale.

Key distinctions:

| Value | Role | Locale-dependent? |
| --- | --- | --- |
| `"signup.name.reserved"` | Internal message code set by app on reject | Code name stays fixed |
| `"signup.name.required"` | Key in annotation message template | Key name stays fixed |
| `"NotBlank.signup.name"` | Spring candidate lookup code | Can change when object/field changes |
| `"NAME_REQUIRED"` | Public API code | **Must stay stable** |
| `"Tên không được để trống"` | Localized message | **Changes by locale** |

A codebase is much easier to maintain when team members do not overload a single variable named `errorCode` to hold an API code in one place, a message key in another, and translated text elsewhere.

## 10. Handling JSON Errors, Method Validation, and Service Errors

The runnable project in Section 6 uses form-urlencoded to demonstrate `BindingResult`. However, an API often receives JSON and validates across multiple layers.

### 10.1. `@Valid @RequestBody` with Valid JSON

Illustrative fragment in a REST controller:

```java
@PostMapping("/api/users")
ResponseEntity<?> create(
        @Valid @RequestBody CreateUserRequest request) {
    return ResponseEntity.ok().build();
}
```

If JSON parses cleanly yet the DTO violates constraints, Spring MVC normally throws `MethodArgumentNotValidException`. In `@RestControllerAdvice`, you can pass `ex.getBindingResult().getFieldErrors()` through the **same `stableCode(...)` adapter** to emit public API codes rather than letting every endpoint invent its own format.

**Caveat:** with direct constraints on method parameters, Spring MVC 6.1+ may throw `HandlerMethodValidationException`. It does not have the exact same structure as a standalone `BindingResult`; add a corresponding adapter for `ParameterValidationResult`.

### 10.2. Malformed or Undeserializable JSON

```text
{"age":,}
```

This is **syntactically invalid** JSON, wrapped in a `text` code fence so it is not presented as valid JSON. Spring MVC typically throws `HttpMessageNotReadableException`. There is no valid DTO to run `@Min` against, so never emit `AGE_TOO_YOUNG` just because the word `age` appears in the payload.

Return instead:

```json
{
  "code": "REQUEST_BODY_UNREADABLE",
  "message": "Request body cannot be read"
}
```

In Vietnamese, only `message` changes. Never return raw Jackson exceptions, stack traces, or internal property paths in the response. If you need to distinguish **malformed syntax** from **type mismatch**, add controlled mapping over the exception cause with a safe general fallback.

### 10.3. Method Validation and `BindingResult` Scope

Illustrative fragment:

```java
@GetMapping("/search")
ResponseEntity<?> search(
        @RequestParam @Min(1) int page) {
    return ResponseEntity.ok().build();
}
```

With `page=0`, Spring MVC can apply built-in method validation (Framework 6.1+) and raise `HandlerMethodValidationException`. To keep the response schema uniform, the handler should map method validation results to codes like `PAGE_OUT_OF_RANGE` or `METHOD_VALIDATION_FAILED` and interpolate the message by locale.

If `page=abc` cannot convert to `int`, that is a **parameter type conversion error**, not `@Min(1)`. The code can be `INVALID_TYPE`. Do not assume every HTTP 400 provides a `FieldError` usable by a single mapper.

### 10.4. Business Errors and HTTP Status

For example, a service returns `EMAIL_ALREADY_EXISTS` when an email collides with a unique index. The client can display Vietnamese or English via key `api.error.EMAIL_ALREADY_EXISTS`. However, the HTTP status may be **409 Conflict** or **422** per API contract instead of defaulting to 400. Choose consistent statuses and document them; never let a language change alter the HTTP status.

Note on race conditions: “checking if email exists” before inserting does not eliminate races; the database still needs a unique constraint or equivalent consistency guarantee. When mapping database errors to API codes, expose only safe details—never constraint or table names.

## 11. `ProblemDetail` / RFC 9457 and Stable Error Codes

Spring Framework supports `ProblemDetail` and the `ErrorResponse` interface to produce responses following the problem details format (RFC 9457). Standard fields have defined meanings:

- `type`: identifies the problem category, usually a URI.
- `title`: short summary, can use human-friendly language.
- `status`: HTTP status.
- `detail`: explanation of the problem.
- `instance`: URI pointing to the specific occurrence if appropriate.

Suggested example:

```json
{
  "type": "https://api.example.org/problems/validation-failed",
  "title": "Invalid input",
  "status": 400,
  "detail": "Some submitted values are invalid",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "name",
      "code": "NAME_REQUIRED",
      "message": "Name is required"
    }
  ]
}
```

This is an **advanced schema suggestion**, not the output of Section 6's runnable controller. The `code` and `errors` properties are **application-defined extensions**, not required by RFC 9457.

**Draw clear boundaries:**

- If `type` is a stable public URI identifying the error category, do not change the URI by locale.
- You can translate `title` and `detail`, while keeping `status` independent of locale.
- If adding `code`, preserve vocabulary and versioning semantics.
- Never use localized `detail` text as business-logic input on the frontend.
- When evolving the error format, maintain backwards compatibility or announce a versioned migration.

Spring can resolve messages via `MessageSource` for several standard `ErrorResponse` exceptions, yet that does not mean every exception automatically carries an **application API code**. That adapter still has to be designed.

## 12. Versioning Error Codes and Managing Translations

### 12.1. Published API Codes Are Part of the Contract

If a client wrote `switch (error.code)` for `NAME_REQUIRED`, renaming it to `MISSING_NAME` without notice is a **breaking change**. Changing “Name is required” to “Please enter your name” is generally non-breaking as long as the frontend does not inspect text.

New error codes can be **added** across versions without altering old codes, while clients should still include a fallback for unknown codes. When merging or splitting code groups, establish a deprecation/migration policy and contract tests.

### 12.2. Establish a Single Owner for the Vocabulary

A large team should maintain a backend registry or enum (e.g., `ApiErrorCode`) alongside documentation:

| API code | Meaning | Scenario | Replacement Code on Refactor |
| --- | --- | --- | --- |
| `NAME_REQUIRED` | Name is blank | Input validation | Keep unchanged |
| `EMAIL_INVALID` | Email format invalid | Input validation | Keep unchanged |
| `AGE_TOO_YOUNG` | Age below threshold | Input validation | Keep unchanged |
| `INVALID_TYPE` | Data type conversion failed | Binding / parsing | Keep unchanged |
| `NAME_RESERVED` | Name is unavailable | Business validation | Keep unchanged |
| `REQUEST_BODY_UNREADABLE` | Body cannot be read | Message converter | Keep unchanged |

Illustrative table only. You do not have to assign a separate code for every translated sentence if they express the same condition. If a rule varies by country, you can keep the same API code with different arguments or wording; if semantics genuinely differ, consider a distinct code.

### 12.3. CI Checks for Bundle Completeness

With `messages.properties` and `messages_vi.properties`, check at minimum:

1. All **keys** for public error codes are present.
2. No keys have casing typos.
3. Placeholders `{0}`, `{1}` match across languages.
4. Files are saved with proper encoding so Vietnamese diacritics never corrupt.
5. No English strings are left untranslated in the Vietnamese bundle unintentionally.
6. Messages contain no unescaped raw user input in HTML contexts.
7. Locale fallback works when a language lacks a dedicated resource.
8. Translation edits do not alter API codes in snapshot/contract tests.

A test can read bundles and compare key sets, excluding internal keys that do not require translation if the project has a clear policy. Base checks on the published list of **public error codes** rather than requiring entire properties files to be 1-to-1 identical when locales have domain-specific entries.

### 12.4. Do Not Use Messages as Metrics Labels

Monitoring should group by `code`, endpoint, and HTTP status. Grouping by `message` splits one error into multiple series across locales and copy revisions, making trend analysis and alerting noisy. Logs can include the localized message if helpful, yet should **prioritize structured fields** such as `errorCode`, `requestId`, `status`, and controlled field paths.

## 13. Common Implementation Pitfalls

### 13.1. Using `getDefaultMessage()` as the Public Code

Wrong:

```java
String apiCode = error.getDefaultMessage();
```

`getDefaultMessage()` may already be translated, come from the provider, or be a `defaultMessage` passed to `reject`; it is unsuitable as `apiCode`. Instead, map the error to an application vocabulary code, then resolve the message.

### 13.2. Treating `getCode()` as a Semantic Constant

`FieldError#getCode()` may return `NotBlank.signup.name` (the first candidate code) rather than just `NotBlank`. Renaming the model implicitly alters the API code. When mapping from `getCodes()`, treat it as **mutable framework metadata** and cover it with contract tests.

### 13.3. Translating Codes Inside Bundles

Never put `"NAME_REQUIRED"` in English and `"TEN_BAT_BUOC"` in Vietnamese in the `code` field. Translate the **message**, keep the identifier fixed.

### 13.4. Having `messages_vi.properties` Without `messages.properties`

Spring Boot needs a base bundle to auto-configure `MessageSource` as expected. With only locale-specific files and no base file, auto-configuration may not activate under Boot rules. Add the base bundle and configure the basename properly.

### 13.5. Forgetting to Set Locale in Tests

Tests running only under the developer machine's default locale can pass by coincidence. Use `MockMvc.locale(Locale.forLanguageTag("vi"))` or send `Accept-Language` and assert both `code` and `message`. Test at least two real locales plus fallback.

### 13.6. Failing to Separate Binding Failures from Constraints

`age=abc` cannot convert to `Integer`, so it must not return `AGE_TOO_YOUNG`. Check `FieldError.isBindingFailure()` or the corresponding exception before mapping `@Min`.

### 13.7. Leaking Rejected Values

`FieldError.getRejectedValue()` can hold passwords, tokens, emails, or sensitive data. Never serialize raw `BindingResult` into public API responses. Return the field name, stable code, and safe message.

### 13.8. Missing Global Errors

A validator calling `errors.reject("invalid.combination")` creates an `ObjectError`, not a `FieldError`. If responses serialize only `getFieldErrors()`, clients will miss cross-field errors. Support global errors with dedicated codes in real systems.

### 13.9. Coupling Public Codes Tightly to Constraint Annotations

If you switch from `@Email` to a custom validator while the API semantics remain “invalid email”, do not change `EMAIL_INVALID` just because framework error codes changed. Update the adapter to preserve the legacy public code. Only revisit versioning if the rule's meaning actually changes.

### 13.10. Confusing “Friendly” Messages with System Error Text

Exceptions from Jackson, databases, or Hibernate Validator can contain technical internals. Never expose `ex.getMessage()` directly to users. Public messages should be user-friendly without leaking stack traces, SQL statements, or class names.

## 14. Testing a Multilingual Error Contract

A solid test suite should cover at minimum:

| Case | Code (untranslated) | Message by Locale |
| --- | --- | --- |
| `name=""` | `NAME_REQUIRED` | English/Vietnamese |
| `name="admin"` | `NAME_RESERVED` | English/Vietnamese |
| `email="not-an-email"` | `EMAIL_INVALID` | English/Vietnamese |
| `age=16` | `AGE_TOO_YOUNG` | English/Vietnamese |
| Missing `age` | `AGE_REQUIRED` | English/Vietnamese |
| `age=abc` | `INVALID_TYPE` | English/Vietnamese |
| `role=ADMIN` | `DISALLOWED_FIELDS` | English/Vietnamese |
| Locale without bundle | Code stays fixed | Intentional fallback |
| Malformed JSON | `REQUEST_BODY_UNREADABLE` | General localized text, no raw exception |
| Command object renamed | Code stays fixed | Message via application key |
| Translation text edited | Code stays fixed | Updated message |
| Multiple field errors | Exact codes and field paths | Deterministic ordering and schema |

Do not assert only HTTP 400; a test proving the contract must verify **both the code and the localized message**. At the same time, avoid excessive assertions on default Hibernate Validator prose, which can change across versions, locales, and providers. Public codes and application-owned message resources are far better anchors for expectations.

For API snapshot tests, consider separating two layers: snapshot the stable schema/codes, and verify message localization separately. That way, a copy edit does not force the team to review dozens of snapshots unrelated to behavior.

## 15. Design Workflow for a Multilingual Product

A consistent implementation workflow:

1. **Define error conditions** that clients genuinely need to understand and fix.
2. **Assign stable codes** independent of language, with descriptions and HTTP statuses.
3. **Build an adapter** from validation/binding/business errors to stable codes.
4. **Standardize the response schema** for field/global errors and request-level errors.
5. **Create translation keys** like `api.error.CODE` plus base and locale bundles.
6. **Choose a `LocaleResolver`** and fallback policy; read locale only from intentional sources.
7. **Write multilingual tests**: same payload, unchanged code, properly switched message.
8. **Add negative cases**: conversion errors, missing values, custom validators, malformed requests.
9. **Protect sensitive data**: never serialize rejected values or raw exceptions.
10. **Monitor by code**, not by message text.
11. **Review every vocabulary change** like an API contract change.
12. **Ensure client fallback** on unknown codes without crashing.

## 16. Conclusion

In Spring Validation, there are **framework message lookup codes**, **application-defined public error codes**, and **translated display messages**. They are related, yet **must never be treated as the same thing**.

- `MessageCodesResolver` generates candidate codes for message lookup, typically depending on object name, field name, and type.
- `MessageSource` selects wording by key, arguments, and `Locale`.
- `BindingResult` and `FieldError` provide metadata so the application can identify the error; they do not define a stable API contract on their own.
- Stable public codes such as `NAME_REQUIRED` must stay intact even when messages switch between English and Vietnamese, or internals are refactored.
- For JSON decoding, method validation, business errors, or sensitive data, design proper adapters and responses instead of exposing raw exceptions.

**Most important practical rule:** *clients branch on stable error codes; users read translated messages*. When both are cleanly separated, a system can evolve its translations without breaking the contract between frontend and backend.

## References

- [Spring Framework — Resolving Error Codes to Error Messages](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [Spring Framework — Validation and Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring Framework — MessageSource interface](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/MessageSource.html)
- [Spring Framework — DefaultMessageCodesResolver API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html)
- [Spring Framework — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework — @ModelAttribute and BindingResult](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Error Responses / ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html)
- [Spring Boot 3.4 — Application Properties (spring.messages.*)](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/)
