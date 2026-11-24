# MessageInterpolator and the Message Interpolation Mechanism in Spring Framework

## 1. What is message interpolation?

When validating data with Jakarta Bean Validation, a constraint can declare an error message as plain text or a **message template** (also called a message descriptor). **`MessageInterpolator`** is the component that turns that template into a human-readable string to return to the user. It resolves keys in resource bundles, substitutes annotation attribute values, evaluates expressions when enabled, and selects the appropriate language.

For example:

```java
@Size(min = 4, max = 12,
      message = "{order.code.size}")
private String code;
```

Suppose `ValidationMessages_vi.properties` contains:

```properties
order.code.size=Mã đơn phải có từ {min} đến {max} ký tự
```

With a Vietnamese `Locale`, when `code = "ab"`, the constraint fails and the message is interpolated into:

```text
Mã đơn phải có từ 4 đến 12 ký tự
```

There are two distinct actions:

1. **Rule checking**: `@Size` determines that the length of `"ab"` is 2, which is less than `min = 4`.
2. **Message interpolation**: `MessageInterpolator` takes the template `"{order.code.size}"`, looks up the translation, and replaces `{min}` and `{max}` with the attributes of `@Size`.

The interpolation component **does not decide whether a value is valid**, does not automatically translate field names, does not modify data, and does not generate HTTP formatting on its own. Producing HTTP 400 and the JSON structure is the responsibility of the web/exception handling layer.

Scope of this article: Jakarta Validation 3.x, Spring Framework 6.x and Spring Boot 3.x, Java 17+. The examples use the `jakarta.validation.*` package; Spring Boot 2.x projects use the `javax.validation.*` namespace.

## 2. Terminology and components to distinguish

| Component | Example | Role |
| --- | --- | --- |
| Constraint | `@Size(min=4, max=12)` | Data rule |
| Message descriptor/template | `"{order.code.size}"` | Message template before interpolation |
| User resource bundle | `ValidationMessages_vi.properties` | Translations provided by the application |
| Provider bundle | Default messages from Hibernate Validator | Built-in messages for standard constraints |
| Constraint attribute | `min=4`, `max=12` | Values used for `{min}` and `{max}` |
| Message parameter | `{order.code.size}`, `{min}` | Bundle key or constraint attribute name |
| EL expression | `${validatedValue}` | Jakarta Expression Language expression |
| MessageInterpolator | `jakarta.validation.MessageInterpolator` | Interpolates the descriptor given a context and locale |
| ConstraintViolation | `getMessageTemplate()`, `getMessage()` | Holds both the original template and the interpolated message |
| Spring MessageSource | `messages.properties` and `MessageSource` | Spring's message/i18n resolution system, which can integrate with Bean Validation |

Typical flow:

```text
@Size(message="{order.code.size}", min=4, max=12)
                |
                v
ConstraintValidator detects violation
                |
                v
MessageInterpolator(template, context, locale)
                |
      +---------+----------+
      |                    |
ValidationMessages    @Size attributes
      |                    |
      +---------+----------+
                |
                v
"Mã đơn phải có từ 4 đến 12 ký tự"
                |
                v
ConstraintViolation#getMessage()
                |
                v
Spring FieldError / BindingResult / API response
```

Note the difference between the two APIs:

- `violation.getMessageTemplate()` returns the template, for example `"{order.code.size}"`.
- `violation.getMessage()` returns the interpolated message, for example `"Mã đơn phải có từ 4 đến 12 ký tự"`.
- `violation.getPropertyPath()` describes the error location; it is independent of language and message content.

## 3. Default Jakarta Validation interpolation rules

To understand `MessageInterpolator` accurately, you need to know the standard processing order. For a descriptor like `"{order.code.size}"`, the provider follows this algorithm:

1. **Look up in the application bundle** with basename `ValidationMessages` for the locale. If `{key}` exists, replace it with the key's value; perform this **recursively** for keys found in the newly inserted value until no more replacements occur via this bundle.
2. **Look up in the provider's built-in bundle** (for example, Hibernate Validator's default messages). Replacements from the provider bundle in this step **do not recurse**.
3. If step 2 performed a replacement, **run step 1 again** so the application bundle has a chance to override/define keys referenced in the provider message.
4. Replace remaining parameters whose names match attributes of the constraint annotation, for example `{min}` with `4` and `{max}` with `12`. Attribute values inserted in this step **are not interpolated further**.
5. Evaluate `${...}` expressions using Jakarta Expression Language (EL) within the allowed feature level.

The algorithm places the **application bundle before the provider bundle** so you can customize messages even for standard constraints. Parameter replacement `{...}` takes precedence over EL `${...}` for compatibility with older Bean Validation versions; keep this in mind if you use syntax with overlapping names.

### 3.1. Step-by-step illustration with nested keys

```java
@Size(
    min = 4,
    max = 12,
    message = "{order.code.size}"
)
String code;
```

```properties
# ValidationMessages_vi.properties
order.code.label=Mã đơn
order.code.size={order.code.label} phải có từ {min} đến {max} ký tự
```

Process:

```text
{order.code.size}
  -> {order.code.label} phải có từ {min} đến {max} ký tự
  -> Mã đơn phải có từ {min} đến {max} ký tự
  -> Mã đơn phải có từ 4 đến 12 ký tự
```

The first two `{order...}` replacements are recursive key lookups in the bundle. Replacing `{min}` and `{max}` afterward reads the attributes of `@Size` (when the bundle does not provide keys with the same names). This allows a single message template to be reused across annotations with different configurations.

**Avoid creating circular references** between resource bundle keys, such as `a={b}` and `b={a}`. Design short, clear reference chains; test the messages after adding new keys.

### 3.2. Distinguishing syntax forms

| Descriptor | Interpretation |
| --- | --- |
| `"Invalid code"` | Fixed string; no bundle lookup needed |
| `"{order.code.size}"` | Look up key from bundle by locale |
| `"From {min} to {max}"` | Parameters can come from constraint attributes |
| `"Value is ${validatedValue}"` | Jakarta EL when supported/enabled |
| `"order.code.size"` | Literal string; missing `{}` braces so it is not looked up in the bundle as a key |

Characters with special meaning in a message descriptor must be escaped if you want them to appear literally: `\{`, `\}`, `\$`, and `\\`. When writing descriptors in **Java strings** or **`.properties` files**, you must also follow the escaping rules of Java/Properties; therefore, verify the actual runtime value if you need to display literal braces or `$`.

## 4. Building a bilingual Spring Boot example

We will create a `POST /orders` API that accepts an order code of 4–12 characters. Sending `"ab"` with `Accept-Language: vi` returns a Vietnamese error; with `Accept-Language: en`, it returns an English error. In addition to locale-based messages, the example illustrates nested keys and `{min}`, `{max}` parameters.

### 4.1. Dependencies and project structure

Use Gradle/Groovy with Java 17 and Spring Boot 3.3.x. The `build.gradle` example can run standalone once the project has the Gradle wrapper:

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

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` provides the Jakarta Validation API, Hibernate Validator (provider), and the required integration. Having only the annotation API without a provider will not create a working validation system. Spring Boot 3.3.x uses Hibernate Validator 8.x according to the release's dependency management.

```text
src/
  main/
    java/com/example/interpolation/
      DemoApplication.java
      api/OrderRequest.java
      api/OrderController.java
      api/ValidationExceptionHandler.java
    resources/
      ValidationMessages.properties
      ValidationMessages_vi.properties
  test/
    java/com/example/interpolation/
      OrderApiValidationTest.java
