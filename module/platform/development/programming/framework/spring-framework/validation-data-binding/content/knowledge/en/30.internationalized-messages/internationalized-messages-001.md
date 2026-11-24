# MessageSource and Locale for Displaying Errors in Spring Framework

## 1. Why Separate Validation Rules from Language?

A Spring REST API may serve both Vietnamese and international users. With the same invalid request:

```json
{"name":" ","age":17,"email":"lan@example.org"}
```

the business rules remain the same: `name` must not be blank, `age` must be at least 18. However, the messages can be:

| Locale | `name` field | `age` field |
| --- | --- | --- |
| `vi` | Tên không được bỏ trống | Tuổi phải từ 18 |
| `en` | Name must not be blank | Age must be at least 18 |

To implement this properly, we need to distinguish:

1. **Constraint** such as `@NotBlank`, `@Min`: decides whether data is valid or invalid; language-independent.
2. **Error code** such as `NotBlank.accountRequest.name`, `Min.accountRequest.age`: describes the error type for message lookup.
3. **`Locale`** such as `vi`, `en`, `vi-VN`: identifies the language/region to display.
4. **`MessageSource`**: resolves a message code and arguments according to a locale.
5. **Jakarta Validation's MessageInterpolator**: interpolates a constraint's message template, for example `{account.name.required}` or `{min}`/`{max}`.

This lesson focuses on **Spring Framework – validation/data binding**, Java 17+, Spring Boot 3.x, and Servlet Spring MVC. The runnable examples use Spring Boot 3.3.6 (Spring Framework 6.1.x); Spring WebFlux has a different exception/binding pipeline.

### Learning Outcomes

- Select the right locale from `Accept-Language`.
- Define translations in `messages.properties` and `messages_vi.properties`.
- Use `MessageSource.getMessage(FieldError, locale)` instead of only printing the default message.
- Return HTTP 400 with stable error codes, field paths, and localized messages.
- Distinguish conversion/malformed JSON errors from constraint validation.
- Understand when `ValidationMessages.properties` is used.
- Test Vietnamese, English, and fallback behavior with `MockMvc`.

## 2. How It Works in Spring MVC

```text
HTTP POST /api/accounts
Accept-Language: vi
Content-Type: application/json
             |
             v
DispatcherServlet / LocaleResolver
             | select Locale vi
             v
HttpMessageConverter / Jackson
             | JSON -> AccountRequest
             v
@Valid / Jakarta Validator
             | @NotBlank(name), @Min(age)
             v
BindingResult / FieldError / ObjectError
             | codes: NotBlank.accountRequest.name,
             |        NotBlank.name, NotBlank...
             v
@RestControllerAdvice
             | MessageSource.getMessage(error, locale)
             v
messages_vi.properties
             | Tên không được bỏ trống
             v
HTTP 400 JSON: field + code + localized message
```

**Binding** converts the request into a Java object; **validation** decides whether the values satisfy the constraints; **message resolution** selects the display message. All three are separate steps. Translating a message does not change the HTTP status, constraint values, or business logic.

With `@ModelAttribute` form/query parameters, Spring `WebDataBinder` can produce a `BindingResult` containing both conversion errors (e.g., `age=abc`) and Bean Validation errors. With `@RequestBody` JSON, the message converter must parse the JSON first; when JSON cannot be parsed, the result is usually `HttpMessageNotReadableException` rather than a `FieldError` generated from `@Min`.

## 3. What Is MessageSource?

`org.springframework.context.MessageSource` is the contract for resolving messages. Some key methods:

```java
// With fallback if the code does not exist:
String a = messages.getMessage(
        "api.validation.failed", null, "Invalid input", locale);

// Without fallback: may throw NoSuchMessageException:
String b = messages.getMessage(
        "api.validation.failed", null, locale);

// Resolve message from Spring's full list of codes:
String c = messages.getMessage(fieldError, locale);
```

The above is a snippet: assume `messages` is a `MessageSource` bean, `locale` is a `Locale`, and `fieldError` is a `FieldError`.

### 3.1. Argument Substitution

Bundle:

```properties
api.hello=Welcome, {0}!
api.age.range=Age must be between {0} and {1}
```

Java:

```java
String text = messages.getMessage(
        "api.hello",
        new Object[]{"Lan"},
        locale
);
```

With the English locale, the result is:

```text
Welcome, Lan!
```

`{0}`, `{1}` in Spring `MessageSource` follow `MessageFormat` semantics. Do not confuse them with `{min}` and `{max}` in Bean Validation templates, or EL variables like `${validatedValue}` interpolated by Jakarta/Hibernate Validator.

### 3.2. FieldError Is a MessageSourceResolvable

Spring `FieldError` and `ObjectError` provide:

- `getCode()`: simple error code, e.g., `NotBlank`.
- `getCodes()`: array of codes from most specific → most general.
- `getArguments()`: arguments for the message.
- `getDefaultMessage()`: existing default message or one interpolated by the provider.
- `getField()` on `FieldError`: the name of the invalid field.
- `getRejectedValue()`: the rejected value, **do not return this automatically to clients because it may contain sensitive data**.

When calling:

```java
String localized = messages.getMessage(fieldError, locale);
```

Spring can try a series of codes and fall back to the default message if the bundles do not contain a matching code. Calling `getCode()` and looking up only `NotBlank` will bypass specialized translations for a specific DTO/field.

## 4. DefaultMessageCodesResolver and Error Code Precedence

Suppose a DTO named `AccountRequest` has `@NotBlank String name`. An error on field `name` typically receives codes in this order:

```text
NotBlank.accountRequest.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
```

`DefaultMessageCodesResolver` lets Spring try the most specific code first. As a result:

```properties
NotBlank.accountRequest.name=Name must not be blank
NotBlank.name=A name is required
NotBlank=Text is required
```

can serve multiple levels of customization. The actual code names also depend on `objectName`, field type, nested property path, and error type. Do not hardcode the list above for every case.

With a custom Spring validator:

```java
errors.rejectValue("name", "app.name.blocked");
```

and object name `signup`, Spring can generate:

```text
app.name.blocked.signup.name
app.name.blocked.name
app.name.blocked.java.lang.String
app.name.blocked
```

You only need to place the appropriate key in the bundle; you do not have to write translation code inside the validator itself. Conversely, **a code registered by Spring `rejectValue` does not necessarily correspond to a Jakarta Validation annotation**.

### 4.1. Global Errors

Class-level custom constraints can produce an `ObjectError` rather than a `FieldError`. When building the response, you should inspect `getAllErrors()` or combine `getFieldErrors()` and `getGlobalErrors()`. Reading only field errors may cause the application to miss cross-field validation constraints. In the runnable project, we use `getAllErrors()` and represent object-level errors with `field=""`.

## 5. Locale in Spring MVC

### 5.1. Accept-Language

A client can send:

```http
Accept-Language: vi
```

or:

```http
Accept-Language: en-US,en;q=0.9,vi;q=0.8
```

Spring MVC uses `LocaleResolver` to choose the locale for the request. `AcceptHeaderLocaleResolver` typically reads the header and can configure supported locales and a default locale.

When a request goes through `DispatcherServlet`, controller methods and `@ExceptionHandler` methods in MVC can directly accept a `Locale locale` parameter:

```java
@GetMapping("/hello")
public String hello(Locale locale) {
    return locale.toLanguageTag();
}
```

Using a request-specific `Locale` allows the server to serve multiple users in different languages concurrently without changing the JVM-wide locale.

### 5.2. Supported Locales Do Not Automatically Normalize Every Language Tag

`vi` and `vi-VN` are two different locales; similarly for `en` and `en-US`. `AcceptHeaderLocaleResolver#setSupportedLocales` has matching rules where a locale containing language + country often requires an exact match; if you want language-only fallback, declare that locale appropriately. Always test the headers that real clients actually send.

In the runnable example, we intentionally support `vi` and `en` directly, and fall back to English for other language codes.

### 5.3. Do Not Miscombine with LocaleChangeInterceptor

