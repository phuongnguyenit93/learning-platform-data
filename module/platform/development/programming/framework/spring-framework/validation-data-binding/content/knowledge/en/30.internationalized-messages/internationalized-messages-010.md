# Missing Translations and Default Values in Spring Framework

## 1. Real-World Problem: User Selects Vietnamese, Yet Not Every Key Has a Translation

A Spring MVC system serves both Vietnamese and English. Its signup validation API takes a name and age:

```http
POST /api/signup
Content-Type: application/json
Accept-Language: vi

{"name":" ","age":16}
```

The rules are language-independent: `name` must contain text, `age` must be at least 18. Yet when returning errors, the application can encounter one of three situations:

1. **Vietnamese translation exists:** `NotBlank.signupInput.name` → “Tên không được bỏ trống”.
2. **Vietnamese translation is missing, but a message exists in the base bundle:** `Min.signupInput.age` → “Age must be at least 18”.
3. **Key does not exist in any resource bundle:** `ui.notProvided` → uses a developer-supplied default string, or throws `NoSuchMessageException` if an overload without a default is called.

Distinguish **missing translation** from **missing message**. A key might be absent from `messages_vi.properties` yet still be found in `messages.properties`, another code in `FieldError#getCodes()`, or a parent `MessageSource`.

This lesson explains fallback mechanisms, how to pick default values, the traps of `useCodeAsDefaultMessage`, and how to write APIs and tests so **missing i18n content never turns into an unintended server error**.

**Scope:** Spring Framework 6.1–6.2, Spring Boot 3.x, Jakarta Validation 3.x, Servlet Spring MVC, Java 17+. The hands-on example uses Spring Boot 3.3.6. Spring WebFlux classes (such as `WebExchangeBindException`) differ from the MVC classes presented here.

## 2. Three Distinct Fallback Layers

| Layer | Source | Example | Remember |
| --- | --- | --- | --- |
| **Locale fallback** | `LocaleResolver` | Unsupported header `fr` → picks `en` | Occurs before or while resolving the request's language |
| **Resource bundle / error-code fallback** | `MessageSource` | Key missing in `messages_vi.properties` → found in `messages.properties`; `FieldError` tries multiple codes | Determines only which text is retrieved |
| **Explicit `defaultMessage`** | `getMessage` call | Cannot find `ui.unknown` → “Information unavailable” | Supplied by the application at the message lookup site |

Another issue is **defective translation content**: the key exists, yet its value is empty, missing placeholders, or misspelled. Technically the lookup succeeds, though the UX is broken. Do not confuse this with a missing key.

### 2.1. Contrast Example

Suppose:

```properties
# messages.properties (base English)
ui.hello=Hello, {0}!
ui.baseOnly=This text is available only in the base bundle
```

```properties
# messages_vi.properties
ui.hello=Xin chào, {0}!
# ui.baseOnly intentionally omitted
```

With locale `vi`:

- `getMessage("ui.hello", ...)` → “Xin chào, Lan!”.
- `getMessage("ui.baseOnly", ...)` → “This text is available only in the base bundle”.
- `getMessage("ui.notProvided", ...)` → uses explicit default or may throw `NoSuchMessageException`, because the key is absent from both base and `vi`.

Testing with locale `fr` when `LocaleResolver` only supports `vi`/`en` is a **different** test: the resolver may pick the default English locale. Do not conclude “the key lacks a French translation” merely because the response shows English.

## 3. MessageSource and the Three Most Important Overloads

Spring uses the interface:

```java
org.springframework.context.MessageSource
```

### 3.1. With `defaultMessage`: Soft Fallback

```java
String text = messageSource.getMessage(
        "ui.notProvided",
        null,
        "Information is currently unavailable",
        locale
);
```

For a nonexistent code, the method uses `defaultMessage`. If the default contains placeholders and arguments are passed, Spring can render it via `MessageFormat`:

```java
String text = messageSource.getMessage(
        "ui.greeting.notProvided",
        new Object[]{"Lan"},
        "Hello, {0}!",
        Locale.ENGLISH
);
```

Illustrative output:

```text
Hello, Lan!
```

**Nullable note:** the four-argument overload allows passing `null` as the default; when no message is found, the return value can be `null`:

```java
String optional = messageSource.getMessage(
        "ui.notProvided",
        null,
        (String) null,
        locale
);
```

Do not pass `optional` to `Map.of("message", optional)` unless you have ensured it is non-null: `Map.of` rejects null values. If the API always needs a `message`, supply a non-null default such as a vetted generic message.

### 3.2. Without `defaultMessage`: Strict Lookup

```java
String text = messageSource.getMessage(
        "ui.notProvided",
        null,
        locale
);
```

If the code cannot be resolved and no special config applies, Spring throws:

```java
org.springframework.context.NoSuchMessageException
```

The strict approach is valuable in **tests/CI or startup checks**: a missing critical key is caught immediately. However, using it unconditionally inside an `@ExceptionHandler` handling HTTP 400 input errors can cause a missing translation to throw a second exception, turning the client's 400 into a 500.

