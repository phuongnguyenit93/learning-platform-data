# Customizing Error Messages and Localization for Data Validation in Spring Boot

## 1. Problem: Validation Works, Yet Error Messages Are Not Helpful

In a Spring Boot API, two requests may both be rejected with HTTP 400, yet consumers need **two different things**: a *stable error code* for programmatic client handling and a *language-appropriate human-readable message* for display. For instance, on the same `@NotBlank` constraint for a name, a client sending `Accept-Language: vi` can receive “Tên không được để trống”, while a client sending `Accept-Language: en` receives “Name must not be blank”.

This lesson walks through a testable approach for **Spring Boot 3.5.x + Spring MVC + Jakarta Bean Validation + Java 17+**:

- Define constraints with `@NotBlank`, `@Email`, `@Min` using **message keys** instead of hardcoding messages in controllers.
- Create `messages.properties` and `messages_vi.properties` resource bundles; explain `MessageSource` and locale fallback.
- Resolve locale from `Accept-Language` via MVC `LocaleResolver`, without manually parsing headers.
- Handle `MethodArgumentNotValidException` with `@RestControllerAdvice`, returning a JSON error contract with `code`, `message`, `errors[]`.
- Distinguish object validation from malformed JSON, path/query type mismatches, missing request parameters, business rules, and method validation.
- Verify automatically with `MockMvc` across at least two languages and separate error cases.
- Keep technical internals, rejected values, tokens, and private information out of public responses.

**Core mindset:** localization changes *display messages*, not the semantics of the constraint, HTTP status, error fields, stable error codes, or API access permissions.

## 2. Distinguishing i18n, l10n, Validation, and Error Responses

- **Internationalization (i18n)**: designing the system so messages can vary by locale without modifying business logic.
- **Localization (l10n)**: providing translations and regional rules for a language/region, such as Vietnamese, English, decimal separators, and dates.
- **Validation**: determining whether data satisfies constraints, such as required name, minimum age, and valid email syntax.
- **Error response contract**: JSON sent to clients; the API defines the error code and list of field issues while selecting messages per locale.

Messages from `@NotBlank(message="...")` can be interpolated by Bean Validation. A `FieldError` from `BindingResult` is also a `MessageSourceResolvable`, carrying error codes and a default message. These two localization mechanisms are related, though not identical.

An example response structure:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu yêu cầu không hợp lệ",
  "errors": [
    {
      "field": "name",
      "message": "Tên không được để trống"
    }
  ]
}
~~~

Keep `code=VALIDATION_ERROR` identical across both languages. UI layers should branch on `code` and `field` in logic rather than comparing Vietnamese/English message text.

## 3. Processing Chain from HTTP Request to Localized Message

~~~text
POST /api/registrations
Accept-Language: vi
Content-Type: application/json
                |
                v
DispatcherServlet and LocaleResolver
  -> Request Locale (vi)
                |
                v
@RequestBody + HttpMessageConverter
  -> JSON decoded into RegistrationRequest
                |
                v
@Valid -> Validator (Hibernate Validator)
  -> check @NotBlank, @Email, @Min
  -> resolve constraint message templates from MessageSource
                |
                +-- valid -> invoke controller
                |
                +-- invalid -> BindingResult/FieldError
                              |
                              v
                 MethodArgumentNotValidException
                              |
                              v
                 @RestControllerAdvice
                   MessageSource + Locale
                              |
                              v
                 ResponseEntity<ApiError>
                 HTTP 400 + localized JSON
~~~

Different components carry different responsibilities:

| Component | What does it do? | What does it not do? |
|---|---|---|
| `@Valid` | Requests validation on supported arguments | Does not build JSON responses by itself |
| `jakarta.validation.Validator` | Evaluates constraints and produces violations | Does not pick HTTP statuses for business rules |
| `LocalValidatorFactoryBean` | Integrates Bean Validation with Spring | Does not define the public JSON schema |
| `MessageSource` | Looks up messages by code + locale and arguments | Does not decide whether the caller may view an object |
| `LocaleResolver` | Determines the HTTP request's locale | Does not automatically translate hardcoded strings |
| `BindingResult` | Holds binding/validation errors as field/global errors | Does not guarantee its contents are safe to expose publicly |
| `@RestControllerAdvice` | Maps exceptions to the API contract response | Does not replace enforcing constraints |
| `HttpMessageConverter` | Decodes/serializes HTTP bodies | Does not automatically translate arbitrary business errors |

**Order matters:** if the JSON body cannot be read, DTO validation never runs. If a query parameter fails conversion, a type mismatch error occurs before the business controller runs. Do not catch every exception as `VALIDATION_ERROR`.

## 4. MessageSource and Resource Bundles

### 4.1. Default File Must Exist

In Spring Boot 3.5, it looks by default for a bundle named `messages` at the classpath root. A standard layout:

~~~text
src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
~~~

`messages.properties` is the **default bundle** and should exist so Spring Boot auto-configures `MessageSource` per documentation. Creating only `messages_vi.properties` without a default bundle can prevent auto-configuration from activating as expected.

`messages.properties` acts as the fallback for unsupported locales; for example, choosing English as fallback. `messages_vi.properties` holds the corresponding Vietnamese translations. You can add `messages_en.properties`, `messages_en_US.properties`, or `messages_vi_VN.properties` when regional variants are needed.

Files must be packaged on the application classpath (typically inside the JAR). Configure UTF-8 encoding explicitly, especially for Vietnamese diacritics.

### 4.2. Configuring application.properties

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false

spring.web.locale=en
spring.web.locale-resolver=accept-header
~~~

Meaning:

1. `spring.messages.basename`: where to find message bundles; can be a comma-separated list across modules.
2. `spring.messages.encoding=UTF-8`: ensures accented Unicode messages are read accurately.
3. `spring.messages.fallback-to-system-locale=false`: avoids depending on the JVM/server OS locale when a translation is missing. Falls back to `messages.properties` instead of accidentally picking an OS bundle.
4. `spring.web.locale=en`: default locale when the request omits a suitable preference.
5. `spring.web.locale-resolver=accept-header`: uses the HTTP `Accept-Language` header to pick a locale when provided.

**Note:** `Accept-Language` is a language preference, not proof of geography, nationality, or user permissions. Clients can change the header arbitrarily.

If the product supports only two locales, define an intentional fallback policy and test headers such as `vi`, `vi-VN`, `en-US`, `fr`, or a missing header. `AcceptHeaderLocaleResolver` does not “translate everything” by itself—it only determines the locale; `MessageSource` still needs the messages.

### 4.3. Resolving Messages in Java

`MessageSource` supports:

~~~java
String text = messages.getMessage(
        "registration.name.required",
        null,
        locale);
~~~

This is an illustrative method snippet: `messages` is an `org.springframework.context.MessageSource`, and `locale` is the request's `java.util.Locale`. If the code does not exist and an overload **without a default message** is called, Spring can throw `NoSuchMessageException`.

When a key might be missing, you can explicitly supply a fallback:

~~~java
String safeText = messages.getMessage(
        "registration.name.required",
        null,
        "Invalid name",
        locale);
~~~

Do not enable `spring.messages.use-code-as-default-message=true` as a long-term production solution: it can expose raw internal codes like `registration.name.required` to end users instead of proper prose.

### 4.4. Message Arguments: MessageFormat

For text with variables, use message arguments:

~~~properties
errors.minimum-age=Age must be at least {0}
~~~

~~~java
String text = messages.getMessage(
        "errors.minimum-age",
        new Object[]{18},
        locale);
~~~

The English result is `Age must be at least 18`. Placeholders `{0}`, `{1}` follow `java.text.MessageFormat`. Single quotes in MessageFormat have special escaping semantics; test translations containing apostrophes or reordered placeholders.

**Do not confuse** `MessageSource` `{0}` placeholders with Jakarta Bean Validation constraint template `{min}`; those are two different placeholder syntaxes interpolated at different stages.

## 5. Bean Validation Message Templates and MessageSource

### 5.1. Write Annotations with Keys, Do Not Hardcode Languages

Instead of:

~~~java
@NotBlank(message = "Name must not be blank")
String name
~~~

write:

~~~java
@NotBlank(message = "{registration.name.required}")
String name
~~~

When Bean Validation runs, key `registration.name.required` is looked up in the configured message source. Spring Boot integrates the application `MessageSource` to resolve `{...}` placeholders in constraint messages, then completes interpolation via the Bean Validation provider.

**Note:** when using plain Jakarta Bean Validation outside Spring Boot or manually building a `ValidatorFactory`, the Bean Validation spec defaults to `ValidationMessages.properties`. Spring Boot bridges to the application `MessageSource`; in non-Boot setups, configure `LocalValidatorFactoryBean` or a matching message interpolator rather than assuming `messages.properties` works automatically.

### 5.2. Distinguishing Interpolation and Binding Error Codes

For `@NotBlank` on field `name` of `RegistrationRequest`, a `FieldError` can carry codes in descending order of specificity:

~~~text
NotBlank.registrationRequest.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
~~~

These codes are generated by `DefaultMessageCodesResolver` by convention; actual object names and field types should be verified in your binding context. The framework tries more specific codes first and falls back to general ones.

There are two ways to resolve messages:

- **Bean Validation message template**: `@NotBlank(message="{registration.name.required}")`; the provider builds an interpolated default message for the constraint.
- **FieldError resolution**: `messageSource.getMessage(fieldError, locale)`; Spring tries field-specific codes first, then falls back to `FieldError.defaultMessage` when no code override exists in the bundle.