`LocaleChangeInterceptor` is for selecting a locale via a request parameter like `?lang=vi` when paired with a resolver that supports `setLocale(...)`. `AcceptHeaderLocaleResolver` **does not support this setter**; the server cannot modify the HTTP `Accept-Language` header already sent by the client.

If the application needs to store the user's language in a cookie or session, consider `CookieLocaleResolver` or `SessionLocaleResolver`. Do not add the interceptor just because a tutorial uses a query parameter without also switching the resolver.

### 5.4. Avoid Locale.setDefault During Request Handling

Wrong:

```java
Locale.setDefault(Locale.forLanguageTag("vi"));
```

This changes the **JVM-wide** default, which can cause English requests to receive the wrong translation in a multithreaded environment. The right approach: obtain the `Locale` resolved for the request and pass it directly to `MessageSource`. `LocaleContextHolder` is useful in synchronous code with a request context, but does not replace explicit passing if logic runs asynchronously or outside a request.

## 6. Resource Bundles and Spring Boot Configuration

Typical structure:

```text
src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
  messages_en.properties         # Optional if the base is English
  messages_vi_VN.properties      # Optional if there are regional differences
```

Spring Boot includes `MessageSource` auto-configuration. With basename `messages`, make sure you have the **base file `messages.properties`**. Having only `messages_vi.properties` without a base file can prevent auto-configuration from creating the expected `MessageSource`.

`application.properties`:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Meaning:

- `basename` is the base name of the resource files. Multiple basenames such as `messages,i18n/errors` can be used when there really are two sets of resource files.
- `encoding=UTF-8` ensures Vietnamese characters are read properly.
- `fallback-to-system-locale=false` avoids using the host server's locale when the requested locale file is not found; it uses the base fallback by design.
- In production, configure appropriate caching; do not create a new `ResourceBundleMessageSource` per request.

If the application declares its own `MessageSource` bean named `messageSource`, note that Boot may back off in favor of the application-managed bean. In that case, basename/encoding/fallback configuration must be handled consistently.

### 6.1. Spring MessageSource and Jakarta ValidationMessages Are Two Separate Paths

Jakarta Validation allows:

```java
@NotBlank(message = "{account.name.required}")
private String name;

@Size(min = 4, max = 12, message = "{account.code.size}")
private String code;
```

The provider can look up these keys in:

```text
ValidationMessages.properties
ValidationMessages_vi.properties
```

Example:

```properties
# ValidationMessages.properties
account.name.required=Name is required
account.code.size=Code length must be from {min} to {max}
```

```properties
# ValidationMessages_vi.properties
account.name.required=Tên là bắt buộc
account.code.size=Mã phải có từ {min} đến {max} ký tự
```

`{min}`/`{max}` are attributes of the `@Size` constraint, not Spring `MessageFormat` arguments `{0}`/`{1}`. The interpolated result can become the default message in a `FieldError`, while `MessageSource#getMessage(fieldError, locale)` can override that message via Spring's code list.

When unifying bundle sources, Spring `LocalValidatorFactoryBean#setValidationMessageSource(...)` supports integration, but you must understand provider limitations and must not configure both `setValidationMessageSource` and `setMessageInterpolator` at the same time. Spring documentation notes that this capability relies on Hibernate Validator's interpolation support; it is not a portable feature across all Jakarta providers. Do not create a separate validator bean and assume MVC will definitely use it; verify the actual Spring Boot and Web MVC configuration.

In the runnable project below, **only `messages*.properties` is used for API errors**, while Jakarta templates are kept at their defaults. This makes Spring's resolution behavior easy to observe.

## 7. Runnable Project: Spring Boot, Java 17, vi/en Error API

The demo application includes:

- `POST /api/accounts`: JSON request, `@Valid`, HTTP 201 if valid.
- `@NotBlank`, `@Min`, `@NotNull` errors: HTTP 400 and localized messages.
- `GET /api/hello?name=Lan`: `MessageFormat` example with argument `{0}`.
- Unreadable JSON: HTTP 400 with a separate `INVALID_PAYLOAD` code.
- `MockMvc` tests for Vietnamese, English, fallback, missing field, and malformed JSON.