```

### 4.2. DTO declaring message templates

File `src/main/java/com/example/interpolation/api/OrderRequest.java`:

```java
package com.example.interpolation.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record OrderRequest(
    @NotBlank(message = "{order.code.required}")
    @Size(min = 4, max = 12, message = "{order.code.size}")
    String code
) {}
```

`@NotBlank` reports an error when the value is null/empty/whitespace-only; `@Size` reports an error when the string does not match the length bounds (it considers `null` valid per the constraint contract). An empty input can violate both constraints simultaneously; that is normal behavior, and you should not rely on the order of errors in the list.

### 4.3. Declaring the base bundle and translation

File `src/main/resources/ValidationMessages.properties` is the default (fallback) bundle, using English here:

```properties
order.code.label=Order code
order.code.required=Order code must not be blank
order.code.size={order.code.label} must contain {min} to {max} characters
```

File `src/main/resources/ValidationMessages_vi.properties`:

```properties
order.code.label=Mã đơn
order.code.required=Mã đơn không được để trống
order.code.size={order.code.label} phải có từ {min} đến {max} ký tự
```

Points to remember:

- The default name is **`ValidationMessages`**, not `ValidationMessage` or `messages`; the files must be placed on the classpath, typically `src/main/resources`.
- The locale suffix follows the basename, for example `_vi`, `_en`, `_en_US`. The fallback mechanism depends on `ResourceBundle` and the actual locale configuration. Having a base file makes fallback behavior clear.
- If a key disappears from the Vietnamese translation, the system may use the fallback value (depending on the bundle chain found). Do not let missing keys be discovered only after deployment.
- `ValidationMessages*.properties` is used for Bean Validation interpolation. The `messages*.properties` files that Spring Boot typically uses for `MessageSource` are **a separate mechanism**, unless you configure them to integrate.
- Save files in UTF-8 and check how the provider/JDK reads properties in the actual environment; do not corrupt Vietnamese diacritics with broken encoding.

### 4.4. Spring Boot application and controller

File `src/main/java/com/example/interpolation/DemoApplication.java`:

```java
package com.example.interpolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File `src/main/java/com/example/interpolation/api/OrderController.java`:

```java
package com.example.interpolation.api;

import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    @PostMapping
    public ResponseEntity<Map<String, String>> create(
            @Valid @RequestBody OrderRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("code", request.code()));
    }
}
```

`@Valid` triggers Bean Validation for `@RequestBody` after Jackson deserialization. In Spring MVC using `LocalValidatorFactoryBean`, Spring provides the `LocaleContextMessageInterpolator` adapter to pass the `LocaleContextHolder` locale to the provider. In a normally processed HTTP request, Spring MVC determines the locale via `LocaleResolver`; a common configuration uses the `Accept-Language` header. This allows messages to be interpolated per request rather than changing `Locale.setDefault(...)` for the entire JVM.

If you instantiate a validator separately using `Validation.buildDefaultValidatorFactory()` **outside Spring**, Jakarta Validation's default algorithm uses `Locale.getDefault()`, so you cannot assume it will read the HTTP request's locale. Distinguish between the two contexts.

### 4.5. HTTP error formatting

File `src/main/java/com/example/interpolation/api/ValidationExceptionHandler.java`:

```java
package com.example.interpolation.api;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handle(
            MethodArgumentNotValidException exception) {

        List<Map<String, String>> errors =
                exception.getBindingResult().getFieldErrors().stream()
                .map(this::toError)
                .toList();

        return ResponseEntity.badRequest()
                .body(Map.of("errors", errors));
    }

    private Map<String, String> toError(FieldError error) {
        return Map.of(
                "field", error.getField(),
                "message", Objects.toString(error.getDefaultMessage(), "")
        );
    }
}
```

This handler only illustrates **field violations**; real applications may need to add `getGlobalErrors()` for class-level constraints, handle deserialization errors (`HttpMessageNotReadableException`), and handle method validation errors. `MethodArgumentNotValidException` is the typical path when `@Valid @RequestBody` fails Bean Validation and there is no `BindingResult` immediately after the parameter.

