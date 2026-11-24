# Constraint Parameters in Messages and Expression Interpolation

## 1. Goal and Real-World Problem

A Spring MVC API accepting JSON has the following rules:

- `displayName` must contain between 3 and 8 characters.
- `quantity` must be at least 2.
- `tag` must be at least 4 characters long; on error, we want to report the **actual character count**.
- Users can receive messages in English or Vietnamese.

You should not write separate hardcoded messages like “Name must be 3 to 8 characters” and “Name must be 4 to 10 characters” every time a constraint changes. Jakarta Validation supports **message interpolation** using structured components:

```java
@Size(min = 3, max = 8,
      message = "{order.name.size}")
private String displayName;
```

```properties
order.name.size=Name must contain between {min} and {max} characters
```

On violation, the message key `{order.name.size}` is resolved through the bundle, while `{min}`/`{max}` are pulled from `@Size`'s attributes. Result:

```text
Name must contain between 3 and 8 characters
```

For more complex cases, a template can use Jakarta Expression Language:

```text
At least {value} item${value > 1 ? 's' : ''} required
```

or **dynamic parameters** added inside a `ConstraintValidator`.

This lesson explains:
1. How message descriptors/keys, constraint attribute parameters, dynamic parameters, and EL differ.
2. In what order Jakarta Validation interpolates, and how it handles escaping and bundles.
3. How Spring Boot `MessageSource` integrates with Jakarta Validator for language selection.
4. Custom constraints adding `{actual}` with Hibernate Validator.
5. How to use `getMessage()`, `getMessageTemplate()`, `ConstraintDescriptor`, and return HTTP errors.
6. EL safety boundaries, testing `en`/`vi`, and common pitfalls.

Example scope: Java 17+, Spring Framework 6.2.x, Spring Boot 3.5.x, Jakarta Validation 3.x, and Hibernate Validator 8.x. The `HibernateConstraintValidatorContext` portion is a **Hibernate Validator-specific API**, not a required API across all Jakarta Validation providers.

## 2. Distinguishing Three Kinds of Placeholders

| Kind | Syntax | Value Source | Example |
| --- | --- | --- | --- |
| Message key | `{order.name.size}` | Locale bundle file | `messages_vi.properties` |
| Constraint parameter | `{min}`, `{max}`, `{value}` | Annotation attributes | `@Size(min=3,max=8)` |
| EL expression | `${validatedValue}`, `${value > 1 ? 's' : ''}` | EL context/logic | Input value, ternary |
| Dynamic message parameter (Hibernate) | `{actual}` | `addMessageParameter("actual", n)` | Actual length |
| Dynamic EL variable (Hibernate) | `${actual}` | `addExpressionVariable("actual", n)` | Used when EL is enabled |
| Spring `MessageFormat` argument | `{0}`, `{1}` | `MessageSource.getMessage(key,args,locale)` | Not a constraint attribute |

Easy-to-miss points:
- `@Min(value=2)` has `{value}` equal to the **threshold 2**, not the current input `1`.
- `@Size(min=3,max=8)` gets `{min}` and `{max}` from annotation metadata.
- `${validatedValue}` is the **value currently being validated** in EL, which may contain sensitive data.
- `{actual}` is a custom name we create in our Hibernate validator, not something that exists on every constraint by default.
- `@Valid` is a cascade/validation directive and **does not** have its own `{min}` parameter.

## 3. Interpolating Annotation Attributes: `{min}`, `{max}`, `{value}`

### 3.1. `@Size`

```java
@Size(min = 3, max = 8,
      message = "Length must be between {min} and {max}")
String name;
```

With `"AB"`, the interpolated message is:

```text
Length must be between 3 and 8
```

The caller does not pass `3` and `8` into a format function. The provider reads them directly from `@Size`'s descriptor. If you later change `min = 4` and `max = 10`, the same message template automatically produces `4`/`10`.

### 3.2. `@Min`

```java
@Min(value = 2,
     message = "Quantity must be at least {value}")
int quantity;
```

Input `quantity = 1` triggers a violation:

```text
Quantity must be at least 2
```

Here `{value}` is the `value()` attribute of the `@Min` annotation. To mention the invalid input value, consider `${validatedValue}` (with the data-exposure caveats noted below).

### 3.3. Putting a Key and Template in the Annotation

```java
@Size(min = 3, max = 8,
      message = "{order.name.size}")
String displayName;
```

`@Size.message` holds a **key**, not the final sentence. The bundle contains:

```properties
order.name.size=Name must contain between {min} and {max} characters
```

Once the key is found, the provider proceeds to resolve constraint placeholders. Another service can reuse the same resource key with different annotation metadata; the translation remains reusable as long as the needed attributes exist.

### 3.4. Do Not Use `{min}` on a Constraint Without `min()`