The goal is not “never let the app throw `NoSuchMessageException`”; the goal is **using it in the right place**:

- CI: detect missing keys and require completion before deployment.
- Production error responses: safe fallback and metrics.
- Mandatory configuration keys: strict lookup makes sense when a missing key should fail startup.

### 3.3. `MessageSourceResolvable`: Multiple Codes and Built-In Default

```java
String translated = messageSource.getMessage(
        fieldError,
        locale
);
```

`FieldError` and `ObjectError` implement `MessageSourceResolvable`. A single error can carry multiple codes ordered by specificity, such as:

```text
NotBlank.signupInput.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
```

`getMessage(error,locale)` tries that list and can use `error.getDefaultMessage()` if no code matches. If none of the codes resolve **and the resolvable has no default**, `NoSuchMessageException` can still occur.

**Do not equate this overload with `getMessage(error.getCode(),...)`.** Passing a single code discards Spring's field-specific codes, default message, and arguments.

## 4. “Defaults” with Similar Names but Different Meanings

| Config / Value | Role |
| --- | --- |
| `resolver.setDefaultLocale(Locale.ENGLISH)` | Locale fallback when no requested language matches |
| `messages.properties` | Base bundle, supplies messages when a locale-specific bundle lacks them |
| `getMessage(code,args,"Safe text",locale)` | Explicit default if the code cannot be found |
| `FieldError#getDefaultMessage()` | Default message attached to a validation/binding error |
| `AbstractMessageSource#setUseCodeAsDefaultMessage(true)` | Debug fallback returning **the code itself** when no message is found |
| `@RequestParam(defaultValue="guest")` | Default value for a **request parameter**, not i18n |
| `ValidationMessages.properties` | Default bundle for Jakarta Validation message interpolation, distinct from Spring `messages` |

The following example highlights the difference:

```java
@GetMapping("/welcome")
public String welcome(
        @RequestParam(defaultValue = "visitor") String name,
        Locale locale) {

    return messageSource.getMessage(
            "ui.welcome",
            new Object[]{name},
            "Welcome, {0}!",
            locale
    );
}
```

`"visitor"` is the default for the **HTTP input**, whereas `"Welcome, {0}!"` is the default for the **message lookup**. Both can appear in the same method while remaining completely independent.

## 5. Bundle Lookup, System-Locale Fallback, and Base Bundle

In Spring Boot, you typically create:

```text
src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
  messages_en.properties      # only if overriding base English
  messages_vi_VN.properties   # when regional variants exist
```

Configuration:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Meaning:

- `spring.messages.basename`: sets the basename; multiple bases like `messages,i18n/errors` can be declared.
- `spring.messages.encoding=UTF-8`: reads Vietnamese diacritics properly.
- `spring.messages.fallback-to-system-locale=false`: when a locale-specific resource is not found, **do not try the OS locale**. This keeps results consistent across dev, CI, and production machines.
- Disabling system-locale fallback **does not disable** base fallback from `messages_vi.properties` to `messages.properties`.

**Important:** Spring Boot auto-configures `MessageSource` when it finds the declared base bundle. If you create only `messages_vi.properties` without `messages.properties`, auto-configuration may not activate as intended. Always verify the base file exists.

### 5.1. An Empty String Is Not a Missing Key

```properties
ui.banner=
```

The key `ui.banner` exists with an empty value. Lookup can treat that as a valid message and return an empty string, **without falling back** to the explicit default. Therefore, missing-translation checks should cover:

- Absent keys.
- Keys with empty or whitespace-only values.
- Templates missing `{0}`, `{1}`, or having broken escaping.
- Translations containing text in the wrong product language.
- Content containing private data or unescaped HTML.

### 5.2. Locale Tags with a Region

`vi` and `vi-VN` are two distinct `Locale`s. When an app supports `vi`, do not assume every `vi-VN` header is handled identically without testing `AcceptHeaderLocaleResolver`'s matching rules. The same applies to `en-US` and `en`.

If users should switch languages via `?lang=vi`, `LocaleChangeInterceptor` requires a `LocaleResolver` that supports `setLocale` (such as `CookieLocaleResolver` or `SessionLocaleResolver`). `AcceptHeaderLocaleResolver` does not allow the server to rewrite the request header that way.

## 6. `useCodeAsDefaultMessage`: A Trap When Handling Errors

`AbstractMessageSource` provides the setter:

```java
messageSource.setUseCodeAsDefaultMessage(true);
```

This snippet assumes `messageSource` has type `AbstractMessageSource`/subclass, not the `MessageSource` interface.

When enabled, an unresolved code can become the returned text itself:

```text
validation.user.internalOwnerId.invalid
```

This is convenient for **debugging**, yet must not be the fallback for end users. Raw codes are confusing and can leak internal field/class structure.

### 6.1. A Parent `MessageSource` Can Defeat Fallback Codes