**Relationship with Spring:** `FieldError` is created from a violation and contains message codes and a default message. Calling `error.getDefaultMessage()` in this example retrieves the message already interpolated by Bean Validation. At another presentation layer, Spring `MessageSource` can also look up `MessageSourceResolvable`/error codes such as `Size.orderRequest.code` to select a UI-layer translation. Both processes can affect the string the user sees, but they are not the same step.

### 4.6. Sending requests and expected results

Start the application:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`.

Send an invalid request asking for Vietnamese:

```bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"code":"ab"}'
```

Expect HTTP `400 Bad Request` with a body containing (JSON field order is not guaranteed):

```json
{
  "errors": [
    {
      "field": "code",
      "message": "Mã đơn phải có từ 4 đến 12 ký tự"
    }
  ]
}
```

Switch to English:

```bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -H "Accept-Language: en" \
  -d '{"code":"ab"}'
```

Expect HTTP `400 Bad Request` with the message:

```text
Order code must contain 4 to 12 characters
```

Send a valid input:

```bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"code":"ORD-2048"}'
```

Expect HTTP `201 Created` and body `{"code":"ORD-2048"}`. When the data is valid, there is no `ConstraintViolation` requiring error message interpolation.

## 5. Automated testing of locale and interpolation

File `src/test/java/com/example/interpolation/OrderApiValidationTest.java`:

```java
package com.example.interpolation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderApiValidationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void vietnameseMessageInterpolatesKeyAndConstraintAttributes()
            throws Exception {

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                .content("{\"code\":\"ab\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field").value("code"))
            .andExpect(jsonPath("$.errors[0].message")
                .value("Mã đơn phải có từ 4 đến 12 ký tự"));
    }

    @Test
    void englishMessageUsesDefaultBundle() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                .content("{\"code\":\"ab\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].message")
                .value("Order code must contain 4 to 12 characters"));
    }

    @Test
    void validOrderPassesValidation() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"code\":\"ORD-2048\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.code").value("ORD-2048"));
    }
}
```

Run:

```bash
./gradlew test
```

The three tests separate: nested key interpolation + `{min}`/`{max}` in the Vietnamese locale, English fallback, and a valid request. They verify behavior through the real HTTP entry point, where `Accept-Language` takes effect. If a locale test fails, first check the bundle filenames, classpath location, and the `LocaleResolver`/validator configuration used by the project.

To observe both the original template and the interpolated result via the Jakarta API, you can inspect them from the same violation as follows (this snippet assumes a `validator` variable of type `jakarta.validation.Validator` is provided and the locale is already set):

```java
var violations = validator.validate(new OrderRequest("ab"));
for (var violation : violations) {
    System.out.println(violation.getMessageTemplate());
    System.out.println(violation.getMessage());
}
```

In this example, a `@Size` violation has the template `{order.code.size}`; the `getMessage()` string depends on the locale used by the interpolator. Do not assert translated strings when a test cannot fix the locale.

## 6. Where is the locale decided?

### 6.1. Pure Jakarta Validation

Per the standard algorithm, if you call directly:

```java
var factory = jakarta.validation.Validation
        .buildDefaultValidatorFactory();
var validator = factory.getValidator();
```

then `Locale.getDefault()` is used by default when no locale is explicitly passed. There is no `locale` parameter on `Validator#validate(...)`; the locale is chosen by `MessageInterpolator` at message creation time, not by the `validate(...)` method.

The `jakarta.validation.MessageInterpolator` interface declares two overloads:

```java
String interpolate(
        String messageTemplate,
        MessageInterpolator.Context context);

String interpolate(
        String messageTemplate,
        MessageInterpolator.Context context,
        java.util.Locale locale);
```

`Context` provides `getConstraintDescriptor()` to read annotation metadata and `getValidatedValue()` to access the value being validated. The method taking `Locale` lets a wrapper specify the language for each interpolation call. Implementations must be **thread-safe** because they can be shared across multiple validators and requests.

### 6.2. Spring MVC and Accept-Language