For example, `@NotBlank` has no `min()` attribute. If `@NotBlank`'s message contains `{min}` without a matching resource key or custom parameter, `{min}` may remain uninterpolated.

Read the annotation's API. For a custom constraint, you can declare `int min() default 4;` and reference `{min}` in the message template.

## 4. Default Order of Jakarta Validation Message Interpolation

In essence, the provider follows the steps in the Jakarta Validation specification:

1. **User resource bundle:** searches `{key}` expressions in the application's resource bundle, typically `ValidationMessages*.properties` when bootstrapping a plain Jakarta Validator. If the replacement still contains keys, it can resolve recursively.
2. **Provider resource bundle:** searches default keys for Jakarta built-in constraints, such as `jakarta.validation.constraints.Size.message`, in the provider-supplied bundle.
3. **Constraint attributes:** substitutes remaining placeholders matching annotation member names such as `{min}`, `{max}`, `{value}`.
4. **Jakarta EL:** evaluates `${expression}` segments if an EL implementation and feature level permit it.

User and standard bundle lookups can repeat per the spec algorithm; the outline above is a mental model of the main steps, not an implementation to mimic with regexes.

Concrete example:

```text
Constraint descriptor:
  {order.name.size}

Lookup in application bundle:
  Name must contain between {min} and {max} characters

Read @Size attributes:
  min = 3, max = 8

Interpolate constraint parameters:
  Name must contain between 3 and 8 characters

No remaining EL expression:
  Name must contain between 3 and 8 characters
```

**Important:** Message parameter interpolation happens before EL. Avoid confusing `${value}` with printing the threshold: because `{value}` sits inside the expression, it can be replaced first, leaving a stray `$`. If you only want the threshold, use `{value}`; if you want conditional logic, use an expression like `${value > 1 ? 's' : ''}`.

### 4.1. Bundle Keys Can Be Nested

```properties
field.displayName=Display name
order.name.size={field.displayName} must contain {min} to {max} characters
```

The second key can reference the first key, and annotation attributes are interpolated afterward. Keep nesting reasonable; overly complex recursive chains invite key collisions and are hard to test.

### 4.2. Avoid Collisions Between Resource Keys and Attribute Names

Do not define generic resource keys:

```properties
min=minimum
max=maximum
value=some-value
```

Because bundles are searched first, these values can accidentally replace constraint attributes in a message. Use namespaced keys: `order.name.size`, `signup.age.minimum`, `profile.email.required`. Reserve `min`/`max`/`value` for annotation metadata.

### 4.3. Fallback and Missing Keys

When a key is missing from a bundle, the provider may continue searching the provider bundle; if still unfound, the unresolved key can remain in the message. If a response returns literal `{order.name.size}`, check:
- Resource bundle filename.
- `MessageSource` basename.
- Encoding.
- Locale.
- Whether the execution path actually uses Jakarta `MessageInterpolator`.
- Whether the key has a typo or collides with another term.

Never treat a message still containing curly braces as finished localization.

## 5. Multilingual Support: `ValidationMessages.properties` and `messages.properties`

### 5.1. Jakarta Validation Project Independent of Spring

Under the standard convention, you can declare:

```text
src/main/resources/
├── ValidationMessages.properties
├── ValidationMessages_en.properties
├── ValidationMessages_vi.properties
└── ValidationMessages_vi_VN.properties
```

Example:

```properties
# ValidationMessages.properties
order.name.size=Name must contain {min} to {max} characters
```

```properties
# ValidationMessages_vi.properties
order.name.size=Tên phải có từ {min} đến {max} ký tự
```

Without a custom locale resolver, the provider typically relies on the JVM default locale. A Spring MVC application may determine locale differently because requests carry `Accept-Language` and Spring uses `LocaleContextHolder`.

### 5.2. Spring Boot 3.x `MessageSource` Integration

Spring Boot uses the application's `MessageSource` to resolve message parameters in constraint templates, then lets the default Bean Validation interpolator handle the remaining steps. Consequently, Boot apps usually use:

```text
src/main/resources/
├── messages.properties
└── messages_vi.properties
```

Under Boot's convention, **the base file `messages.properties` should exist** so the message source auto-configures. `messages_vi.properties` provides Vietnamese translations; `messages.properties` provides fallback.

```properties
# application.properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
```

Spring `MessageSource` and Jakarta `MessageInterpolator` are two separate APIs. Boot's integration does not mean `{min}` is replaced by positional `{0}` from Java `MessageFormat`. Keep `{min}`, `{max}`, `{value}` style templates for Jakarta constraints.

### 5.3. Direct Distinction Between the Two APIs

Spring `MessageSource`:

```java
String message = messageSource.getMessage(
        "order.created",
        new Object[] {42},
        Locale.forLanguageTag("vi"));
```

With resource text `Đã tạo đơn {0}`, `{0}` is a `MessageFormat` positional argument.

Jakarta `MessageInterpolator`:

```java
String message = interpolator.interpolate(
        messageTemplate,
        constraintContext,
        Locale.forLanguageTag("vi"));
```

This is an **illustrative fragment**: `interpolator`, `messageTemplate`, and `constraintContext` are supplied by bootstrap/validation code, not built-in controller variables. The interpolator uses the constraint descriptor and bundle system to resolve `{min}` and `${...}`. Do not merge both mechanisms into a manual `String.replace(...)`.

### 5.4. Per-Request HTTP Locale

With proper default Spring MVC configuration:
- `Accept-Language: en` → English message (base bundle or locale bundle).
- `Accept-Language: vi` → message from `messages_vi.properties`.
- `Accept-Language: vi-VN` → can search `messages_vi_VN.properties`, then `messages_vi.properties`, then fallback.
- Unsupported locale → appropriate base/provider fallback.

Spring uses `LocaleContextHolder` and `LocaleContextMessageInterpolator` to tie the managed locale to the provider. If the app replaces `LocaleResolver`, `MessageSource`, or calls `Validation.buildDefaultValidatorFactory()` directly outside Spring, re-verify locale resolution.

Messages with Vietnamese diacritics must be saved in the right encoding and packaged onto the classpath. Do not rely on the CI machine's locale when tests can specify locales explicitly.

## 6. EL Expressions: Conditionals, Validated Value, and Formatter

Jakarta EL allows `${...}` expressions when supported by the provider. Available variables/context objects include:

| Variable/Object | Meaning | Example |
| --- | --- | --- |
| `min` / `max` / `value` | Annotation attributes | `${value > 1 ? 's' : ''}` |
| `validatedValue` | Value currently being validated | `${validatedValue}` |
| `formatter` | Locale-aware formatting helper | `${formatter.format('%.2f', validatedValue)}` |
| Custom EL variable | Added via provider-specific API | `${actual}` |

### 6.1. Singular/Plural with a Constraint Attribute

```java
@Min(
    value = 2,
    message = "At least {value} item${value > 1 ? 's' : ''} required"
)
int quantity;
```

When `quantity=1`, the rule requires at least 2 and the message can be:

```text
At least 2 items required
```

`{value}` → `2`, and `${value > 1 ? 's' : ''}` → `s`. The EL expression references the **`value` attribute**, not `quantity`.

For languages with complex pluralization rules, do not cram all pluralization logic into an EL ternary; ICU `MessageFormat` or frontend i18n may be a better fit.

### 6.2. `${validatedValue}`

```java
@Size(min = 3, max = 8,
      message = "Value ${validatedValue} must have {min}..{max} chars")
String publicTag;
```

If `publicTag="AB"`, you can get `Value AB must have 3..8 chars`. This is a **technical illustration**, not a pattern to use for passwords, tokens, emails, or private data.

In production APIs, returning field + error code + limits is generally safer than returning raw `validatedValue`. Even when the interpolator handles escaping, rejected data can still leak in responses or logs.

### 6.3. `formatter`

```java
@DecimalMax(
    value = "100.00",
    message = "Actual ${formatter.format('%.2f', validatedValue)} exceeds {value}"
)
BigDecimal amount;
```

This is an illustrative fragment. Given `120.567`, a locale using decimal dots may format `120.57`, whereas a locale using decimal commas may show `120,57`. Do not assume one identical stdout across every locale.

### 6.4. EL Is Not Just Another `{...}` Substitution

`{validatedValue}` has no special meaning equivalent to `${validatedValue}`. Likewise, if a custom validator calls `addExpressionVariable("actual", 2)`, the placeholder is `${actual}` **and** requires EL to be enabled, unlike `addMessageParameter("actual", 2)` + `{actual}`.

## 7. Escaping: Counting Syntax Layers Carefully

According to Hibernate Validator, message descriptors use:

| Descriptor Syntax | Result |
| --- | --- |
| `\{` | Literal `{` character |
| `\}` | Literal `}` character |
| `\$` | Literal `$` character |
| `\\` | Literal `\` character |

A message string may pass through **two layers**: a Java string literal or `.properties` loader, and then the message interpolator. Therefore, the number of backslashes you type **in source code** can be higher than what the interpolator sees.

Java source:

```java
String template = "Use \\{min\\} literally";
```

The runtime string contains `\{min\}` so the interpolator does not substitute `min`. In `.properties`, to pass a backslash through the properties parser, you typically write:

```properties
example.literal=Use \\{min\\} literally
```

Test the actual message after loading the file; `MessageSource`/`MessageFormat` settings can add another processing layer. Do not mechanically copy Java string escaping into `.properties` files.

## 8. Custom Constraints with Dynamic Parameters

### 8.1. Why Static Attributes Are Not Enough

Suppose the rule is “tag must be at least 4 characters long”. `{min}` comes from the annotation:

```java
@MinTextLength(min = 4)
String tag;
```

However, when `tag="AB"`, the number **2** is not on the annotation. We must measure `value.length()` inside the validator and pass it into the message.

Hibernate Validator extends Jakarta's `ConstraintValidatorContext` with `HibernateConstraintValidatorContext`, offering `addMessageParameter`:

```java
HibernateConstraintValidatorContext hv =
        context.unwrap(HibernateConstraintValidatorContext.class);

hv.disableDefaultConstraintViolation();
hv.addMessageParameter("actual", value.length())
  .buildConstraintViolationWithTemplate("{order.tag.min}")
  .addConstraintViolation();
```

In the bundle:

```properties
order.tag.min=Tag must have at least {min} characters, actual {actual}
```

Result with `min=4` and a 2-character input:

```text
Tag must have at least 4 characters, actual 2
```

- `{min}`: static `min()` attribute of `@MinTextLength`.
- `{actual}`: dynamic parameter added during `isValid()`.
- `{order.tag.min}`: bundle key.

### 8.2. `addExpressionVariable` Is an Alternative Path

```java
hv.addExpressionVariable("actual", value.length());
```

This case uses `${actual}` with EL. When you only need to print the number `2`, **prefer `addMessageParameter`** because it is simpler and does not require enabling EL for custom violations.

### 8.3. Provider-Specific Scope

`HibernateConstraintValidatorContext` and `addMessageParameter` are Hibernate Validator-specific APIs. If you switch to another Jakarta Validation provider, custom validators must be adjusted. Standard annotation attributes like `{min}` remain portable per the specification.

## 9. EL Feature Levels and Preventing Expression Injection

Hibernate Validator 8.x lets you configure `ExpressionLanguageFeatureLevel`:

| Level | Capability |
| --- | --- |
| `NONE` | Disables Jakarta EL interpolation |
| `VARIABLES` | Injected EL variables, resources, and formatter |
| `BEAN_PROPERTIES` | Adds ability to read bean properties |
| `BEAN_METHODS` | Adds ability to invoke methods; broad scope, high risk |

**Hibernate Validator 8.x defaults:**
- Constraint messages declared on annotations use `BEAN_PROPERTIES`.
- Custom violations created via `ConstraintValidatorContext` have **EL disabled by default**.
- When a custom violation needs EL, Hibernate provides `enableExpressionLanguage()` on the builder and overloads to pick a feature level.

Related provider properties:

```properties
hibernate.validator.constraint_expression_language_feature_level=bean-properties
hibernate.validator.custom_violation_expression_language_feature_level=none
```

These are **Hibernate Validator provider properties**; do not assume Spring Boot binds them from `application.properties` the same way as Boot's own properties. Configure them via Hibernate Validator bootstrap or Boot's `ValidationConfigurationCustomizer`, and verify with tests.

Never enable `BEAN_METHODS` just to render a number in a message. Never concatenate user input directly into an EL message template:

```java
String unsafe = "Invalid: " + userText;
context.buildConstraintViolationWithTemplate(unsafe)
       .addConstraintViolation();
```

The snippet above is an **anti-pattern**: user input may contain message/EL syntax and affect interpolation if features are enabled. Use a fixed key, pass values through properly escaped parameters, and never leak sensitive data.

### 9.1. `ParameterMessageInterpolator` Does Not Support EL

Hibernate Validator provides `org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator` to interpolate parameters **without Jakarta EL**. With this interpolator, `${...}` expressions may not be evaluated, including some built-in messages that use EL. When testing messages with EL, verify which provider and interpolator are active.

### 9.2. Do Not Treat EL as a “General-Purpose Template Engine”

Message interpolation is designed to explain constraint violations, not execute scripts from databases or clients. Use message keys and constraint attributes for most scenarios; leave complex linguistic logic to a dedicated i18n system.

## 10. Runnable Project: Spring Boot 3.5.6, Java 17, en/vi

The application includes:
- Request DTO using `@NotBlank`, `@Size`, `@Min`, and custom `@MinTextLength`.
- `messages.properties` (English fallback) and `messages_vi.properties`.
- `@RestControllerAdvice` returning a list of fields and messages.
- `MockMvc` tests checking English/Vietnamese and dynamic parameters.
- Jakarta `Validator` test verifying `getMessageTemplate()` remains the original key.

### 10.1. Directory Tree

```text
constraint-message-demo/
├── pom.xml
├── src/main/
│   ├── java/demo/messages/
│   │   ├── MessageDemoApplication.java
│   │   ├── OrderRequest.java
│   │   ├── MinTextLength.java
│   │   ├── MinTextLengthValidator.java
│   │   ├── OrderController.java
│   │   └── ErrorAdvice.java
│   └── resources/
│       ├── application.properties
│       ├── messages.properties
│       └── messages_vi.properties
└── src/test/java/demo/messages/
    └── MessageInterpolationTest.java