`AbstractMessageSource` Javadoc warns: when resolving a `MessageSourceResolvable` with **multiple codes** (such as `FieldError`) and a parent source has `useCodeAsDefaultMessage` enabled, the parent source may return **the first code** before the system gets a chance to find translations for fallback codes.

Example:

```text
NotBlank.signupInput.name
NotBlank.name
NotBlank
```

If `NotBlank.signupInput.name` does not exist while `NotBlank.name` has a translation, returning the code early from the parent can cause the client to see `NotBlank.signupInput.name` instead of the proper message. To avoid this:

1. Keep `useCodeAsDefaultMessage=false` in production.
2. Do not overuse parent message sources when a few resource bundles suffice.
3. Configure clear, meaningful codes.
4. Measure translation coverage directly from files in CI.
5. Test `FieldError`s with multiple error codes to detect altered fallback behavior.

If you need a generic message, use an **explicit `defaultMessage`** rather than turning raw keys into translations.

## 7. `BindingResult` and Missing Translations for Bean Validation Errors

### 7.1. `FieldError` Has Multiple Codes

Spring's `DefaultMessageCodesResolver` produces a code list ordered by specificity. For instance, `@NotBlank` on `SignupInput.name` may produce:

```text
NotBlank.signupInput.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
```

With a message in `messages.properties` and none in `vi`, `messages.getMessage(fieldError,Locale.forLanguageTag("vi"))` can still return base English.

`FieldError#getCode()` is suitable as an **error code** in JSON; `MessageSource#getMessage(fieldError,locale)` is suitable for computing **localized text**. Never force the frontend to compare literal Vietnamese/English strings to drive validation UI.

### 7.2. `ObjectError` and Class-Level Constraints

With a class-level custom constraint such as “end date must be after start date”, Spring can create an `ObjectError` not bound to any specific field. Thus, an API error adapter should use:

```java
bindingResult.getAllErrors()
```

instead of only `getFieldErrors()`. `ObjectError` is also a `MessageSourceResolvable`, so it looks up bundles the same way. If the schema requires `field`, you can represent global errors with an empty string or a separate `globalErrors` array.

### 7.3. Missing Translations Do Not Make Validation Pass

When `age=16` violates `@Min(18)`, the validation result is still **invalid**, even if `Min.signupInput.age` is missing from the `vi` file. The system must still return HTTP 400 and never alter business logic just because a message is missing.

### 7.4. Binding Errors Differ from Validation Errors

In an `@ModelAttribute` HTML form:

```text
age=abc
```

Spring can generate `typeMismatch.signupForm.age` when converting the string to `Integer` fails. This is not a `@Min` error. You can declare:

```properties
# messages.properties
typeMismatch.signupForm.age=Age must be a number
```

```properties
# messages_vi.properties
typeMismatch.signupForm.age=Tuổi phải là một số
```

In `@Valid @RequestBody` JSON, if Jackson cannot parse the JSON, the error is usually `HttpMessageNotReadableException`. Do not fabricate a `FieldError` and call it a constraint violation.

## 8. Jakarta Validation `MessageInterpolator` and Its Own Resource Bundle

Jakarta Validation has a separate mechanism: **`MessageInterpolator`** interpolates constraint templates.

```java
@NotBlank(message = "{signup.name.required}")
String name;

@Size(min = 4, max = 12, message = "{signup.code.size}")
String code;
```

Providers normally search templates in:

```text
ValidationMessages.properties
ValidationMessages_vi.properties
```

Example:

```properties
# ValidationMessages.properties
signup.name.required=Name is required
signup.code.size=Code length must be between {min} and {max}
```

```properties
# ValidationMessages_vi.properties
signup.name.required=Tên là bắt buộc
signup.code.size=Độ dài mã phải từ {min} đến {max}
```

`{min}` and `{max}` belong to Jakarta Validation constraint metadata. They are **different** from Spring `MessageFormat` placeholders `{0}`/`{1}`.

Key points:

- `messages.properties` serves Spring `MessageSource`.
- `ValidationMessages.properties` serves Jakarta Validation message interpolation.
- They are not automatically the same file.
- The provider may populate `FieldError`'s default message before the Spring adapter queries `MessageSource` using `FieldError#getCodes()`.
- If you need a single source, you can configure `LocalValidatorFactoryBean#setValidationMessageSource(...)` per Spring and compatible provider docs; do not assume it is portable across every provider. Never configure both `setValidationMessageSource` and `setMessageInterpolator` on the same validator bean per Spring guidelines.

In the hands-on example, we **use only Spring `messages` bundles to drive API responses**; we omit `ValidationMessages*.properties` so two overlapping systems do not obscure missing-translation behavior.

## 9. Hands-On Project: Spring Boot 3.3.6, Java 17

Goals:

- Look up a key with a `vi` translation.
- Look up a key present only in base English.
- Look up a completely nonexistent key with an explicit default.
- Test strict lookup throwing `NoSuchMessageException`.
- Test nullable default returning `null`.
- Return `@Valid` errors with translated name and age **intentionally missing `vi` translation** to demonstrate fallback.
- Handle malformed JSON separately from Bean Validation.
- Verify HTTP behavior with `MockMvc`.