Spring MVC uses `LocaleResolver` to determine the request locale; for example, with a header-based resolver, `Accept-Language: vi` results in a Vietnamese `Locale` in `LocaleContextHolder`. When using a standard Spring-configured `LocalValidatorFactoryBean`, `LocaleContextMessageInterpolator` wraps the provider's interpolator and passes the current locale.

Overall flow:

```text
HTTP Accept-Language
    -> Spring LocaleResolver
    -> LocaleContextHolder
    -> LocaleContextMessageInterpolator
    -> provider MessageInterpolator (passed Locale)
    -> ConstraintViolation#getMessage()
```

Do not call `Locale.setDefault(...)` in a controller to change the language per request: it mutates shared JVM state, easily causing language mix-ups across concurrent requests. If you use validation in a scheduled job/message listener, explicitly set up the locale for that execution path; do not assume an HTTP context exists.

## 7. Integrating Spring MessageSource with Bean Validation

Many Spring Boot applications already have:

```text
src/main/resources/messages.properties
src/main/resources/messages_vi.properties
```

Spring Boot normally auto-configures `MessageSource` for the `messages` basename when it finds the base bundle `messages.properties` (changeable via `spring.messages.basename`). Meanwhile, **Jakarta Bean Validation** looks up `ValidationMessages.properties` by default. Changing `spring.messages.basename` alone does not guarantee that every `@Size(message="{...}")` will use the Bean Validation i18n files in all configurations.

If you want to share Spring's `MessageSource`, you can configure `LocalValidatorFactoryBean#setValidationMessageSource(...)`. Example **replacing** the `ValidationMessages`-based default path in an application with `messages.properties`:

```java
package com.example.interpolation;

import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationMessageSourceConfig {

    @Bean
    public LocalValidatorFactoryBean validator(MessageSource messageSource) {
        LocalValidatorFactoryBean factory =
                new LocalValidatorFactoryBean();
        factory.setValidationMessageSource(messageSource);
        return factory;
    }
}
```

This snippet is an **alternative configuration option** and does not need to be added when running the example in sections 4–5. If you apply it, move your custom keys to the corresponding `messages*.properties` bundles, verify which validator MVC actually uses, and re-test `Accept-Language`. To avoid losing provider default message fallback, `MessageSource` should allow returning an unfound key; do not enable `useCodeAsDefaultMessage` for this source.

`LocalValidatorFactoryBean` also has `setMessageInterpolator(...)` to plug in a custom interpolator. Per the Spring API, **do not configure both `setValidationMessageSource(...)` and `setMessageInterpolator(...)` on the same factory** because they are two ways of choosing the interpolation mechanism. If you need both special behavior and Spring's translation source, build/decorate an appropriate interpolator rather than overwriting one setter with the other.

A practical operational rule is to standardize on **one canonical key source** for validation messages, clearly define how the locale is selected, and test the API with at least two locales.

## 8. When do you need to write a custom MessageInterpolator?

Normally you **do not need** to rewrite the standard interpolation algorithm. Prefer:

1. Using `message = "{custom.key}"` and adding language bundles if you only want to change messages.
2. Using `setValidationMessageSource` if you need to reuse Spring `MessageSource`.
3. Customizing `LocaleResolver` or selecting the locale in background tasks if you only want to control the language.
4. Creating a custom `MessageInterpolator` only when you have a special policy for locale, context data, or translation source selection that built-in capabilities cannot satisfy.

With pure Jakarta Validation, a safe way to enforce a locale in a dedicated validator factory is to **wrap the standard interpolator**, delegating interpolation to it. Example standalone file `FixedLocaleInterpolator.java` (must be imported into a project with Jakarta Validation):