In a single project, both can coexist. If a bundle defines `NotBlank.registrationRequest.name`, it can take precedence over the annotation's default message when calling `getMessage(fieldError, locale)`. **Do not casually define two conflicting messages for the same field and expect the annotation to always win.**

`FieldError.getDefaultMessage()` normally holds the text already interpolated by Bean Validation in the request locale, whereas calling `MessageSource.getMessage(fieldError,locale)` lets the framework resolve by error codes. For manual `BindingResult.rejectValue`, the code-resolution mechanism is especially helpful because a default message alone may be insufficient.

### 5.3. Common Annotations

| Constraint | Meaning | Scenario |
|---|---|---|
| `@NotBlank` | Non-null string with at least one non-whitespace character | Display name |
| `@NotNull` | Non-null value | Non-string values or required fields |
| `@Size(min,max)` | String/collection/map/array size | Name 3–40 characters long |
| `@Email` | Email syntax check per validator | Email; **does not** verify address actually exists |
| `@Min(18)` | Numeric value at least 18 | Minimum age |
| `@Pattern(regexp=...)` | String matches regular expression | Product code, formatted identifier |
| `@Valid` | Triggers cascaded validation on eligible objects | Body DTO containing a nested DTO |

Some constraints like `@Email` permit `null` or empty strings per Jakarta Bean Validation; if email is **required**, add `@NotBlank` with its own message key. Do not assume `@Email` implies requiredness.

## 6. Error Branches to Distinguish in Spring MVC

| Source / Stage | Typical Exception | Typical Default HTTP | Localization Approach |
|---|---|---|---|
| `@Valid @RequestBody DTO` fails constraint | `MethodArgumentNotValidException` | 400 | FieldError/ObjectError via MessageSource |
| `@Valid @ModelAttribute` binding/validation error without adjacent BindingResult | `MethodArgumentNotValidException` in many cases | 400 | Error codes from binder/validator |
| Direct constraint on `@RequestParam`, `@PathVariable`, method arguments | `HandlerMethodValidationException` in modern MVC | 400 for input validation | ParameterValidationResult + MessageSource |
| Query/path cannot convert to target type (`abc` -> `int`) | `MethodArgumentTypeMismatchException` | 400 | Safe generic error code and message |
| Required parameter not sent | `MissingServletRequestParameterException` | 400 | missing-parameter key |
| Malformed JSON syntax/structure or undeserializable | `HttpMessageNotReadableException` | 400 | unreadable-body key |
| Unsupported `Content-Type` | `HttpMediaTypeNotSupportedException` | 415 | unsupported-media-type key |
| `Accept` does not match producible response | `HttpMediaTypeNotAcceptableException` | 406 | not-acceptable key |
| Business rule such as email already taken | Application-defined business exception | Per contract, e.g., 409 | Dedicated business error key |

**Do not catch `Exception.class` and return 400 for everything.** It masks server errors, database issues, programming bugs, and authentication/authorization failures. Nor assume catching only `MethodArgumentNotValidException` covers all Spring MVC validation, because **method validation** has its own branch.

### 6.1. BindingResult Position

With method:

~~~java
@PostMapping("/forms")
String submit(@Valid @ModelAttribute FormData form,
              BindingResult result) {
    if (result.hasErrors()) {
        return "form";
    }
    return "success";
}
~~~

This is an illustrative method only, requiring `FormData` and imports. `BindingResult` must sit **immediately after** the parameter it corresponds to so Spring passes errors for local handling. When `BindingResult` is present, eligible errors do not throw the default exception and are instead exposed via `result.getFieldErrors()`.

In REST APIs, centralized `@RestControllerAdvice` is usually preferred over repeating handling in every controller. Choose one consistent approach: if you declare `BindingResult` to build responses locally, do not expect a global exception handler to fire for errors you captured yourself.

### 6.2. Method Validation Differs from Single-DTO Validation

In Spring Framework 6.1+, when constraints sit directly on parameters or return types, MVC uses method validation and can throw `HandlerMethodValidationException`. Results contain `ParameterValidationResult` per method parameter, rather than just a single DTO's `BindingResult`.

If class-level `@Validated` is placed on the controller, AOP proxy validation may alter the handling path. Spring Framework documentation recommends omitting class-level `@Validated` on controllers when leveraging built-in MVC method validation.

To handle this branch, use `HandlerMethodValidationException`'s visitor or iterate `getAllValidationResults()`; error results implement `MessageSourceResolvable`. Do not copy a `MethodArgumentNotValidException` handler and try casting it to the method-validation exception.

## 7. Runnable Example: Spring Boot 3.5.16 + Java 17+ + Maven

The example comprises a simple registration API with constraints:

- `name` must not be blank.
- `email` must have valid email syntax.
- `age` must be at least 18.