### 9.1. Source Structure

```text
message-fallback-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/messagefallback/
        MessageFallbackApplication.java
        WebLocaleConfiguration.java
        SignupInput.java
        FieldIssue.java
        ApiError.java
        MessageController.java
        ApiErrorAdvice.java
      resources/
        application.properties
        messages.properties
        messages_vi.properties
    test/
      java/com/example/messagefallback/
        MessageFallbackTest.java
```

### 9.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'message-fallback-demo'
```

`build.gradle`:

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

`spring-boot-starter-web` provides Servlet Spring MVC and Jackson; `spring-boot-starter-validation` brings a Jakarta Validation provider aligned with the Spring Boot BOM. Putting `@Valid` on a DTO without a provider and proper validation boundary does not guarantee constraints are enforced.

### 9.3. Main Application

`src/main/java/com/example/messagefallback/MessageFallbackApplication.java`:

```java
package com.example.messagefallback;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessageFallbackApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessageFallbackApplication.class, args);
    }
}
```

### 9.4. Locale Resolver

`src/main/java/com/example/messagefallback/WebLocaleConfiguration.java`:

```java
package com.example.messagefallback;

import java.util.List;
import java.util.Locale;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.i18n.AcceptHeaderLocaleResolver;

@Configuration
public class WebLocaleConfiguration {

    @Bean
    public LocaleResolver localeResolver() {
        AcceptHeaderLocaleResolver resolver =
                new AcceptHeaderLocaleResolver();
        resolver.setSupportedLocales(List.of(
                Locale.ENGLISH,
                Locale.forLanguageTag("vi")
        ));
        resolver.setDefaultLocale(Locale.ENGLISH);
        return resolver;
    }
}
```

`Accept-Language: vi` picks Vietnamese; `en` picks English; `fr` is not in the supported list so it falls back to English. If your product uses `vi-VN` or `en-US`, configure and test matching language tags rather than assuming automatic equivalence.

### 9.5. Resource Bundle Configurations

`src/main/resources/application.properties`:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

`src/main/resources/messages.properties` (English base):

```properties
ui.hello=Hello, {0}!
ui.baseOnly=This text is available only in the base bundle
api.validation=Invalid input
api.invalidJson=Cannot read the request JSON

NotBlank.signupInput.name=Name must not be blank
NotBlank.name=Name must not be blank
Min.signupInput.age=Age must be at least 18
Min.age=Age must be at least 18
NotNull.signupInput.age=Age is required
NotNull.age=Age is required
```

`src/main/resources/messages_vi.properties`:

```properties
ui.hello=Xin chào, {0}!
api.validation=Dữ liệu không hợp lệ
api.invalidJson=Không thể đọc JSON của yêu cầu

NotBlank.signupInput.name=Tên không được bỏ trống
NotBlank.name=Tên không được bỏ trống

# Intentionally omit ui.baseOnly in the vi file
# Intentionally omit Min.signupInput.age and Min.age in the vi file
# Intentionally omit ui.notProvided in all files
```

This exercise demonstrates missing translations. In production, complete them:

```properties
Min.signupInput.age=Tuổi phải từ 18
Min.age=Tuổi phải từ 18
ui.baseOnly=Thông điệp đã có bản dịch tiếng Việt
```

If you add these keys, tests expecting **English fallback** must be updated to expect Vietnamese; that is an intentional change.

### 9.6. Input DTO

`src/main/java/com/example/messagefallback/SignupInput.java`:

```java
package com.example.messagefallback;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record SignupInput(
        @NotBlank String name,
        @NotNull @Min(18) Integer age
) {}
```

`@NotNull` is needed on `age` because `@Min` itself allows `null`. `@NotBlank` rejects empty or whitespace-only strings.

### 9.7. Error DTOs

`src/main/java/com/example/messagefallback/FieldIssue.java`:

```java
package com.example.messagefallback;

public record FieldIssue(
        String field,
        String code,
        String message
) {}
```

`src/main/java/com/example/messagefallback/ApiError.java`:

```java
package com.example.messagefallback;

import java.util.List;

public record ApiError(
        String code,
        String message,
        List<FieldIssue> fields
) {}
```

`code` is machine/client-readable; `message` is for display; `field` locates the error. Changing language must never alter `code` values or HTTP statuses.

### 9.8. Controller

`src/main/java/com/example/messagefallback/MessageController.java`:

```java
package com.example.messagefallback;