```

### 10.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>constraint-message-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
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

The Spring Boot parent manages dependency versions. `spring-boot-starter-validation` supplies the appropriate Bean Validation provider, usually Hibernate Validator. The application does not create an extra `ValidatorFactory` per request.

### 10.3. `application.properties`

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
```

### 10.4. `messages.properties` (English fallback)

```properties
order.name.required=Name is required
order.name.size=Name must contain between {min} and {max} characters
order.quantity.min=At least {value} item${value > 1 ? 's' : ''} required
order.tag.required=Tag is required
order.tag.min=Tag must have at least {min} characters, actual {actual}
```

### 10.5. `messages_vi.properties`

```properties
order.name.required=Vui lòng nhập tên
order.name.size=Tên phải có từ {min} đến {max} ký tự
order.quantity.min=Số lượng tối thiểu là {value}
order.tag.required=Vui lòng nhập thẻ
order.tag.min=Thẻ phải có ít nhất {min} ký tự, thực tế {actual}
```

Vietnamese messages do not need EL for pluralization. The English file intentionally uses EL to illustrate the logic, not as a requirement that every translation include an expression.

### 10.6. `MessageDemoApplication.java`

```java
package demo.messages;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessageDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessageDemoApplication.class, args);
    }
}
```

### 10.7. `MinTextLength.java`

```java
package demo.messages;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Constraint(validatedBy = MinTextLengthValidator.class)
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
public @interface MinTextLength {
    String message() default "{order.tag.min}";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
    int min() default 4;
}
```

`@MinTextLength` has a `min` attribute, so the message bundle can use `{min}`. Annotation target `FIELD` allows the constraint on the field generated from a Java record component; target `PARAMETER` supports parameter contracts where appropriate.

### 10.8. `MinTextLengthValidator.java`

```java
package demo.messages;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import org.hibernate.validator.constraintvalidation.HibernateConstraintValidatorContext;

public class MinTextLengthValidator
        implements ConstraintValidator<MinTextLength, String> {

    private int min;

    @Override
    public void initialize(MinTextLength constraint) {
        min = constraint.min();
    }

    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        if (value == null) {
            // @NotBlank/@NotNull verifies presence if needed.
            return true;
        }

        int actual = value.length();
        if (actual >= min) {
            return true;
        }

        var hibernate = context.unwrap(
                HibernateConstraintValidatorContext.class);
        hibernate.disableDefaultConstraintViolation();
        hibernate.addMessageParameter("actual", actual)
                .buildConstraintViolationWithTemplate("{order.tag.min}")
                .addConstraintViolation();
        return false;
    }
}
```

`String.length()` counts UTF-16 code units, not necessarily the number of user-perceived grapheme clusters. If an application needs to count Unicode characters differently, adjust the implementation rule and test emojis/combining marks rather than silently equating `String.length()` with “visible character count”.

### 10.9. `OrderRequest.java`

```java
package demo.messages;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record OrderRequest(
        @NotBlank(message = "{order.name.required}")
        @Size(min = 3, max = 8,
              message = "{order.name.size}")
        String displayName,

        @Min(value = 2,
             message = "{order.quantity.min}")
        int quantity,

        @NotBlank(message = "{order.tag.required}")
        @MinTextLength(min = 4)
        String tag) {
}
```

If you need to distinguish “quantity missing” from “quantity equals 0”, use `Integer` + `@NotNull` in a real system. This demo uses primitive `int` to focus on `@Min` and the `{value}` message parameter.

### 10.10. `OrderController.java`

```java
package demo.messages;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @PostMapping
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody OrderRequest request) {
        return ResponseEntity.ok(Map.of(
                "accepted", true,
                "displayName", request.displayName()));
    }
}
```

`@Valid` on the request DTO triggers Bean Validation after Jackson decodes the JSON. The controller class does not need `@Validated` to validate DTO arguments. If the request is invalid, MVC may throw `MethodArgumentNotValidException` before `create` is called.

### 10.11. `ErrorAdvice.java`

```java
package demo.messages;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Comparator;
import java.util.Map;
import java.util.Objects;

@RestControllerAdvice
public class ErrorAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> invalid(
            MethodArgumentNotValidException exception) {

        var errors = exception.getBindingResult()
                .getFieldErrors().stream()
                .map(e -> Map.of(
                        "field", e.getField(),
                        "message", Objects.toString(
                                e.getDefaultMessage(), "")))
                .sorted(Comparator.comparing(e -> e.get("field")))
                .toList();

        return ResponseEntity.badRequest().body(Map.of("errors", errors));
    }
}
```