```java
package com.example.interpolation;

import jakarta.validation.MessageInterpolator;
import java.util.Locale;
import java.util.Objects;

public final class FixedLocaleInterpolator implements MessageInterpolator {
    private final MessageInterpolator delegate;
    private final Locale fixedLocale;

    public FixedLocaleInterpolator(
            MessageInterpolator delegate,
            Locale fixedLocale) {
        this.delegate = Objects.requireNonNull(delegate);
        this.fixedLocale = Objects.requireNonNull(fixedLocale);
    }

    @Override
    public String interpolate(String template, Context context) {
        return delegate.interpolate(template, context, fixedLocale);
    }

    @Override
    public String interpolate(
            String template, Context context, Locale locale) {
        return delegate.interpolate(template, context, locale);
    }
}
```

How to register it (bootstrap API illustration, not a replacement for Spring MVC HTTP configuration):

```java
var configuration = jakarta.validation.Validation
        .byDefaultProvider().configure();
var defaultInterpolator = configuration.getDefaultMessageInterpolator();

try (var factory = configuration.messageInterpolator(
        new FixedLocaleInterpolator(
                defaultInterpolator, java.util.Locale.forLanguageTag("vi")))
        .buildValidatorFactory()) {

    var validator = factory.getValidator();
    // validator.validate(...) uses the Vietnamese locale in the overload without Locale.
}
```

Avoid the trap of creating an interpolator wrapper whose `interpolate(...)` calls itself infinitely, or rebuilding a new `ValidatorFactory` on every interpolation. Initialize a factory suited to the application lifecycle; `ValidatorFactory` must be closed when no longer in use in a manual bootstrap path. Do not store mutable per-request locale state in a field of a singleton interpolator.

For multilingual applications, `FixedLocaleInterpolator` is only an illustration of delegation; you should choose the locale per request or per job instead of fixing one language system-wide.

## 9. EL, message parameters, and advanced customization

### 9.1. How EL differs from bundle placeholders

The `{min}` syntax is a message parameter; the `${...}` syntax is **Jakarta Expression Language**. With EL, the standard context can provide:

- Constraint annotation attributes, such as `min`, `max`, and `inclusive`.
- `validatedValue` (the value being validated).
- `formatter` for locale-dependent formatting, such as number formatting.

Example illustrating a descriptor on `@DecimalMin`:

```java
@DecimalMin(
    value = "10",
    inclusive = false,
    message = "Value must be ${inclusive ? 'greater than or equal to' : 'greater than'} {value}"
)
private java.math.BigDecimal amount;
```

With `inclusive = false`, the expected interpolated result is `"Value must be greater than 10"` if the provider supports EL and the feature level is enabled for this expression. `{value}` comes from the `@DecimalMin` attribute, while `${inclusive ? ...}` is evaluated by EL.

**Do not depend on EL** when the environment lacks a suitable implementation. Hibernate Validator includes `ParameterMessageInterpolator`, which supports parameters but **does not evaluate EL**; `${...}` expressions may remain untouched. In many situations, bundle keys + `{min}`/`{max}` are sufficient, simpler, and easier to internationalize.

### 9.2. Messages created via ConstraintValidatorContext

Inside a custom constraint, you can call:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        "{order.code.custom.invalid}")
    .addConstraintViolation();
return false;
```

The descriptor passed to `buildConstraintViolationWithTemplate(...)` is still processed through message interpolation when the constraint is violated. If you use Hibernate Validator, the `HibernateConstraintValidatorContext#addMessageParameter(...)` extension lets you attach additional `{name}` parameters. `addExpressionVariable(...)` is a separate path, intended for EL `${name}` when EL features are enabled.

Hibernate Validator 8.x restricts EL levels by context: custom violations created manually via `ConstraintValidatorContext` **disable EL by default**; to use EL, you must explicitly enable it on the extension API with an appropriate level. Levels such as `NONE`, `VARIABLES`, `BEAN_PROPERTIES`, and `BEAN_METHODS` grant different permissions. In particular, do not enable calling methods on beans unless there is a clear need.

**Security:** Never concatenate user-supplied strings directly into a message template that may be passed through EL. Use fixed message keys and pass data through parameters/variables designed for that purpose by the API. Also avoid exposing sensitive data from `validatedValue` in errors returned to clients.