import jakarta.validation.Valid;
import java.util.Locale;
import java.util.Map;
import org.springframework.context.MessageSource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class MessageController {

    private final MessageSource messages;

    public MessageController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping("/messages/hello")
    public Map<String, String> hello(
            @RequestParam(defaultValue = "visitor") String name,
            Locale locale) {

        String text = messages.getMessage(
                "ui.hello",
                new Object[]{name},
                "Hello, {0}!",
                locale
        );
        return Map.of("message", text);
    }

    @GetMapping("/messages/base-only")
    public Map<String, String> baseOnly(Locale locale) {
        String text = messages.getMessage(
                "ui.baseOnly",
                null,
                "Information not available",
                locale
        );
        return Map.of("message", text);
    }

    @GetMapping("/messages/unknown")
    public Map<String, String> unknown(Locale locale) {
        String text = messages.getMessage(
                "ui.notProvided",
                null,
                "Information not available",
                locale
        );
        return Map.of("message", text);
    }

    @PostMapping(
        path = "/signup",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Map<String, Object>> signup(
            @Valid @RequestBody SignupInput input) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of(
                        "name", input.name(),
                        "age", input.age()
                ));
    }
}
```

Here, the three GET endpoints do not accept arbitrary message codes from clients; the application controls which keys can be displayed. A “look up any key” endpoint should not be exposed publicly because it can leak internal messages.

### 9.9. Exception Advice: Validation and Parser Errors

`src/main/java/com/example/messagefallback/ApiErrorAdvice.java`:

```java
package com.example.messagefallback;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import org.springframework.context.MessageSource;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {

    private final MessageSource messages;

    public ApiErrorAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException exception,
            Locale locale) {

        List<FieldIssue> fields = exception.getBindingResult()
                .getAllErrors()
                .stream()
                .map(error -> toIssue(error, locale))
                .sorted(Comparator
                        .comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .toList();

        String summary = messages.getMessage(
                "api.validation",
                null,
                "Invalid input",
                locale
        );

        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_ERROR", summary, fields));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException exception,
            Locale locale) {

        String summary = messages.getMessage(
                "api.invalidJson",
                null,
                "Cannot read the request JSON",
                locale
        );

        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_JSON", summary, List.of()));
    }

    private FieldIssue toIssue(ObjectError error, Locale locale) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        String code = Objects.toString(
                error.getCode(), "invalid"
        );

        // ObjectError/FieldError holds all codes and the default.
        String message = messages.getMessage(error, locale);
        return new FieldIssue(field, code, message);
    }
}
```

`getAllErrors()` retrieves both `FieldError` and `ObjectError` (class-level validation). `getMessage(error, locale)` leverages the error's code list, arguments, and default. `messages.getMessage("api.validation",..., "Invalid input",locale)` provides an explicit fallback if another application has not configured the summary key.

For safe error reporting, the adapter never reflects `FieldError#getRejectedValue()`, raw exception messages, or stack traces—those may contain personal data, tokens, SQL, or internal Java structures.

## 10. Sending Requests and Observing Fallbacks

Start the app after creating the Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows:

```powershell
.\gradlew.bat bootRun
```

### 10.1. Vietnamese Key Present

```bash
curl -i 'http://localhost:8080/api/messages/hello?name=Lan' \
  -H 'Accept-Language: vi'
```

HTTP 200:

```json
{"message":"Xin chào, Lan!"}
```

### 10.2. Missing in `vi`, Present in Base

```bash
curl -i 'http://localhost:8080/api/messages/base-only' \
  -H 'Accept-Language: vi'
```

HTTP 200:

```json
{"message":"This text is available only in the base bundle"}
```

### 10.3. Key Absent from All Bundles

```bash
curl -i 'http://localhost:8080/api/messages/unknown' \
  -H 'Accept-Language: vi'
```

HTTP 200:

```json
{"message":"Information not available"}
```

This is the **explicit default**, not “Spring automatically translated the missing key”.

### 10.4. Validation Error with Incomplete Vietnamese Translations

```bash
curl -i -X POST 'http://localhost:8080/api/signup' \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi' \
  -d '{"name":" ","age":16}'
```