The handler returns the **interpolated message** without including `rejectedValue` or the entire object in the response. Malformed JSON can go through a different exception; do not lump parsing errors together with constraint violations.

### 10.12. `MessageInterpolationTest.java`

```java
package demo.messages;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MessageInterpolationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    Validator validator;

    private static String json(String name, int quantity, String tag) {
        return """
                {"displayName":"%s","quantity":%d,"tag":"%s"}
                """.formatted(name, quantity, tag);
    }

    private MockHttpServletRequestBuilder submit(Locale locale, String json) {
        return post("/api/orders")
                .locale(locale)
                .contentType(MediaType.APPLICATION_JSON)
                .content(json);
    }

    @Test
    void validRequestWorks() throws Exception {
        mvc.perform(submit(Locale.ENGLISH,
                json("Linh", 2, "ABCD")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }

    @Test
    void englishMinMaxAttributesWork() throws Exception {
        mvc.perform(submit(Locale.ENGLISH,
                json("AB", 2, "ABCD")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Name must contain between 3 and 8 characters"));
    }

    @Test
    void vietnameseMinMaxAttributesWork() throws Exception {
        mvc.perform(submit(Locale.forLanguageTag("vi"),
                json("AB", 2, "ABCD")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tên phải có từ 3 đến 8 ký tự"));
    }

    @Test
    void englishElPluralizationWorks() throws Exception {
        mvc.perform(submit(Locale.ENGLISH,
                json("Linh", 1, "ABCD")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("At least 2 items required"));
    }

    @Test
    void vietnameseQuantityWorks() throws Exception {
        mvc.perform(submit(Locale.forLanguageTag("vi"),
                json("Linh", 1, "ABCD")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Số lượng tối thiểu là 2"));
    }

    @Test
    void dynamicActualParameterEnglishWorks() throws Exception {
        mvc.perform(submit(Locale.ENGLISH,
                json("Linh", 2, "AB")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tag must have at least 4 characters, actual 2"));
    }

    @Test
    void dynamicActualParameterVietnameseWorks() throws Exception {
        mvc.perform(submit(Locale.forLanguageTag("vi"),
                json("Linh", 2, "AB")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Thẻ phải có ít nhất 4 ký tự, thực tế 2"));
    }

    @Test
    void notBlankMessageIsTranslated() throws Exception {
        // 4 whitespace characters: @Size still passes, @NotBlank fails.
        mvc.perform(submit(Locale.ENGLISH,
                json("    ", 2, "ABCD")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Name is required"));
    }

    @Test
    void templateAndDescriptorAreDifferentFromFinalMessage() {
        var violations = validator.validate(
                new OrderRequest("AB", 2, "ABCD"));

        assertEquals(1, violations.size());
        ConstraintViolation<OrderRequest> v =
                violations.iterator().next();

        assertEquals("{order.name.size}", v.getMessageTemplate());
        assertEquals("displayName",
                v.getPropertyPath().toString());
        assertEquals(3,
                v.getConstraintDescriptor().getAttributes().get("min"));
    }

    @Test
    void validObjectHasNoViolations() {
        assertTrue(validator.validate(
                new OrderRequest("Linh", 3, "ABCD")).isEmpty());
    }

    @Test
    void malformedJsonIsNotAConstraintViolation() throws Exception {
        mvc.perform(submit(Locale.ENGLISH, "{\"displayName\":"))
                .andExpect(status().isBadRequest());
    }
}
```

The project has **11 tests**. With Maven/JDK 17 and compatible dependencies, all assertions are expected to pass. This is a complete example for learners to run themselves; it does **not** claim tests were executed while authoring the lesson.

Run:

```bash
mvn test
```

Start the server:

```bash
mvn spring-boot:run
```

## 11. Trying the API with curl

### 11.1. Valid Request

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: en' \
  -d '{"displayName":"Linh","quantity":2,"tag":"ABCD"}'
```

Expected HTTP **200**:

```json
{"accepted":true,"displayName":"Linh"}
```

### 11.2. `@Size` in Vietnamese

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi' \
  -d '{"displayName":"AB","quantity":2,"tag":"ABCD"}'
```

Expected HTTP **400**, body contains:

```json
{
  "errors": [
    {
      "field": "displayName",
      "message": "Tên phải có từ 3 đến 8 ký tự"
    }
  ]
}
```

### 11.3. `@Min` in English with EL

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: en' \
  -d '{"displayName":"Linh","quantity":1,"tag":"ABCD"}'