### 7.1. Source Structure

```text
i18n-validation-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/i18nvalidation/
        I18nValidationApplication.java
        LocaleConfiguration.java
        AccountRequest.java
        AccountController.java
        Violation.java
        ApiError.java
        ValidationAdvice.java
      resources/
        application.properties
        messages.properties
        messages_vi.properties
    test/
      java/com/example/i18nvalidation/
        I18nValidationTest.java
```

### 7.2. Gradle Build

File `settings.gradle`:

```groovy
rootProject.name = 'i18n-validation-demo'
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

`spring-boot-starter-web` brings Servlet Spring MVC/Jackson; `spring-boot-starter-validation` provides the typical Jakarta Validation provider (Hibernate Validator via the Spring Boot BOM). Without a provider, having `@Valid` in the source code alone does not guarantee validation will run automatically.

### 7.3. Spring Boot Application

`src/main/java/com/example/i18nvalidation/I18nValidationApplication.java`:

```java
package com.example.i18nvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class I18nValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(I18nValidationApplication.class, args);
    }
}
```

### 7.4. Locale Configuration

`src/main/java/com/example/i18nvalidation/LocaleConfiguration.java`:

```java
package com.example.i18nvalidation;

import java.util.List;
import java.util.Locale;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.i18n.AcceptHeaderLocaleResolver;