HTTP **400 Bad Request**:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu không hợp lệ",
  "fields": [
    {
      "field": "age",
      "code": "Min",
      "message": "Age must be at least 18"
    },
    {
      "field": "name",
      "code": "NotBlank",
      "message": "Tên không được bỏ trống"
    }
  ]
}
```

The English text on `age` is the **intentional demonstration of a missing translation**; in production, add `Min.signupInput.age` to `messages_vi.properties` and update tests.

### 10.5. Unparseable JSON

```bash
curl -i -X POST 'http://localhost:8080/api/signup' \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi' \
  -d '{"name":"Lan","age":'
```

HTTP 400 with `code=INVALID_JSON`, message “Không thể đọc JSON của yêu cầu”. This is a **deserialization** error, not a `@Min(18)` violation.

## 11. MockMvc + MessageSource Tests

File `src/test/java/com/example/messagefallback/MessageFallbackTest.java`:

```java
package com.example.messagefallback;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.MessageSource;
import org.springframework.context.NoSuchMessageException;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MessageFallbackTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    MessageSource messages;

    private static final Locale VI = Locale.forLanguageTag("vi");

    @Test
    void availableVietnameseKeyIsUsed() throws Exception {
        mvc.perform(get("/api/messages/hello")
                .param("name", "Lan")
                .header("Accept-Language", "vi"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Xin chào, Lan!"));
    }

    @Test
    void englishHeaderUsesBaseEnglish() throws Exception {
        mvc.perform(get("/api/messages/hello")
                .param("name", "Lan")
                .header("Accept-Language", "en"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Hello, Lan!"));
    }

    @Test
    void missingVietnameseKeyFallsBackToBaseBundle()
            throws Exception {

        mvc.perform(get("/api/messages/base-only")
                .header("Accept-Language", "vi"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("This text is available only in the base bundle"));
    }

    @Test
    void missingKeyEverywhereUsesExplicitDefault() throws Exception {
        mvc.perform(get("/api/messages/unknown")
                .header("Accept-Language", "vi"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Information not available"));
    }

    @Test
    void strictMissingKeyThrowsNoSuchMessageException() {
        assertThrows(
                NoSuchMessageException.class,
                () -> messages.getMessage("ui.notProvided", null, VI)
        );
    }

    @Test
    void nullableExplicitDefaultReturnsNull() {
        String result = messages.getMessage(
                "ui.notProvided", null, (String) null, VI
        );
        assertNull(result);
    }

    @Test
    void explicitDefaultIsReturnedForAbsentKey() {
        String result = messages.getMessage(
                "ui.notProvided", null, "Safe fallback", VI
        );
        assertEquals("Safe fallback", result);
    }

    @Test
    void validationWithMissingViTranslationFallsBackToEnglish()
            throws Exception {

        mvc.perform(post("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("""
                        {"name":" ","age":16}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.message")
                    .value("Dữ liệu không hợp lệ"))
            .andExpect(jsonPath("$.fields[0].field").value("age"))
            .andExpect(jsonPath("$.fields[0].code").value("Min"))
            .andExpect(jsonPath("$.fields[0].message")
                    .value("Age must be at least 18"))
            .andExpect(jsonPath("$.fields[1].field").value("name"))
            .andExpect(jsonPath("$.fields[1].code")
                    .value("NotBlank"))
            .andExpect(jsonPath("$.fields[1].message")
                    .value("Tên không được bỏ trống"));
    }

    @Test
    void unsupportedLocaleUsesDefaultEnglish() throws Exception {
        mvc.perform(get("/api/messages/hello")
                .param("name", "Lan")
                .header("Accept-Language", "fr"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Hello, Lan!"));
    }

    @Test
    void malformedJsonHasASeparateLocalizedError() throws Exception {
        mvc.perform(post("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("{\"name\":\"Lan\",\"age\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"))
            .andExpect(jsonPath("$.message")
                    .value("Không thể đọc JSON của yêu cầu"));
    }

    @Test
    void validSignupPasses() throws Exception {
        mvc.perform(post("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("""
                        {"name":"Lan","age":24}
                        """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.name").value("Lan"))
            .andExpect(jsonPath("$.age").value(24));
    }
}
```

Run:

```bash
./gradlew test
```

**Expected:** 11 tests succeed when Java 17, the Gradle wrapper, and dependencies are available. Providing source code and expected results does **not** mean Gradle/JUnit was executed while writing the lesson.

The tests verify the difference between:

- Vietnamese key exists → Vietnamese.
- Vietnamese key missing, base exists → English.
- Key completely missing, default present → safe text.
- Key completely missing, strict overload → `NoSuchMessageException`.
- Null default → `null` result.
- Unsupported client locale → default locale.
- Input validation still returns HTTP 400 with invariant machine codes.
- Malformed JSON takes a separate exception path.

The advice **sorts errors by field and code**, so tests can rely on `age` appearing before `name`. If sorting is removed, provider violation order is not guaranteed; assert over lists of fields/codes rather than indices.

## 12. Translation Coverage: Do Not Let Runtime Fallback Hide Gaps

A naive test:

```java
assertEquals(
        "Age must be at least 18",
        messages.getMessage("Min.signupInput.age", null, VI)
);
```

does **not** prove the key was translated to `vi`. It may simply be reading from `messages.properties`.

To measure completeness, inspect **the specific locale bundle**, rather than using an API with fallback enabled to check for missing keys.

### 12.1. Example Test Checking for Missing Keys

The JUnit snippet below is **not part of the 11 tests above**; if run against this lesson's `messages_vi.properties`, it **intentionally fails** to flag missing translations:

```java
@Test
void allPublicKeysMustBeTranslatedToVietnamese() throws Exception {
    Properties base = new Properties();
    Properties vi = new Properties();

    try (Reader reader = new InputStreamReader(
            Objects.requireNonNull(getClass()
                    .getResourceAsStream("/messages.properties")),
            StandardCharsets.UTF_8)) {
        base.load(reader);
    }

    try (Reader reader = new InputStreamReader(
            Objects.requireNonNull(getClass()
                    .getResourceAsStream("/messages_vi.properties")),
            StandardCharsets.UTF_8)) {
        vi.load(reader);
    }

    List<String> missing = base.stringPropertyNames()
            .stream()
            .filter(key -> key.startsWith("ui.")
                    || key.startsWith("api.")
                    || key.startsWith("Min."))
            .filter(key -> !vi.containsKey(key)
                    || vi.getProperty(key).isBlank())
            .sorted()
            .toList();

    assertTrue(missing.isEmpty(),
            "Missing vi translations: " + missing);
}
```

Requires imports for `java.util.Properties`, `java.util.Objects`, `java.util.List`, `java.io.Reader`, `java.io.InputStreamReader`, `java.nio.charset.StandardCharsets`, and JUnit `assertTrue`. In a real codebase, you can maintain a dedicated i18n-lint module tracking public-facing keys that must be translated.

### 12.2. Comparing Placeholders

```properties
# Base
ui.invite=Invite {0} to {1}

# Vi missing info (content bug)
ui.invite=Mời tham gia
```

The key exists, yet `{0}`/`{1}` were dropped. CI should compare placeholder index sets, format types, and `MessageFormat` escaping rules. This defect will not manifest as a `NoSuchMessageException`.

### 12.3. Defining Severity by Message Category

- **Required in every language:** validation errors and core UI guidance.
- **Allow temporary fallback:** rare content where clear base English is available.
- **Internal-only:** log messages and diagnostics not shown to users; may not need every locale.
- **Security-sensitive:** messages must never contain secrets or infrastructure details, even in default fallbacks.

Avoid making the linter too blunt and blocking releases needlessly; classify keys and locale requirements per product.

## 13. Designing Fallbacks for Production

A resilient strategy can combine layers:

1. **Complete base bundle** as the foundation, e.g., English.
2. **Locale bundles** containing genuinely translated messages.
3. **Safe explicit `defaultMessage`** for error summaries and unknown codes at the boundary.
4. **Strict translation coverage tests** for mandatory user-facing keys.
5. **Logs/metrics** for missing codes (without logging sensitive raw user input).
6. **Stable error codes** independent of language.
7. **Controlled parser/internal error messages**, never pushing raw exception messages to clients.

### 13.1. Never Return Raw Codes to the Frontend

If `useCodeAsDefaultMessage` is enabled in production, users may see:

```text
validation.user.internalOwnerId.missing
```

This is confusing and can expose internal field names. Enable it only in controlled debug environments if truly needed; production should serve translations or safe fallbacks.

### 13.2. Never Let a Translation Error Turn a 400 into a 500

A `@Min` violation must return an input error (typically HTTP 400) when a client sends invalid data. If the error adapter calls `getMessage("Min.signupInput.age",null,locale)` strictly and the key is missing everywhere, the lookup failure can **erase the original validation response**.

Combine a complete base bundle with an error adapter that provides sensible defaults, while recording translation gaps in CI so poor quality is never hidden.

### 13.3. Never Put Sensitive Data in Defaults

`FieldError#getRejectedValue()` may contain passwords, emails, tokens, or personal data. `exception.getMessage()` may contain raw JSON, SQL, or class paths. Never pass them as the default message sent to clients:

```java
// Do not do this:
messages.getMessage(
        "api.error",
        null,
        exception.getMessage(),
        locale
);
```

Use controlled text instead:

```java
messages.getMessage(
        "api.error",
        null,
        "Unable to complete the request",
        locale
);
```

If message parameters include user input rendered into HTML, the view must escape it against XSS; `MessageSource` is not an HTML sanitizer.

## 14. `ProblemDetail` and Missing Translations

Spring Framework 6 provides `ProblemDetail` (RFC 9457) and `ResponseEntityExceptionHandler`. When using `ErrorResponse`, the framework supports `MessageSource` lookups for fields like `type`, `title`, and `detail` using exception-specific codes.

Using a custom `ApiError` like the example remains completely valid; if you adopt `ProblemDetail`, clearly define who is responsible for populating localized title/detail and which codes form the public contract.

**Illustrative method example**, not in the runnable source:

```java
@ExceptionHandler(SomeBusinessException.class)
ResponseEntity<ProblemDetail> conflict(
        SomeBusinessException error,
        Locale locale) {

    ProblemDetail detail = ProblemDetail.forStatus(409);
    detail.setTitle(messages.getMessage(
            "problem.conflict.title", null, "Conflict", locale));
    detail.setDetail(messages.getMessage(
            "problem.conflict.detail",
            null,
            "Operation conflicts with the current state",
            locale
    ));

    return ResponseEntity.status(409).body(detail);
}
```

The snippet assumes `SomeBusinessException` and the `messages` bean are defined. Requires importing `org.springframework.http.ProblemDetail`, `ResponseEntity`, and Spring annotations.

In Spring MVC 6.1+, `HandlerMethodValidationException` also distinguishes HTTP 400 input errors from HTTP 500 return-contract errors via `isForReturnValue()`. A missing translation on a 500 response error does not turn it into a client error; preserve separate status semantics and safe fallback messages.

## 15. Common Pitfalls

**1. Thinking a missing Vietnamese key always throws `NoSuchMessageException`.** If the base bundle has the code, Spring can return English.

**2. Thinking the explicit default is used immediately when the `vi` file lacks a key.** If the key still resolves from base, parent, or alternate codes, the explicit default is not used.

**3. Using the strict overload in every `@ExceptionHandler`.** A single missing key can cause the exception handler to throw another exception and lose the original HTTP 400.

**4. Passing `default=null` and treating the result as a non-null string.** That overload can return `null`; handle it explicitly in your response schema.

**5. Creating only `messages_vi.properties` without a base file.** Spring Boot auto-config may fail to detect `MessageSource` as expected.

**6. Thinking `fallback-to-system-locale=false` disables base fallback.** It only prevents trying the host server's locale.

**7. Enabling `useCodeAsDefaultMessage` on a parent `MessageSource`.** This can cause a multi-code `FieldError` to return a raw code before other fallback codes are tried.

**8. Resolving only `FieldError#getCode()`.** Ignores field-specific codes and arguments.

**9. Trusting `getDefaultMessage()` to always match the request locale.** It may have been pre-interpolated by Jakarta `MessageInterpolator`; Spring `MessageSource` can translate further or apply fallbacks.

**10. Forgetting `@NotNull` alongside `@Min`.** `@Min` treats `null` as valid, so a missing field may pass `@Min`.

**11. Omitting `@Valid` at the controller boundary.** Constraints on DTOs do not run automatically across every deserialization path.

**12. Treating malformed JSON as a Bean Validation error.** No object exists to validate; handle `HttpMessageNotReadableException` separately.

**13. Ignoring `ObjectError`.** `getAllErrors()` retains both class-level and field-level errors.

**14. Treating an empty-value key as a missing key.** Lookup may return an empty string; lint the content.

**15. Using `MessageSource` fallback to measure translation coverage.** The base bundle masks missing locale keys; inspect specific bundle files.

**16. Dropping placeholders during translation.** The key exists, yet the message loses data or breaks formatting.

**17. Calling `Locale.setDefault(...)` per request.** That mutates JVM-global state and corrupts concurrent requests.

**18. Not testing `vi` vs. `vi-VN` and `en` vs. `en-US`.** Locale matching depends on resolver config and supported locales.

**19. Returning raw `rejectedValue`/parser exceptions as default messages.** Leaks private data and framework internals.

**20. Frontend branching on literal translated messages.** Copy changes break logic; use stable error codes and fields.

## 16. Implementation Checklist

1. Provide base `messages.properties` and locale bundles such as `messages_vi.properties`.
2. Configure UTF-8, basename, and system-locale fallback properly.
3. Define supported locales and default locale; test real headers.
4. Distinguish locale fallback, bundle fallback, error-code fallback, and explicit defaults.
5. Use overloads with defaults for public messages that might be missing at runtime.
6. Use strict overloads in CI/startup to verify mandatory keys.
7. Never let raw codes become production fallbacks.
8. Use `getMessage(ObjectError/FieldError,locale)` when resolving multiple codes/arguments.
9. Use `getAllErrors()` so class-level errors are not lost.
10. Keep Spring's `messages*.properties` separate from Jakarta provider's `ValidationMessages*.properties`.
11. Never echo sensitive rejected values or exception messages.
12. Return stable error codes independent of localized text and preserve proper HTTP statuses.
13. Write `MockMvc` tests for `vi`/`en`, base-only, unknown keys, strict exceptions, null defaults, validation, and parser failures.
14. Lint locale bundles directly to catch missing or blank keys.
15. Compare `{0}`/`{1}` placeholders, escaping, and message content.
16. Configure HTTP caching properly if responses vary by `Accept-Language` (consider `Vary: Accept-Language`).
17. When upgrading Spring Boot/Framework, verify API/bundle behavior with integration tests.
18. Feed missing translations into QA/observability instead of ignoring them silently.

**Conclusion:** A missing locale translation does not mean no message is available. Spring can search the base bundle, try alternate error codes, query a parent, or use an explicit default. Maintain **safe runtime fallbacks** so critical responses are never lost, paired with **translation coverage tests** to catch missing translations before production. `MessageSource` selects the message; `LocaleResolver` selects the language; Jakarta Validation's `MessageInterpolator` handles constraint templates; keep each layer's responsibilities clear.

## References

- [Spring Framework — MessageSource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/MessageSource.html): overloads with `defaultMessage`, strict overloads, and `MessageSourceResolvable`.
- [Spring Framework — AbstractMessageSource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/context/support/AbstractMessageSource.html): `useCodeAsDefaultMessage`, parent, multiple codes.
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html): base bundle, basename, and `fallback-to-system-locale`.
- [Spring Framework — MVC Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): `ErrorResponse`, `ProblemDetail`, and i18n.
- [Spring Framework — Locale Resolver](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/localeresolver.html): `Accept-Language` and default locale.
- [Jakarta Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): message interpolation and constraint validation.