```

Expected HTTP **400**, message `At least 2 items required`. The threshold `2` comes from the `@Min.value` attribute, not the `quantity=1` input.

### 11.4. Custom Parameter `{actual}`

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi' \
  -d '{"displayName":"Linh","quantity":2,"tag":"AB"}'
```

Expected HTTP **400**, message `Thẻ phải có ít nhất 4 ký tự, thực tế 2`. The number `4` comes from the annotation, while `2` is computed by the validator and passed via `addMessageParameter`.

## 12. `getMessageTemplate()`, `getMessage()`, and `ConstraintDescriptor`

When calling Jakarta Validator directly:

```java
Set<ConstraintViolation<OrderRequest>> violations =
        validator.validate(request);
```

with `OrderRequest.displayName="AB"`, the violation exposes:

- `getMessageTemplate()`: the `{order.name.size}` string declared on the annotation.
- `getMessage()`: the message interpolated by locale, e.g., `Name must contain between 3 and 8 characters`.
- `getPropertyPath()`: field path `displayName`.
- `getConstraintDescriptor().getAttributes().get("min")`: value `3`.
- `getInvalidValue()`: value `"AB"`, **which should not be returned or logged directly if it might contain private data**.

`getMessageTemplate()` helps diagnose missing keys; `getMessage()` is suitable for display. `ConstraintDescriptor` helps expose structured metadata, such as limits so the frontend can phrase errors itself.

In Spring MVC, when `@Valid @RequestBody` fails, `MethodArgumentNotValidException` carries `BindingResult` and `FieldError`. The message in `FieldError.getDefaultMessage()` is usually already interpolated; it is not the `ConstraintViolation` object itself.

A public API can choose a response such as:

```json
{
  "field": "displayName",
  "code": "order.name.size",
  "params": {"min": 3, "max": 8}
}
```

The frontend then looks up the locale. However, design error code mapping and data disclosure carefully; do not assume `getMessageTemplate()` is always a public business code safe to expose verbatim.

## 13. Customizing `MessageInterpolator` in Spring

Jakarta interface:

```java
public interface MessageInterpolator {
    String interpolate(String template, Context context);
    String interpolate(String template, Context context, Locale locale);
}
```

Spring Framework provides `LocalValidatorFactoryBean`, supporting `setValidationMessageSource(MessageSource)` and `setMessageInterpolator(MessageInterpolator)`. These are **two alternative configuration paths** and should not be set together on the same bean.

Conceptual plain Spring Framework example:

```java
@Bean
LocalValidatorFactoryBean validator(MessageSource source) {
    LocalValidatorFactoryBean bean = new LocalValidatorFactoryBean();
    bean.setValidationMessageSource(source);
    return bean;
}
```

This is a fragment requiring imports, wiring into MVC validator configuration, and bean lifecycle decisions. Do not add this bean to the sample Boot project in Section 10, because that project intentionally relies on Boot auto-configuration.

Spring Javadoc notes that a `MessageSource` used for constraint messages must support optional resolution—do not set `useCodeAsDefaultMessage=true`, which blocks fallback to provider messages. If you need a custom interpolator, prefer wrapping/delegating to the provider's default interpolator rather than rewriting interpolation with regexes.

### 13.1. Passing an Explicit Locale Outside a Request

In a service or CLI app without HTTP headers, you can call `MessageInterpolator#interpolate(template, context, locale)` or configure locale resolution on `ValidatorFactory` per provider. Never mutate `Locale.setDefault(...)` per request, as it is JVM-wide state and causes race conditions.

## 14. Common Pitfalls

| Symptom | Possible Cause | Diagnosis/Fix |
| --- | --- | --- |
| `{order.name.size}` appears verbatim in response | Wrong key, basename, locale, or bypassed interpolator | Check bundle/`MessageSource` |
| `{min}` is not replaced with a number | Wrong attribute, shadowed by a bundle key, or `String.format` outside provider | Inspect `ConstraintDescriptor#getAttributes()` |
| `{value}` mistaken for the input value | `value` is `@Min`'s attribute | Distinguish from `validatedValue` |
| `${validatedValue}` stays literal | Missing EL implementation, feature level off, or `ParameterMessageInterpolator` | Check provider/interpolator |
| English message despite `Accept-Language: vi` | Wrong locale resolver or `vi` bundle | Test locales in `MockMvc` |
| Garbled Vietnamese diacritics | Wrong encoding | Use UTF-8 in source and build/runtime |
| `{actual}` is not substituted | Custom validator didn't call `addMessageParameter` | Add message parameter with the exact name |
| `${actual}` is not substituted | `addExpressionVariable` not called or EL disabled | Align the two mechanisms |
| `${value}` turns into `$2` | Parameter placeholder substituted before EL | Use `{value}` or a conditional EL expression |
| Direct validation misses HTTP locale | No request context | Select locale when validating |
| `@NotBlank` does not run | Missing provider, annotation, or `@Valid` trigger | Check dependencies and controller |
| Returning raw `getInvalidValue()` | Can leak PII/passwords/tokens | Return field + code + limits |
| Concatenating user input into message template | Expression injection or broken interpolation | Use fixed templates and safe parameters |
| Enabling `BEAN_METHODS` for custom violations | Excessive EL execution surface | Keep `NONE`/`VARIABLES` |
| Confusing parsing with validation | JSON could not construct the object | Classify HTTP input errors separately |
| Checking only HTTP 400 status | Unknown root cause and locale | Assert exception type and message |
| Testing only English | Misses `vi` key/encoding/fallback bugs | Test all supported locales |