Each constraint uses a translation key. The advice produces a fixed error response schema whose messages vary by `Accept-Language`. The project has no database and implements no authentication; its purpose is demonstrating the validation error pipeline.

### 7.1. Project Structure

~~~text
validation-i18n-demo/
  pom.xml
  src/
    main/
      java/com/example/validationi18n/
        ValidationI18nApplication.java
        RegistrationRequest.java
        RegistrationController.java
        ValidationErrorAdvice.java
      resources/
        application.properties
        messages.properties
        messages_vi.properties
    test/
      java/com/example/validationi18n/
        RegistrationMvcTest.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>validation-i18n-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
~~~

`spring-boot-starter-validation` must be present so Hibernate Validator evaluates Jakarta Bean Validation constraints. Do not assume `spring-boot-starter-web` alone always includes a validation provider across all Boot versions.

### 7.3. Configuring Message Source and Locale

File `src/main/resources/application.properties`:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false

spring.web.locale=en
spring.web.locale-resolver=accept-header
~~~

You do not need to manually declare `MessageSource` or `LocalValidatorFactoryBean` in this project because Boot auto-configures them when resource bundles and a validation provider are detected. Manually redefining both beans without understanding auto-configuration conditions can break message interpolation integration.

### 7.4. messages.properties — English Default

File `src/main/resources/messages.properties`:

~~~properties
validation.failed=Request data is invalid
registration.name.required=Name must not be blank
registration.email.invalid=Email address is invalid
registration.age.min=Age must be at least 18
error.body.unreadable=Request body cannot be read
error.parameter.invalid=Request parameter has an invalid format
~~~

The default file acts as fallback; no separate English translation file is needed if all English messages live here. If a product needs distinct US and UK English variants, add `messages_en_US.properties`/`messages_en_GB.properties` by convention.

### 7.5. messages_vi.properties — Vietnamese

File `src/main/resources/messages_vi.properties`, saved as UTF-8:

~~~properties
validation.failed=Dữ liệu yêu cầu không hợp lệ
registration.name.required=Tên không được để trống
registration.email.invalid=Địa chỉ email không hợp lệ
registration.age.min=Tuổi phải từ 18 trở lên
error.body.unreadable=Không đọc được nội dung yêu cầu
error.parameter.invalid=Tham số yêu cầu có định dạng không hợp lệ
~~~

**Rule:** keep the exact same keys across both bundles, changing only the values. A CI tool can check for missing keys, duplicate keys, `{0}` placeholders, or broken encoding.

### 7.6. Spring Boot Entry Point

File `src/main/java/com/example/validationi18n/ValidationI18nApplication.java`:

~~~java
package com.example.validationi18n;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationI18nApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationI18nApplication.class, args);
    }
}
~~~

### 7.7. Request DTO with Bean Validation

File `src/main/java/com/example/validationi18n/RegistrationRequest.java`:

~~~java
package com.example.validationi18n;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record RegistrationRequest(
        @NotBlank(message = "{registration.name.required}")
        String name,

        @Email(message = "{registration.email.invalid}")
        String email,

        @Min(value = 18, message = "{registration.age.min}")
        int age) {
}
~~~

Records are a clean choice in Java 17 and work well with Jackson in Spring Boot 3.5. Constraints sit as annotations on record components; Bean Validation reads this metadata during checks.

In this example, `email` is **optional**: `@Email` primarily validates format for eligible values and does not reject null/empty. In a real API requiring email, add `@NotBlank(message="{registration.email.required}")` and the matching key in all bundles.

Using `int age` means if JSON omits `age`, mapping can default to 0 and `@Min(18)` catches the error; if you need to distinguish “missing” from “under 18”, use `Integer age` with `@NotNull` and `@Min`.

### 7.8. Controller

File `src/main/java/com/example/validationi18n/RegistrationController.java`:

~~~java
package com.example.validationi18n;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {

    public record RegistrationResponse(String name, String email, int age) {
    }

    @PostMapping(
            value = "/api/registrations",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public RegistrationResponse create(
            @Valid @RequestBody RegistrationRequest request) {
        return new RegistrationResponse(
                request.name(), request.email(), request.age());
    }

    @GetMapping("/api/registrations/{id}")
    public String getById(@PathVariable("id") long id) {
        return "id=" + id;
    }
}
~~~

In `create`, JSON is decoded first and the validator checks the DTO afterward. On errors without an adjacent `BindingResult`, Spring MVC normally throws `MethodArgumentNotValidException`. `getById` demonstrates a path conversion error from `"abc"` to `long`, which is a separate branch from DTO validation.

The project stores no real users, hashes no passwords, and performs no real-world email confirmation. The success response merely proves the controller ran after validation passed.

### 7.9. @RestControllerAdvice: One Error Schema, Multiple Translations

File `src/main/java/com/example/validationi18n/ValidationErrorAdvice.java`:

~~~java
package com.example.validationi18n;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class ValidationErrorAdvice {
    private final MessageSource messages;

    public ValidationErrorAdvice(MessageSource messages) {
        this.messages = messages;
    }

    public record FieldIssue(String field, String message) {
    }

    public record ApiError(
            String code,
            String message,
            List<FieldIssue> errors) {
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> validation(
            MethodArgumentNotValidException ex,
            Locale locale) {

        List<FieldIssue> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        messages.getMessage(error, locale)))
                .sorted(Comparator.comparing(FieldIssue::field))
                .toList();

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "VALIDATION_ERROR",
                        text("validation.failed", locale),
                        fields));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException ex,
            Locale locale) {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_BODY",
                        text("error.body.unreadable", locale),
                        List.of()));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> typeMismatch(
            MethodArgumentTypeMismatchException ex,
            Locale locale) {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_PARAMETER",
                        text("error.parameter.invalid", locale),
                        List.of(new FieldIssue(
                                ex.getName(),
                                text("error.parameter.invalid", locale)))));
    }

    private String text(String key, Locale locale) {
        return messages.getMessage(key, null, locale);
    }
}
~~~

**Careful explanation:**

1. `MessageSource` is injected, not instantiated via `new ResourceBundleMessageSource` per request.
2. `Locale locale` is a valid `@ExceptionHandler` parameter in Spring MVC, resolved by the request's locale resolver.
3. `messages.getMessage(error, locale)` accepts `FieldError` as a `MessageSourceResolvable`; it can resolve field-specific error codes or fall back to the default message already interpolated by Bean Validation.
4. Sorting by field name makes test responses more deterministic. If a field violates multiple constraints simultaneously, order among errors on the same field still depends on validator execution; contracts should avoid relying on that ordering.
5. `List<FieldIssue>` emits only field names and safe translations. It never sends `getRejectedValue()`, raw JSON bodies, Java exception causes, or stack traces.
6. For unreadable bodies, it returns `INVALID_BODY` and a generic message; never pretend it is an `@NotBlank` failure.
7. For invalid path/query types, it returns `INVALID_PARAMETER` without constraint codes and without echoing input values that might be sensitive.
8. This handler **does not yet cover every MVC exception**: `MissingServletRequestParameterException`, `HandlerMethodValidationException`, 415, business errors, and fieldless ObjectErrors need dedicated policies in production apps.
9. To also return global validation errors (class-level constraints), inspect `ex.getBindingResult().getGlobalErrors()`; the code above focuses on DTO field errors for demonstration.

`@RestControllerAdvice` works well for uniform JSON across controllers. Do not both `extends ResponseEntityExceptionHandler` and declare `@ExceptionHandler` for exceptions already routed by the superclass: that can create ambiguous exception mappings. When extending the superclass, **override the corresponding protected handler method** rather than registering two handlers with overlapping responsibility.

### 7.10. Running with Maven

Requires JDK 17+ and Maven. In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

If the project has Maven Wrapper, use `./mvnw spring-boot:run`; on Windows use `mvnw.cmd spring-boot:run`.

By default the server listens on port 8080 if unconfigured and available.

**Valid request:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":"Mai","email":"mai@example.test","age":21}'
~~~

Expect HTTP 200, JSON body equivalent to:

~~~json
{"name":"Mai","email":"mai@example.test","age":21}
~~~

**Blank name, selecting Vietnamese:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":"","email":"mai@example.test","age":21}'
~~~

Expect HTTP 400; logical JSON body:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu yêu cầu không hợp lệ",
  "errors": [
    {
      "field": "name",
      "message": "Tên không được để trống"
    }
  ]
}
~~~

**Same error, selecting English:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: en" \
  -d '{"name":"","email":"mai@example.test","age":21}'
~~~

Expect HTTP 400; messages switch to:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Request data is invalid",
  "errors": [
    {
      "field": "name",
      "message": "Name must not be blank"
    }
  ]
}
~~~

Whitespace/property ordering is a serializer detail, not a contract. `code` and `field` remain **unchanged** across both languages.

**Malformed email address:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":"Mai","email":"not-an-email","age":21}'
~~~

Expect `VALIDATION_ERROR`, field `email`, message “Địa chỉ email không hợp lệ”.

**Underage:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":"Mai","email":"mai@example.test","age":16}'
~~~

Expect `VALIDATION_ERROR`, field `age`, message “Tuổi phải từ 18 trở lên”.

**Unreadable JSON:**

~~~bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":"Mai","age":'
~~~

Expect `INVALID_BODY` with message “Không đọc được nội dung yêu cầu”, not `VALIDATION_ERROR`: there is no valid DTO to validate.

**Unconvertible path variable:**