## 10. Common errors and diagnostics

| Symptom | Common cause | What to check |
| --- | --- | --- |
| API returns `{order.code.size}` literally | Wrong key name, missing bundle, wrong basename/classpath | Check `ValidationMessages*.properties` and `message="{...}"` syntax |
| `{min}`/`{max}` not replaced | No matching attribute; wrong descriptor or custom logic | Check the annotation and actual template from `getMessageTemplate()` |
| Always returns English | Locale not passed, resolver configured differently than expected, `_vi` file missing | Test with `Accept-Language`, check locale, resource bundle, and validator |
| App has `messages_vi.properties` but Bean Validation does not translate | Confusing `MessageSource` with `ValidationMessages` | Use the standard Jakarta bundle or configure `setValidationMessageSource(...)` |
| EL appears literally as `${...}` | EL missing/disabled, invalid expression, or using `ParameterMessageInterpolator` | Check provider, EL implementation, and feature level |
| Message shows wrong boundary numbers | Misunderstanding `{min}`, `{max}` substitution or annotation has different values | Inspect `ConstraintDescriptor#getAttributes()` metadata |
| Wrong translations across concurrent requests | Calling `Locale.setDefault(...)` per request or interpolator holding mutable locale | Use `LocaleResolver`/`LocaleContextHolder`, keep interpolator thread-safe |
| Flaky message tests | Tests rely on JVM locale, violation order, or unfixed fallback | Choose locale explicitly and assert errors with deterministic path/constraint |
| HTTP returns JSON/binding format error before validation | Jackson could not parse input into DTO | Distinguish the deserialization step from constraint validation |

Practical guidelines:

- Use **clearly namespaced keys**, such as `order.code.size`, to avoid collisions with messages from other modules.
- Provide a default bundle and per-locale bundles; check for missing keys, placeholders, and fallbacks in CI.
- Keep templates concise and accurately reflecting the business rule; do not put exception stack traces, internal details, or sensitive values into messages.
- Inspect both `getMessageTemplate()` and `getMessage()` when debugging; they help separate message selection errors from interpolation errors.
- In real i18n, avoid building complex sentences by concatenating small word fragments when language grammars differ; select complete messages per locale.
- To standardize APIs, return stable error codes (such as `ORDER_CODE_SIZE`) alongside user-facing translations instead of forcing clients to parse message strings.
- Test at real boundaries: HTTP uses the request locale; background processing uses the chosen locale; plain Java tests use an explicitly configured validator factory.
- When upgrading Spring/Hibernate Validator, re-run locale and EL tests because EL capability policies or message source integration may change across versions.

## 11. Implementation checklist

1. Identify the constraint, violation condition, and desired message content.
2. Declare `message = "{my.key}"`; place the key and translations into the bundle matching the mechanism your validator uses.
3. If the message needs annotation values, use `{min}`/`{max}`/corresponding attributes; check parameter resolution order.
4. Configure and test `Locale` for the appropriate context: HTTP, background job, or plain Java.
5. Use `@Valid`/`@Validated` at the appropriate trigger point and map violations to a consistent response.
6. Only add a custom `MessageInterpolator`/EL when necessary; delegate to the standard algorithm and maintain thread safety.
7. Test the template, translated messages, locale fallback, missing keys, and invalid input cases.

**Conclusion:** `MessageInterpolator` is the bridge from a Bean Validation **message template** to a **locale-interpolated error message**. Understanding the order bundle → annotation attributes → EL, distinguishing `ValidationMessages` from Spring `MessageSource`, and knowing where the locale comes from in Spring MVC will keep your messages accurate, localizable, and easy to test.

## References

- [Jakarta Validation 3.1 — Message interpolation, `6.3](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#message-interpolation)
- [Hibernate Validator 8 — Interpolating constraint error messages](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-message-interpolation)
- [Spring Framework — LocalValidatorFactoryBean API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html)