## 15. Checklist for Writing Multilingual Messages

1. Identify the annotation actually producing the violation and which attributes are available.
2. Use stable message keys like `order.name.size`, avoiding overly generic keys.
3. Create the base bundle `messages.properties` when using Spring Boot's message source convention.
4. Create locale bundle `messages_vi.properties` in UTF-8.
5. Preserve `{min}`/`{max}`/`{value}` in translations instead of replacing them with hardcoded numbers.
6. Understand the order: bundle lookup → attributes → EL.
7. Avoid `min`/`max`/`value` keys in resource bundles since they can shadow attributes.
8. For dynamic data, prefer `addMessageParameter` with a fixed template.
9. When EL is needed, verify provider, feature level, and security requirements.
10. Never use `validatedValue` to expose sensitive data.
11. Test at least `en`, `vi`, a fallback locale, and a missing key.
12. Assert both `getMessageTemplate()` and `getMessage()` programmatically if error codes need stability.
13. For controllers, use `MockMvc`/HTTP integration tests to verify real locale handling.
14. In error responses, separate validation failures from malformed JSON.
15. After upgrading Spring/Hibernate, re-run tests because default interpolation may change.

## 16. Practice Exercises

1. Change `@Size(min=3,max=8)` to `@Size(min=4,max=10)`; keep the bundle and verify the message updates automatically.
2. Swap the order of `{min}` and `{max}` in Vietnamese and explain why both values still substitute into the right places.
3. Try `@Min(value=1)` with input `0`; how does the singular/plural EL expression behave?
4. Delete `messages_vi.properties` and test fallback when sending `Accept-Language: vi`.
5. Point an annotation key to a nonexistent key; compare `getMessageTemplate()` and `getMessage()`.
6. Remove `addMessageParameter("actual", actual)` in the custom validator and observe the message.
7. Add `addExpressionVariable` to a custom violation without enabling EL. Explain how it differs from `addMessageParameter`.
8. Use `ParameterMessageInterpolator` in a separate test; is the pluralization expression still evaluated?
9. Add a `@DecimalMax` constraint on `BigDecimal`, use the EL formatter, and test multiple locales.
10. Add a test returning error codes/parameters instead of translated prose; verify no input values are leaked.
11. Rename message keys to `module.entity.field.rule` and reorganize the resource files.
12. Use a custom Spring `MessageSource` and verify fallback to default provider messages when a key is missing.
13. Write a test separating a malformed JSON parsing error from a `quantity=1` Bean Validation error.
14. Try escaping a literal `{min}` in Java and `.properties` to observe the two parser layers.
15. Add a nested request DTO using `@Valid` and create translations for constraints on the nested property.

**Remember:** Multilingual messages use **resource keys** to select phrasing, **constraint attributes** (`{min}`, `{max}`, `{value}`) to inject static thresholds, **dynamic parameters** to pass values computed during validation, and **EL** when conditional logic or formatting is needed. In Spring Boot, `MessageSource` helps look up `en`/`vi`, while Jakarta `MessageInterpolator` remains responsible for completing interpolation. Prefer simple, safe designs tested per locale.

## 17. Official References

- [Jakarta Validation 3.1 — Message interpolation](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html)
- [Hibernate Validator 8 — Chapter 4: Interpolating constraint error messages](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-message-interpolation)
- [Hibernate Validator 8 — EL feature levels and custom violations](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#section-expression-language-features)
- [Hibernate Validator 8 — `MessageParameterEscaping`](https://docs.hibernate.org/validator/8.0/api/org/hibernate/validator/messageinterpolation/MessageParameterEscaping.html)
- [Spring Boot 3.5 — Validation and MessageSource](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Framework 6.2 — `LocalValidatorFactoryBean`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework 6.2 — `LocaleContextMessageInterpolator`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/LocaleContextMessageInterpolator.html)
- [Spring Framework 6.2 — Spring MVC validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)