~~~bash
curl -i -H "Accept-Language: vi" \
  http://localhost:8080/api/registrations/abc
~~~

Expect `INVALID_PARAMETER` and message “Tham số yêu cầu có định dạng không hợp lệ”.

With `curl -i`, real output includes HTTP status line, headers, and body. The JSON blocks above illustrate only the **logical body**, not raw full stdout. When comparing JSON responses, use JSONPath rather than byte-for-byte comparison that depends on property order.

## 8. MockMvc: Testing Localization and the Error Contract

Use `@SpringBootTest` + `@AutoConfigureMockMvc` (Boot 3.5) to exercise the MVC pipeline, validator, messages, and advice. File `src/test/java/com/example/validationi18n/RegistrationMvcTest.java`:

~~~java
package com.example.validationi18n;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationMvcTest {
    @Autowired
    MockMvc mvc;

    @Test
    void nameErrorIsVietnameseWithViLanguageHeader() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                        .content("""
                                {"name":"","email":"mai@example.test","age":21}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message")
                        .value("Dữ liệu yêu cầu không hợp lệ"))
                .andExpect(jsonPath("$.errors[0].field").value("name"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tên không được để trống"));
    }

    @Test
    void sameErrorIsEnglishWithEnHeader() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                        .content("""
                                {"name":"","email":"mai@example.test","age":21}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message")
                        .value("Request data is invalid"))
                .andExpect(jsonPath("$.errors[0].field").value("name"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Name must not be blank"));
    }

    @Test
    void invalidEmailIsLocalizedInVietnamese() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                        .content("""
                                {"name":"Mai","email":"not-an-email","age":21}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field").value("email"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Địa chỉ email không hợp lệ"));
    }

    @Test
    void minimumAgeUsesLocalizedMessage() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                        .content("""
                                {"name":"Mai","email":"mai@example.test","age":16}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field").value("age"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tuổi phải từ 18 trở lên"));
    }

    @Test
    void malformedJsonHasSeparateCodeAndLocalizedMessage() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_BODY"))
                .andExpect(jsonPath("$.message")
                        .value("Không đọc được nội dung yêu cầu"));
    }

    @Test
    void invalidPathVariableHasSeparateErrorCode() throws Exception {
        mvc.perform(get("/api/registrations/abc")
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"))
                .andExpect(jsonPath("$.errors[0].field").value("id"))
                .andExpect(jsonPath("$.message")
                        .value("Tham số yêu cầu có định dạng không hợp lệ"));
    }

    @Test
    void validRequestPassesValidation() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"Mai","email":"mai@example.test","age":21}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Mai"))
                .andExpect(jsonPath("$.age").value(21));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

In the example, each validation test triggers only **one constraint** failure so `errors[0]` is predictable. When a single request has multiple errors, assert by field/code instead of relying on order. The tests verify the schema keys, HTTP statuses, Vietnamese/English translations, and separation of JSON/parsing from validation.

`MockMvc` does not open a TCP port. For integration tests over the network, use `@SpringBootTest(webEnvironment=RANDOM_PORT)` and a real HTTP client, especially when verifying reverse proxies, TLS, caching, and HTTP headers in production-like deployments.

## 9. Localization with MessageFormat, FieldError, and Complex Cases

### 9.1. Distinguishing Field and Object-Level Errors

`FieldError` carries a field name such as `name` or `age`; `ObjectError` can describe an object-level constraint such as “end date must be after start date”. If only `getFieldErrors()` is read as in the demo, global errors are omitted from the response.

For production, you can standardize:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu yêu cầu không hợp lệ",
  "errors": [
    {
      "field": "startDate",
      "message": "Ngày bắt đầu không hợp lệ"
    },
    {
      "field": null,
      "message": "Ngày kết thúc phải sau ngày bắt đầu"
    }
  ]
}
~~~

This is a **contract example**, not output from the section 7 project (as that project lacks startDate/endDate). When adding a class-level custom validator, read `getGlobalErrors()` and resolve via `MessageSource.getMessage(ObjectError,locale)`, limiting exposed values.

### 9.2. DefaultMessageCodesResolver and Field-Specific Messages

Keys such as `Size.registrationRequest.name`, `Size.name`, `Size.java.lang.String`, and `Size` represent priority levels Spring can generate. To prevent translating a generic constraint into the wrong message on specific fields, use specific keys where needed:

~~~properties
NotBlank.registrationRequest.name=Please enter a name
NotBlank.name=This name is required
NotBlank=This field is required
~~~

When `MessageSource.getMessage(FieldError,locale)` is called, the more specific key takes priority. However, the demo project uses `@NotBlank(message="{registration.name.required}")` and avoids declaring `NotBlank...` to keep a single source of truth.

### 9.3. MessageFormat Placeholders and Escaping

Example key with arguments:

~~~properties
validation.size=Please enter between {0} and {1} characters
~~~

Code:

~~~java
messages.getMessage(
        "validation.size", new Object[]{3, 40}, locale);
~~~

substitutes arguments in order, and a Vietnamese translation can reorder placeholders if natural phrasing requires it. When messages include apostrophes, Java `MessageFormat` treats single quotes as quoting control characters; test messages containing apostrophes, braces, or date/number formats thoroughly.

In `@Size(min=3,max=40)`, `{min}`/`{max}` are Bean Validation attribute interpolation tokens. Do not arbitrarily replace them with `{0}` if relying on the Bean Validation message interpolator, or mix incompatible placeholder styles.

### 9.4. Localizing Business Errors

Business errors do not necessarily come from `BindingResult`. For instance, a service detecting an already-registered email can throw a business exception with a **stable code** `EMAIL_ALREADY_REGISTERED`; the advice translates the message using key `business.email.duplicate`.

Never expose raw `Exception.getMessage()` to the API: it may be untranslatable, or contain emails/SQL/class names or sensitive data. Emit only error codes and public catalog messages while logging internally with a request correlation ID.

## 10. Problem Details and ResponseEntityExceptionHandler

Spring Framework supports RFC 9457 `ProblemDetail` with fields `type`, `title`, `status`, `detail`, `instance`, and custom properties. If an application prefers standard problem responses instead of a custom `ApiError` record, configure in Spring Boot 3.5:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

When enabled, Spring Boot can provide `ResponseEntityExceptionHandler` to handle many built-in MVC errors and consult `MessageSource` for titles/details. However, a custom `@RestControllerAdvice` can still override response behavior depending on scope/precedence; choose **one clear error strategy**.

Illustrative method snippet:

~~~java
ProblemDetail detail = ProblemDetail.forStatus(
        HttpStatus.BAD_REQUEST);
detail.setTitle(messages.getMessage(
        "validation.failed", null, locale));
detail.setProperty("code", "VALIDATION_ERROR");
return detail;
~~~

This snippet requires imports/variables for messages and locale and is not a standalone class. Spring can serialize `ProblemDetail` as `application/problem+json` with an appropriate converter. When extending `ResponseEntityExceptionHandler`, override `handleMethodArgumentNotValid(...)` or related hooks rather than adding duplicate `@ExceptionHandler` mappings.

Spring MVC documentation describes message codes of the form `problemDetail.[fully-qualified-exception-class]`; `MethodArgumentNotValidException` and `HandlerMethodValidationException` also carry message arguments implementing `MessageSourceResolvable`. Consequently, many messages can be localized without writing custom exception handlers per type.

## 11. Common Errors and Diagnostics

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Response literally shows `{registration.name.required}` | Missing key/bundle/validator integration | Check messages.properties, key spelling, classpath, Spring validator |
| `messages_vi.properties` exists yet always returns English | Missing default messages.properties; locale not resolved to vi | Check Spring Boot i18n auto-config and `Accept-Language` |
| Vietnamese diacritics corrupted | File encoding not UTF-8, build alters encoding | `spring.messages.encoding`, file encoding, response charset |
| Messages change between dev and prod machines | Falling back to JVM/system locale | Set `fallback-to-system-locale=false`, check default bundle |
| Sent `Accept-Language: vi` yet language stays unchanged | Custom `LocaleResolver` or `spring.web.locale-resolver=fixed` | Check active resolver and request headers |
| Constraints never run | Missing validation provider, `@Valid`, or binding bypassed | Validation starter, `@Valid`, type annotations, and logs |
| `@Email` accepts empty string | Email syntax constraint does not imply requiredness | Add `@NotBlank` with its own key |
| `@Valid` fails yet handler does not run | Controller has adjacent `BindingResult` or different method validation branch | Distinguish `MethodArgumentNotValidException` and `HandlerMethodValidationException` |
| Malformed JSON produces validation message | Advice too broad or wrong exception mapping | Handle `HttpMessageNotReadableException` separately |
| Path `abc` to `long` reports DTO validation key | Catching `Exception` broadly / code mismatch | Handle `MethodArgumentTypeMismatchException` separately |
| JSON sent with wrong Content-Type returns 400 | Error handler masks 415 | Preserve `HttpMediaTypeNotSupportedException` and right status |
| Default message shows raw `{0}` or broken apostrophe | Mixed MessageFormat/Bean Validation interpolation | Separate placeholder styles and escape properly |
| One field has multiple errors and tests flake | Relying on unguaranteed error ordering | Assert by field/code; explicitly sort public output |
| Global validation error missing | Reading only `getFieldErrors()` | Include `getGlobalErrors()` when class-level constraints exist |
| Translation works yet response leaks password/token | Outputting rejectedValue/cause/raw body in response | Restrict fields and use a safe message catalog |
| Ambiguous handlers for same exception class | Advice extends `ResponseEntityExceptionHandler` and adds duplicate handler | Override protected methods or pick one strategy |
| Spring Security exceptions are untranslated | Filter chain runs before DispatcherServlet | Configure security localization/handlers and LocaleContextHolder properly |
| Locale changes yet cache serves wrong language | Shared cache ignores Accept-Language | Apply `Vary: Accept-Language` or locale-keyed caches |