@Configuration
public class LocaleConfiguration {

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

`Accept-Language: vi` selects Vietnamese; `en` selects English; `fr` is not in the list so it falls back to English. For clients sending `vi-VN`/`en-US`, add and test actual locale support when required by the product.

### 7.5. Resource Files

`src/main/resources/application.properties`:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

`src/main/resources/messages.properties` (English base):

```properties
api.validation.failed=Input is invalid
api.invalid.json=Request JSON cannot be read
api.hello=Welcome, {0}!

NotBlank.accountRequest.name=Name must not be blank
NotBlank.name=Name must not be blank
Min.accountRequest.age=Age must be at least 18
Min.age=Age must be at least 18
NotNull.accountRequest.age=Age is required
NotNull.age=Age is required
Email.accountRequest.email=Email format is invalid
Email.email=Email format is invalid
```

`src/main/resources/messages_vi.properties`:

```properties
api.validation.failed=Dữ liệu không hợp lệ
api.invalid.json=Không thể đọc JSON của yêu cầu
api.hello=Xin chào, {0}!

NotBlank.accountRequest.name=Tên không được bỏ trống
NotBlank.name=Tên không được bỏ trống
Min.accountRequest.age=Tuổi phải từ 18
Min.age=Tuổi phải từ 18
NotNull.accountRequest.age=Tuổi là bắt buộc
NotNull.age=Tuổi là bắt buộc
Email.accountRequest.email=Định dạng email không hợp lệ
Email.email=Định dạng email không hợp lệ
```

When Spring creates a `FieldError` for the `AccountRequest` record, specific codes such as `NotBlank.accountRequest.name` and `Min.accountRequest.age` are looked up first; `NotBlank.name` and `Min.age` also serve as fallbacks. `api.validation.failed` and `api.invalid.json` are custom **application codes**, not Jakarta constraint names.

### 7.6. DTO with Constraints

`src/main/java/com/example/i18nvalidation/AccountRequest.java`:

```java
package com.example.i18nvalidation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record AccountRequest(
        @NotBlank String name,
        @NotNull @Min(18) Integer age,
        @Email String email
) {}
```

`age` needs both `@NotNull` and `@Min`: `@Min` by itself treats `null` as valid. `email` is optional in the demo (`@Email` does not forbid `null`); add `@NotBlank` if the business contract requires an email.

### 7.7. Error DTO with Stable Codes

`src/main/java/com/example/i18nvalidation/Violation.java`:

```java
package com.example.i18nvalidation;

public record Violation(
        String field,
        String code,
        String message
) {}
```

`src/main/java/com/example/i18nvalidation/ApiError.java`:

```java
package com.example.i18nvalidation;

import java.util.List;

public record ApiError(
        String code,
        String message,
        List<Violation> errors
) {}
```

`code` is for client logic, `message` is for display; `field` identifies the error location. When localizing, `field`/`code` should not change by language.

### 7.8. Controller

`src/main/java/com/example/i18nvalidation/AccountController.java`:

```java
package com.example.i18nvalidation;

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
public class AccountController {

    private final MessageSource messages;

    public AccountController(MessageSource messages) {
        this.messages = messages;
    }

    @PostMapping(
        path = "/accounts",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody AccountRequest input) {

        return ResponseEntity.status(HttpStatus.CREATED).body(
                Map.of("name", input.name(), "age", input.age())
        );
    }

    @GetMapping("/hello")
    public Map<String, String> hello(
            @RequestParam(defaultValue = "visitor") String name,
            Locale locale) {

        return Map.of(
                "message",
                messages.getMessage(
                        "api.hello",
                        new Object[]{name},
                        locale
                )
        );
    }
}
```

For POST, Spring must deserialize the JSON and validate `AccountRequest` before invoking `create` if there are no errors. For GET, the `Locale` parameter is resolved by Spring MVC per request and used to look up `api.hello`.

### 7.9. Advice Using MessageSource to Build Responses

`src/main/java/com/example/i18nvalidation/ValidationAdvice.java`:

```java
package com.example.i18nvalidation;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import org.springframework.context.MessageSource;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationAdvice {

    private final MessageSource messages;

    public ValidationAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException ex,
            Locale locale) {

        String summary = messages.getMessage(
                "api.validation.failed", null, locale
        );

        return ResponseEntity.badRequest().body(
                toApiError(ex.getBindingResult(), locale, summary)
        );
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException ex,
            Locale locale) {

        String text = messages.getMessage(
                "api.invalid.json", null, locale
        );

        return ResponseEntity.badRequest().body(
                new ApiError("INVALID_PAYLOAD", text, List.of())
        );
    }

    private ApiError toApiError(
            BindingResult result,
            Locale locale,
            String summary) {

        List<Violation> errors = result.getAllErrors()
                .stream()
                .map(error -> asViolation(error, locale))
                .sorted(Comparator
                        .comparing(Violation::field)
                        .thenComparing(Violation::code))
                .toList();

        return new ApiError("VALIDATION_ERROR", summary, errors);
    }

    private Violation asViolation(
            ObjectError error,
            Locale locale) {

        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        String code = Objects.toString(error.getCode(), "invalid");

        // Resolve across all codes/arguments, not just error.getCode().
        String message = messages.getMessage(error, locale);

        return new Violation(field, code, message);
    }
}
```

**Explanation:**

- `MethodArgumentNotValidException` is the typical exception path when a `@Valid @RequestBody` command object fails Bean Validation.
- `getAllErrors()` retains both `FieldError` and `ObjectError` (class-level). For global errors, the example sets `field=""`.
- `messages.getMessage(error, locale)` resolves across all codes and uses the default message when needed.
- Sorting by `field` then `code` gives the response an application-defined deterministic order; constraint evaluation order is not guaranteed by Jakarta.
- The `HttpMessageNotReadableException` handler is dedicated to JSON that cannot be deserialized. Do not report it as a `@NotBlank` error when the object was never created.
- The API does not return rejected values or raw parser exceptions to avoid leaking sensitive data.

## 8. Testing with MockMvc

`src/test/java/com/example/i18nvalidation/I18nValidationTest.java`:

```java
package com.example.i18nvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class I18nValidationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void invalidInputIsTranslatedIntoVietnamese() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("""
                        {
                          "name": " ",
                          "age": 17,
                          "email": "lan@example.org"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.message")
                    .value("Dữ liệu không hợp lệ"))
            .andExpect(jsonPath("$.errors[0].field").value("age"))
            .andExpect(jsonPath("$.errors[0].code").value("Min"))
            .andExpect(jsonPath("$.errors[0].message")
                    .value("Tuổi phải từ 18"))
            .andExpect(jsonPath("$.errors[1].field").value("name"))
            .andExpect(jsonPath("$.errors[1].message")
                    .value("Tên không được bỏ trống"));
    }

    @Test
    void sameConstraintsDisplayEnglish() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "en")
                .content("""
                        {
                          "name": " ",
                          "age": 17,
                          "email": "lan@example.org"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value("Input is invalid"))
            .andExpect(jsonPath("$.errors[0].message")
                    .value("Age must be at least 18"))
            .andExpect(jsonPath("$.errors[1].message")
                    .value("Name must not be blank"));
    }

    @Test
    void localizedGreetingUsesAnArgument() throws Exception {
        mvc.perform(get("/api/hello")
                .param("name", "Lan")
                .header("Accept-Language", "vi"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Xin chào, Lan!"));

        mvc.perform(get("/api/hello")
                .param("name", "Lan")
                .header("Accept-Language", "en"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Welcome, Lan!"));
    }

    @Test
    void unsupportedLocaleFallsBackToEnglish() throws Exception {
        mvc.perform(get("/api/hello")
                .param("name", "Lan")
                .header("Accept-Language", "fr"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Welcome, Lan!"));
    }

    @Test
    void missingAgeUsesNotNullTranslation() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("""
                        {
                          "name": "Lan",
                          "email": "lan@example.org"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field").value("age"))
            .andExpect(jsonPath("$.errors[0].code").value("NotNull"))
            .andExpect(jsonPath("$.errors[0].message")
                    .value("Tuổi là bắt buộc"));
    }

    @Test
    void malformedJsonIsNotValidationError() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("{\"name\":\"Lan\",\"age\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_PAYLOAD"))
            .andExpect(jsonPath("$.message")
                    .value("Không thể đọc JSON của yêu cầu"));
    }

    @Test
    void validRequestSucceeds() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("""
                        {
                          "name": "Lan",
                          "age": 24,
                          "email": "lan@example.org"
                        }
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

On Windows:

```powershell
.\gradlew.bat test
```

**Expected result:** seven tests PASS when the dependencies and resource files are configured properly. The same invalid request returns different messages by locale, while HTTP status, `code`, and `field` remain unchanged.

In the demo, the advice explicitly **sorts errors by field**, so `errors[0]` is `age` and `errors[1]` is `name`. If you remove sorting, do not assert positions in the error list because the provider may evaluate constraints in a different order.

Writing tests in this article should not be taken as proof that Gradle was executed on your machine; run `./gradlew test` in an actual project before deploying.

## 9. Trying the API with curl

Start the app:

```bash
./gradlew bootRun
```

**Vietnamese:**

```bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi' \
  -d '{"name":" ","age":17,"email":"lan@example.org"}'
```

Expected HTTP **400 Bad Request**, with the corresponding body:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu không hợp lệ",
  "errors": [
    {
      "field": "age",
      "code": "Min",
      "message": "Tuổi phải từ 18"
    },
    {
      "field": "name",
      "code": "NotBlank",
      "message": "Tên không được bỏ trống"
    }
  ]
}
```

**English:**

```bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: en' \
  -d '{"name":" ","age":17,"email":"lan@example.org"}'
```

HTTP is still **400**, but the messages are `Age must be at least 18` and `Name must not be blank`. The `code` fields are still `Min` and `NotBlank`.

**Greeting:**

```bash
curl -i 'http://localhost:8080/api/hello?name=Lan' \
  -H 'Accept-Language: vi'
```

Body:

```json
{"message":"Xin chào, Lan!"}
```

This is a straightforward example of one message code having multiple translations and arguments; the business method does not need to write `if(locale...)`.

## 10. Handling @ModelAttribute Form Errors

`@ModelAttribute` typically goes through `WebDataBinder`, which can produce both conversion errors and Jakarta constraint errors. A controller can handle `BindingResult` itself if it places it **immediately after** the bound argument:

```java
@PostMapping("/signup")
public ResponseEntity<Map<String, Object>> signup(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors,
        Locale locale) {

    if (errors.hasErrors()) {
        List<String> texts = errors.getAllErrors().stream()
                .map(error -> messages.getMessage(error, locale))
                .toList();
        return ResponseEntity.badRequest()
                .body(Map.of("messages", texts));
    }

    return ResponseEntity.ok(Map.of("status", "created"));
}
```

This is an **illustrative snippet** outside the runnable application; assume `SignupForm` is defined and the `MessageSource messages` bean is injected.

With `age=abc` in a form containing `Integer age`, the binder can produce a `typeMismatch.signup.age` error. You can translate it:

```properties
# messages.properties
typeMismatch.signup.age=Age must be a number
```

```properties
# messages_vi.properties
typeMismatch.signup.age=Tuổi phải là một số
```

That is a **type conversion** error rather than a `@Min` violation. If a JSON body has invalid syntax, the controller usually is not even invoked, so `BindingResult` is not the tool for handling parser errors; an appropriate `@ExceptionHandler` is needed.

### BindingResult Position

Right:

```java
method(@Valid @ModelAttribute Form form, BindingResult errors)
```

Wrong:

```java
method(@Valid @ModelAttribute Form form,
       @RequestParam String referrer,
       BindingResult errors)
```

These are illustrative method signatures. `BindingResult` must sit immediately next to the argument it binds to. If Spring MVC 6.1+ uses **method validation** due to direct constraints on the signature, also check `HandlerMethodValidationException`; do not assume every error is `MethodArgumentNotValidException`.

## 11. Integration with ProblemDetail and Method Validation

Spring Framework supports `ProblemDetail` and `ResponseEntityExceptionHandler`. When using the `ErrorResponse` mechanism, message codes for `type`, `title`, and `detail` can be resolved through `MessageSource`. This is a good choice if the API standardizes on RFC 9457 instead of using a custom `ApiError`.

In Spring MVC 6.1+, a handler with a direct constraint such as:

```java
@GetMapping("/pages")
public String page(@RequestParam @Min(1) int page) {
    return "page=" + page;
}
```

typically uses `HandlerMethodValidationException` instead of `MethodArgumentNotValidException` for input validation. The exception provides `isForReturnValue()` to distinguish:

- Input constraint violation → typically HTTP **400**.
- Return-value constraint violation → server contract error, typically HTTP **500**.

When localizing method validation errors, preserve this distinction; do not catch every validation exception and return 400. The `MessageSourceResolvable` instances in method validation results can be resolved against the request locale, or you can use `ResponseEntityExceptionHandler` for common i18n support. When having multiple handlers/advice classes, check `@Order` precedence and avoid duplicate declarations that cause conflicts.

## 12. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Has `messages_vi.properties` without `messages.properties` | Boot MessageSource auto-config does not behave as expected | Add the base bundle |
| Errors always appear in English | Wrong locale, missing key, or only using `getDefaultMessage()` | Check Accept-Language, resolver, and `getMessage(error, locale)` |
| `NoSuchMessageException` error | Calling `getMessage` without fallback for a missing key | Add the key or use an overload with a default |
| Translations lack field-specific semantics | Only resolving `getCode()` | Pass the full `FieldError` as a `MessageSourceResolvable` |
| `@Valid` does not work | Missing provider or activated at the wrong boundary | Check validation starter and annotation boundary |
| `@Min` does not trigger when field is null | `@Min` allows null | Add `@NotNull` |
| Class-level constraint errors are lost | Only reading `getFieldErrors()` | Use `getAllErrors()` |
| Malformed JSON returned as Bean Validation | Parser exception not separated | Add an `HttpMessageNotReadableException` handler |
| `LocaleChangeInterceptor` does not change language | Using `AcceptHeaderLocaleResolver` | Use Cookie/Session resolver if query-parameter language switching is needed |
| Seeing `TÃªn` instead of `Tên` | Wrong encoding/terminal | Read bundle as UTF-8, check response/client |
| Changing language breaks the frontend | Frontend compares literal messages | Use stable `code` and `field` |
| Codes and messages depend on provider | API exposes raw constraint text as code | Map to stable business error codes |
| Message contains secrets | Using rejectedValue/parser text in messages | Return controlled text, do not expose values |
| All error responses are 400 | Not distinguishing input vs output contract | Return-value violations are usually 500 |
| Difference between `vi` and `vi-VN` | Supported locale matching does not match expectations | Declare and test actual BCP 47 tags |
| Mixing `javax.validation` and `jakarta.validation` | Spring Boot 2 vs 3 namespace | Use Jakarta for Spring Boot 3 |
| HTTP cache returns wrong language | Cache does not account for `Accept-Language` | Consider `Vary: Accept-Language` and cache key |
| Wrong timezone for number/date formatting | Confusing Locale with timezone | Configure timezone separately when needed |

### Message Security

`FieldError#getRejectedValue()` may contain passwords, tokens, or PII. Do not return rejected values in JSON just to “help the user fix it”. Similarly, raw `HttpMessageNotReadableException#getMessage()` may leak Java/Jackson internals or request content. Use controlled error codes and messages, and log safely with a correlation ID on the server side.

`MessageSource` is not an HTML sanitizer. If user-supplied messages or arguments are inserted into HTML pages, the view layer must escape output appropriately to prevent XSS.

### Performance and Environment

Do not create a new `ResourceBundleMessageSource` per request. Reuse the Spring-managed bean, configure appropriate caching, and ensure bundles are packaged completely at deploy time. Do not use `Locale.setDefault` to change the request language. With `@Async`, scheduled jobs, or reactive pipelines, do not assume ThreadLocal `LocaleContextHolder` always propagates with the task; pass `Locale` explicitly when needed.

## 13. Implementation Checklist

1. Finalize the list of genuinely supported languages/regions (`vi`/`en`, plus `vi-VN`/`en-US` if needed).
2. Create the base `messages.properties` and each translation file; ensure UTF-8.
3. Configure `spring.messages.basename`, fallback, and encoding.
4. Use a `LocaleResolver` suited to the product's locale source.
5. Never use `Locale.setDefault(...)` per request.
6. Enable the Jakarta Validation provider and apply `@Valid`/`@Validated` at the right boundary.
7. For Spring binding errors, use `MessageSource#getMessage(FieldError/ObjectError, Locale)` to resolve across all codes.
8. Keep `error.code` and `error.field` stable; only localized text changes.
9. Distinguish `ValidationMessages`/`MessageInterpolator` from `messages`/`MessageSource`; integrate intentionally when needed.
10. Handle field errors, global errors, conversion errors, and parser exceptions according to their proper type.
11. Never return rejected values, raw stack traces, or sensitive data.
12. Write MockMvc tests for Vietnamese/English/fallback, missing keys, missing fields, type mismatches, malformed JSON, and valid requests.
13. If using `ProblemDetail`, clearly define which layer is responsible for translating `type/title/detail` and the advice order.
14. If responses vary by `Accept-Language` and caching is used, consider `Vary: Accept-Language` and cache keys.
15. Verify Jakarta namespace and Spring Boot BOM compatibility when upgrading.

**Conclusion:** `MessageSource` answers “for this error code and locale, which sentence should be displayed?”, `LocaleResolver` determines the request's language, and `FieldError`/`ObjectError` indicates which rule was violated. Jakarta Validation's `MessageInterpolator` is a separate mechanism for interpolating constraint templates. By keeping these layers independent, the same API can return contextually accurate Vietnamese/English messages while keeping validation rules, HTTP statuses, and machine-readable error codes consistent.

## References

- [Spring Framework — Resolving Codes to Error Messages](https://docs.spring.io/spring-framework/reference/6.2/core/validation/conversion.html): `DefaultMessageCodesResolver` and error code ordering.
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html): `spring.messages.*`, base bundle rules.
- [Spring Framework — Locale](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/localeresolver.html): `LocaleResolver`, `Accept-Language`, and language selection.
- [Spring Framework — AcceptHeaderLocaleResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/i18n/AcceptHeaderLocaleResolver.html): supported locales list and `setLocale` limitation.
- [Spring Framework — LocalValidatorFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html): connecting Jakarta validation to Spring `MessageSource`.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): argument/method validation and exceptions.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): resource bundles and `MessageInterpolator`.