### 11.1. Safe Debugging

In test environments, log exception names and field codes without logging raw bodies or tokens. Verify step by step: incoming `Accept-Language` → resolved locale → key in `MessageSource` → Bean Validation execution → `BindingResult` codes/defaultMessage → advice output.

You can inject `MessageSource` in tests and call:

~~~java
String msg = messages.getMessage(
        "registration.name.required", null, Locale.forLanguageTag("vi"));
~~~

Expect “Tên không được để trống”. If this lookup works yet the HTTP response is wrong, the issue likely lies in the locale resolver, validator/interpolator, or exception handling, rather than a missing key.

For shared-cached HTTP responses whose content varies by `Accept-Language`, enforce a safe caching policy such as `Vary: Accept-Language` where applicable; responses carrying personal information should generally avoid shared caching.

## 12. Security and Product Boundaries

1. **Never put rejectedValue into error JSON.** Emails, passwords, API keys, tokens, and query values may be sensitive.
2. **Never return stack traces, binding targets, SQL, class names, or root exception causes** to clients. Internal logs must enforce access controls and redaction.
3. **Never branch authorization or automated client logic on prose text**; use `code`, `field`, HTTP status, and schema standardization.
4. **Never treat `Accept-Language` as identity or geography.** It is an untrusted client preference signal.
5. **Never catch all exceptions and return 400**; preserve 401/403/404/409/415/422/500 per API semantics and contracts.
6. **Localize semantics, not just words**: user messages should explain how to fix input without blaming or exposing internals.
7. **Keep translations synchronized**: CI checks for keys, placeholders, encoding, fallback languages, and mobile/web client versions.
8. **Avoid hardcoding Vietnamese prose inside validation annotations** if the API serves multiple languages; use keys and bundles.
9. **Avoid over-relying on default exception messages**: Hibernate Validator/Jackson wording changes across versions and is not a public API contract.
10. **Review when upgrading to Boot 4.x**: APIs/packages, webmvc/validation/test starters, Jackson 3, Problem Details/error auto-configuration, and locale resolver configuration may change; make locale and response contract tests part of regression suites.

## 13. Production Readiness Checklist

- [ ] Default `messages.properties` and all supported locale bundles packaged in the JAR.
- [ ] `spring.messages.encoding=UTF-8` and OS-independent fallback configured.
- [ ] `Accept-Language` or a product-defined locale resolution strategy in place.
- [ ] Validation annotations use message keys, not hardcoded languages.
- [ ] `spring-boot-starter-validation` included and provider initialization tested.
- [ ] Stable response contract (`code`, `message`, `errors[]`) or standardized ProblemDetail.
- [ ] Distinguishes `MethodArgumentNotValidException`, `HandlerMethodValidationException`, binding/conversion errors, unreadable bodies, and 415.
- [ ] FieldError and ObjectError rendered per policy without leaking raw rejected values.
- [ ] Tests cover at least English and Vietnamese for the same error, plus missing headers and unsupported locales.
- [ ] Tests cover distinct constraints, malformed JSON, wrong path/query types, and valid payloads.
- [ ] Tests cover keys with `MessageFormat` arguments, apostrophes, and Unicode.
- [ ] Security/authorization errors verified separately and never turned into validation 400s.
- [ ] Proper caching policy when responses vary by locale.
- [ ] Message catalogs and error schemas verified during Spring Boot/Framework upgrades.

**Conclusion:** to properly localize validation errors in Spring Boot, separate **constraints** (`@Valid`/Jakarta Bean Validation), **translation sources** (`MessageSource`), **request locale** (`LocaleResolver`), and **response contract** (`@RestControllerAdvice` or Problem Details). Stable codes, locale-resolved messages, and Vietnamese/English tests keep APIs both user-friendly and consistent.

## Official References

- Spring Boot 3.5 — Internationalization, Bundles, and `spring.messages.*` Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html
- Spring Boot 3.5 — Validation and MessageSource Interpolation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 — Common Application Properties (`spring.web.locale`, `spring.messages.*`): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework — MVC Validation, MethodArgumentNotValidException, and HandlerMethodValidationException: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Controller Method Exception Handling: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — MVC Error Responses / Problem Details: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework — MVC LocaleResolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html
- Spring Framework — Validation Error Code Resolution: https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html
- Spring Framework — Bean Validation and Customizing Validation Errors: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — MessageSource API/Concepts: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
