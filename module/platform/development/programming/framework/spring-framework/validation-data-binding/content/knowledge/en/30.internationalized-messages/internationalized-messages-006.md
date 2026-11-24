# ValidationMessages.properties and Bean Validation Message Templates

## 1. Goal: Separating Constraints from Message Text

In Jakarta Bean Validation, annotations such as `@NotBlank`, `@NotNull`, `@Size`, `@Min`, and `@Pattern` validate objects, parameters, and method return values. A single rule can apply across multiple languages, for example:

- Vietnamese: **Mã phải dài từ 3 đến 8 ký tự**.
- English: **Code length must be between 3 and 8 characters**.

Instead of hardcoding a fixed sentence in the annotation, declare a **message template** using a key in a resource bundle:

```java
@Size(min = 3, max = 8, message = "{app.code.size}")
private String code;
```

And create the files:

```text
src/main/resources/
├── ValidationMessages.properties
├── ValidationMessages_vi.properties
└── ValidationMessages_en.properties
```

Vietnamese example:

```properties
app.code.size=Mã phải dài từ {min} đến {max} ký tự
```

The Jakarta Bean Validation provider reads the message template, looks up the `app.code.size` key, selects the translation matching `Locale`, and substitutes `{min}`/`{max}` with the annotation's values.

**Distinguish:**

1. `{app.code.size}` is a **bundle key**.
2. `{min}`, `{max}`, `{value}` can be **constraint attributes** that get interpolated.
3. `ConstraintViolation#getMessageTemplate()` holds the original template.
4. `ConstraintViolation#getMessage()` holds the interpolated sentence.
5. Bean Validation's `ValidationMessages.properties` is **different from the default mechanism** of Spring `MessageSource`'s `messages.properties`.

## 2. Resource Bundle Structure

The standard base bundle name is `ValidationMessages`, with uppercase V and M. Standard files are placed **at the classpath root**, such as `src/main/resources/ValidationMessages_vi.properties` in Maven.

| Target Locale | Preferred Filename | Meaning |
| --- | --- | --- |
| `vi-VN` | `ValidationMessages_vi_VN.properties` if present | Vietnamese bundle for Vietnam |
| `vi` | `ValidationMessages_vi.properties` | General Vietnamese bundle |
| `en-US` | `ValidationMessages_en_US.properties` if present | English bundle for the US |
| `en` | `ValidationMessages_en.properties` | General English bundle |
| No locale-specific file | `ValidationMessages.properties` and `ResourceBundle` fallbacks | Fallback message |

Java `ResourceBundle` also applies candidate locale and fallback rules involving the JVM default locale. Therefore, check both the runtime locale and the files packaged in the artifact rather than inferring solely from filename suffixes.

You should provide a root `ValidationMessages.properties` containing fallback keys, especially for custom keys like `app.account.username.required`. The provider ships its own message bundle for standard constraints, but it does not know translations for custom keys.

### 2.1. Bilingual Example

```properties
# ValidationMessages_vi.properties, saved as UTF-8
app.username.required=Tên đăng nhập không được để trống
app.code.size=Mã phải dài từ {min} đến {max} ký tự
app.age.minimum=Tuổi phải từ {value} trở lên
```

```properties
# ValidationMessages_en.properties, saved as UTF-8
app.username.required=Username must not be blank
app.code.size=Code length must be between {min} and {max} characters
app.age.minimum=Age must be at least {value}
```

Key naming with an `app.` prefix helps avoid colliding with short attribute names like `min`, `max`, or `value`. Use UTF-8 and verify the files are actually packaged onto the classpath during build. Java 9+ supports UTF-8 for property resource bundles with compatibility rules; some providers/loaders have custom settings, so still test Vietnamese diacritics.

### 2.2. Do Not Mistake the File Path

Correct under the default convention:

```text
src/main/resources/ValidationMessages.properties
```

Unlike:

```text
src/main/resources/messages/ValidationMessages.properties
```

The second path will only be found if you customize the bundle locator or classpath configuration accordingly. The filename is not a Java package name.

## 3. Message Template and ConstraintViolation

Consider:

```java
@NotBlank(message = "{app.username.required}")
String username;
```

When the field is invalid, the provider produces a `ConstraintViolation<?>`:

| API | Example | Meaning |
| --- | --- | --- |
| `getMessageTemplate()` | `{app.username.required}` | Original descriptor string on the annotation |
| `getMessage()` | `Username must not be blank` | Interpolation result at validation time |
| `getPropertyPath()` | `username` | Location of the violation |
| `getConstraintDescriptor()` | Metadata of `@NotBlank` | Annotation, attributes, groups, etc. |
| `getInvalidValue()` | `"   "` | Rejected data, potentially sensitive |

Do not use `getMessageTemplate()` as the display text. Conversely, do not use `getMessage()` as a machine-readable code because it varies by locale, wording, and translation bundle.

In a REST API, you can construct an error DTO like:

```json
{
  "field": "username",
  "code": "USERNAME_REQUIRED",
  "message": "Username must not be blank"
}
```

This is an illustrative API contract; the business code `USERNAME_REQUIRED` is chosen by the application and does not have to match the interpolation key.

## 4. Jakarta Bean Validation Interpolation Algorithm

Jakarta Bean Validation 3.0 specifies the resolution order in section 6.3.1.1. Given descriptor `{app.code.size}`:

1. Search `{key}` parameters in the **user** resource bundle `ValidationMessages` for the locale; replace with the found value and continue **recursively** if the value itself contains parameters.
2. Look up remaining parameters in the Jakarta Bean Validation provider's **built-in** bundle. The provider step does not expand recursively like the user step.
3. If the provider step found replacements, re-run the user bundle lookup step; this ensures the user bundle takes precedence when keys overlap.
4. Substitute parameters matching **annotation attributes**, such as `{min}`, `{max}` of `@Size` or `{value}` of `@Min`.
5. Evaluate Jakarta Expression Language expressions of the form `${...}`, subject to the capabilities and limits of the interpolator/provider.

Example:

```text
{app.code.size}
  |
  v  look up ValidationMessages_vi.properties
Mã phải dài từ {min} đến {max} ký tự
  |
  v  substitute @Size(min=3,max=8)
Mã phải dài từ 3 đến 8 ký tự
```

**This is not Spring `MessageSource`'s `MessageFormat` algorithm.** Bean Validation combines bundle lookup, constraint attribute interpolation, and optional EL evaluation.

### 4.1. Application Bundle Precedence

Standard constraints like `@NotNull` usually have a default template:

```text
{jakarta.validation.constraints.NotNull.message}
```

Hibernate Validator ships built-in translations. You can override them in your application file:

```properties
# ValidationMessages_vi.properties
jakarta.validation.constraints.NotNull.message=Giá trị bắt buộc
```

Because user lookup runs before the provider bundle, this sentence takes precedence. However, it affects **every `@NotNull` using the default template**, not just one specific field.

To write a custom sentence for one property, declare:

```java
@NotNull(message = "{app.account.region.required}")
String region;
```

and define the corresponding key instead of overriding the system-wide built-in key.

### 4.2. Recursion in the User Bundle

You can reference another key:

```properties
app.username.required={app.common.required}
app.common.required=Value must not be blank
```

The user bundle lookup repeats recursively to yield the final sentence. However, do not create reference cycles like `a={b}`, `b={a}`; that adds no value and can cause unexpected behavior.

### 4.3. Avoiding Collisions with Attribute Names

If you define a bundle key named `min`, it can be resolved before `{min}` is replaced from the annotation attribute. For custom messages, prefer a namespace like `app.checkout.amount.minimum` instead of generic keys like `min` or `value`.

## 5. Constraint Attribute Interpolation

A literal message like:

```java
@Min(value = 18, message = "Tuổi phải từ {value} trở lên")
Integer age;
```

can produce **Tuổi phải từ 18 trở lên**, because `{value}` is an annotation attribute. However, this Vietnamese literal sentence is **not automatically multilingual**. Better:

```java
@Min(value = 18, message = "{app.age.minimum}")
Integer age;
```

with:

```properties
# Vietnamese
app.age.minimum=Tuổi phải từ {value} trở lên
```

```properties
# English
app.age.minimum=Age must be at least {value}
```

Similarly:

```java
@Size(min = 3, max = 8, message = "{app.code.size}")
String code;
```

The values `3` and `8` are declared on the annotation and should not be hardcoded into both bundle files if you want rules to be easy to update.

### Common Attributes

| Constraint | Placeholder | Example |
| --- | --- | --- |
| `@Min(18)` | `{value}` | `18` |
| `@Max(100)` | `{value}` | `100` |
| `@Size(min=3,max=8)` | `{min}`, `{max}` | `3`, `8` |
| `@DecimalMin(value="10.5")` | `{value}`, optionally combined with EL on `inclusive` | `10.5` |
| `@Pattern(regexp="...")` | `{regexp}` if truly needed | Regex, though displaying raw regex is rarely user-friendly |

Not all constraints share the same `min` or `value` attributes; inspect the metadata of the annotation you are using.

## 6. Message Expressions: `${...}` vs. `{...}`

Jakarta Bean Validation supports two interpolation styles:

- `{...}`: message parameter, bundle key, or constraint attribute.
- `${...}`: Jakarta Expression Language (EL).

Example:

```java
@DecimalMin(
    value = "10.5",
    inclusive = true,
    message = "Value must be greater than ${inclusive == true ? 'or equal to ' : ''}{value}"
)
BigDecimal amount;
```

This is an illustrative declaration; it requires importing `BigDecimal` and `@DecimalMin`. With `inclusive=true`, EL picks `"or equal to "`; `{value}` yields `10.5`. EL exposes standard names such as:

- Constraint attributes, e.g., `inclusive`.
- `validatedValue`: the value currently being validated.
- `formatter`: locale-aware formatting helper, e.g., `${formatter.format('%1$.2f', validatedValue)}`.

Per the specification, `{...}` parameter interpolation takes **precedence before** EL evaluation. Therefore, expressions containing names matching attributes should be tested in practice; do not assume every `${value}` survives unaltered to the EL stage.

EL may require a Jakarta EL implementation on the classpath. Hibernate Validator enforces safety restrictions and separate settings for EL in default constraint messages compared to violations built manually via `ConstraintValidatorContext`. Never build EL templates by concatenating client-supplied input.

## 7. Escaping Special Characters

In Jakarta Bean Validation message descriptors:

| Runtime Template Contains | Meaning |
| --- | --- |
| `\{` | Literal `{`, does not start a message parameter |
| `\}` | Literal `}` |
| `\$` | Literal `$`, does not start an EL expression |
| `\\` | Literal `\` |

**Distinguish multiple escaping layers:** Java string literals, `.properties` file syntax, and `MessageInterpolator` all process backslashes `\`. For example, if a runtime template needs `\{`, Java source must escape the backslash using Java rules; inside a `.properties` file, backslashes have their own escaping semantics. Write a small test for special literal characters rather than blindly copying backslash counts between layers without verification.

To keep things simple, keep the template itself as a key like `{app.reference.format}` and put friendly explanations in the bundle rather than embedding complex regexes or JSON in the descriptor.

## 8. Complete Runnable Example: Java 17 + Maven + Hibernate Validator 8

This lab creates an object with five errors, uses `ValidationMessages*.properties` for translation, and prints both `getMessageTemplate()` and `getMessage()`. No Spring context or HTTP server is needed.

**For deterministic output**, the example uses Hibernate Validator's `defaultLocale(...)` extension; this is a provider-specific API, not part of standard `jakarta.validation.Configuration<?>`. It builds separate factories for two locales to show language selection clearly.

### 8.1. Project Structure

```text
validation-messages-demo/
├── pom.xml
└── src/main/
    ├── java/demo/ValidationMessagesDemo.java
    └── resources/
        ├── ValidationMessages.properties
        ├── ValidationMessages_vi.properties
        └── ValidationMessages_en.properties
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>validation-messages-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.hibernate.validator</groupId>
      <artifactId>hibernate-validator</artifactId>
      <version>8.0.2.Final</version>
    </dependency>
    <dependency>
      <groupId>org.glassfish</groupId>
      <artifactId>jakarta.el</artifactId>
      <version>4.0.2</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Hibernate Validator is the provider; Jakarta EL supports EL interpolation. Java 17 lets us use a `record` to present constraints concisely.

### 8.3. ValidationMessages.properties (root fallback)

```properties
app.username.required=Username must not be blank
app.code.size=Code length must be between {min} and {max} characters
app.age.minimum=Age must be at least {value}
app.reference.format=Reference must have format ACCT-nnn
jakarta.validation.constraints.NotNull.message=Region must not be null
```

### 8.4. ValidationMessages_vi.properties

```properties
app.username.required=Tên đăng nhập không được để trống
app.code.size=Mã phải dài từ {min} đến {max} ký tự
app.age.minimum=Tuổi phải từ {value} trở lên
app.reference.format=Mã tham chiếu phải có dạng ACCT-nnn
jakarta.validation.constraints.NotNull.message=Khu vực không được để trống
```

### 8.5. ValidationMessages_en.properties

```properties
app.username.required=Username must not be blank
app.code.size=Code length must be between {min} and {max} characters
app.age.minimum=Age must be at least {value}
app.reference.format=Reference must have format ACCT-nnn
jakarta.validation.constraints.NotNull.message=Region must not be null
```

Notice `NotNull` uses the **constraint annotation's default**, yet its translation is overridden via the standard key `jakarta.validation.constraints.NotNull.message`.

### 8.6. ValidationMessagesDemo.java

```java
package demo;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.hibernate.validator.HibernateValidator;

public class ValidationMessagesDemo {

    private static final Locale VI = Locale.forLanguageTag("vi-VN");
    private static final Locale EN = Locale.ENGLISH;

    public record Account(
        @NotBlank(message = "{app.username.required}")
        String username,

        @Size(min = 3, max = 8, message = "{app.code.size}")
        String code,

        @Min(value = 18, message = "{app.age.minimum}")
        Integer age,

        @Pattern(
            regexp = "ACCT-[0-9]{3}",
            message = "{app.reference.format}"
        )
        String reference,

        @NotNull String region
    ) {}

    private static void check(Locale locale, Account account) {
        try (ValidatorFactory factory =
                Validation.byProvider(HibernateValidator.class)
                    .configure()
                    .locales(VI, EN)
                    .defaultLocale(locale)
                    .buildValidatorFactory()) {

            Validator validator = factory.getValidator();
            Set<ConstraintViolation<Account>> violations =
                    validator.validate(account);

            List<ConstraintViolation<Account>> sorted =
                violations.stream()
                    .sorted(Comparator.comparing(
                        v -> v.getPropertyPath().toString()))
                    .toList();

            System.out.println("LOCALE=" + locale.toLanguageTag());
            for (ConstraintViolation<Account> violation : sorted) {
                System.out.println(
                    violation.getPropertyPath()
                    + " | " + violation.getMessageTemplate()
                    + " | " + violation.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        Account invalid = new Account(
            "   ",  // NotBlank
            "ab",   // Size(min=3)
            17,     // Min(18)
            "bad",  // Pattern
            null    // NotNull
        );
        check(VI, invalid);
        check(EN, invalid);
    }
}
```

`ValidatorFactory` is closed via try-with-resources to release provider resources. In production, reuse a single factory rather than rebuilding one on every HTTP request. This sample intentionally creates two factories to illustrate locale selection, not as an optimal web server architecture.

### 8.7. Run Command and Expected Output

Requires Java 17+ and Maven 3.x. In the folder containing `pom.xml`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.ValidationMessagesDemo
```

Lines from `System.out.println`, excluding Maven or provider logs:

```text
LOCALE=vi-VN
age | {app.age.minimum} | Tuổi phải từ 18 trở lên
code | {app.code.size} | Mã phải dài từ 3 đến 8 ký tự
reference | {app.reference.format} | Mã tham chiếu phải có dạng ACCT-nnn
region | {jakarta.validation.constraints.NotNull.message} | Khu vực không được để trống
username | {app.username.required} | Tên đăng nhập không được để trống
LOCALE=en
age | {app.age.minimum} | Age must be at least 18
code | {app.code.size} | Code length must be between 3 and 8 characters
reference | {app.reference.format} | Reference must have format ACCT-nnn
region | {jakarta.validation.constraints.NotNull.message} | Region must not be null
username | {app.username.required} | Username must not be blank
```

Both validation runs detect the exact same five violations, while the displayed sentences differ. `getMessageTemplate()` preserves the keys, and `getMessage()` changes by locale and substitutes attributes. `Set<ConstraintViolation<?>>` has no guaranteed order, so the example sorts by property path before printing. The output is analyzed from the source code and bundles; if you customize provider, version, or configuration, run tests to verify.

## 9. Custom Constraint with a Default Template

When writing a custom constraint, the common convention is the annotation's fully qualified name + `.message`. For example:

```java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = AllowedCategoryValidator.class)
public @interface AllowedCategory {
    String message() default "{demo.AllowedCategory.message}";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

This is an **illustrative declaration**; you also need an `AllowedCategoryValidator` class implementing `ConstraintValidator<AllowedCategory,String>`. A top-level public annotation file must be named `AllowedCategory.java`; this snippet is not part of the program in Section 8.

In the bundles:

```properties
# ValidationMessages_vi.properties
demo.AllowedCategory.message=Loại hàng không được hỗ trợ
```

```properties
# ValidationMessages_en.properties
demo.AllowedCategory.message=Unsupported product category
```

A custom validator can use `ConstraintValidatorContext#buildConstraintViolationWithTemplate(...)` to build a custom template on violation. Use controlled keys/constants; never concatenate raw user input into an EL expression and hand it to the interpolator.

## 10. Locale: How Plain Jakarta Differs from Spring

### 10.1. Plain Jakarta Validator

When calling:

```java
ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
Validator validator = factory.getValidator();
Set<ConstraintViolation<Account>> errors = validator.validate(account);
```

this is a fragment assuming `Account` and `account` already exist. With the default interpolator, unless you explicitly pass a locale or configure the provider, Jakarta uses the JVM's default locale per the specification. **The HTTP `Accept-Language` header does not automatically affect a plain factory built like this.**

Do not call `Locale.setDefault(...)` per request to change languages, as it mutates global state and creates race conditions across concurrent requests.

### 10.2. Spring LocalValidatorFactoryBean

Spring integrates Bean Validation via `LocalValidatorFactoryBean`. This factory usually wraps the provider interpolator with `LocaleContextMessageInterpolator`, which reads `LocaleContextHolder.getLocale()`. In Spring MVC, the request locale is determined by `LocaleResolver`, so validation through the Spring-managed factory can use the current request's locale.

That does not mean every validator created manually by the application uses the request locale. If you call `Validation.buildDefaultValidatorFactory()` inside a service or supply a custom interpolator, you must verify its locale strategy. In asynchronous code, also ensure proper context propagation instead of assuming a `ThreadLocal` automatically follows every reactive stream.

### 10.3. Once the Message Has Been Produced

`ConstraintViolation#getMessage()` is interpolated **at validation time**. Changing the locale after `validate(...)` has returned will not re-interpolate an existing `ConstraintViolation`. Select the locale before validation, or intentionally re-resolve templates separately if needed.

## 11. ValidationMessages.properties vs. Spring messages.properties

Both systems can use `.properties` files, yet their message sources and syntax differ:

| Aspect | Jakarta Bean Validation | Spring MessageSource |
| --- | --- | --- |
| Default bundle | `ValidationMessages.properties` | Commonly `messages.properties` |
| Sentence selection | `message="{app.code.size}"` | `getMessage(code,args,locale)` |
| Typical placeholders | `{min}`, `{value}`, `${...}` | `{0}`, `{1}` via `MessageFormat` |
| Result | `ConstraintViolation#getMessage()` | String resolved from Spring `MessageSource` |
| Locale | `MessageInterpolator` / provider config | Locale passed to `MessageSource` |
| Share default bundle? | No | No |

In Spring MVC, `FieldError` and `ObjectError` implement `MessageSourceResolvable`. When calling:

```java
String message = messageSource.getMessage(fieldError, locale);
```

Spring tries codes such as `NotBlank.signupForm.username`, `NotBlank.username`, and `NotBlank`; the default message may hold the sentence already interpolated by Bean Validation. This is a **different** resolution layer from the provider reading `ValidationMessages.properties`.

### 11.1. `spring.messages.basename` Does Not Rename the Jakarta Bundle

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
```

This Spring Boot setting controls Spring `MessageSource`. It does not by default change the standard resource bundle used by the Bean Validation provider. When using both layers, keep both bundles or bridge them intentionally.

### 11.2. Using Spring MessageSource Instead of ValidationMessages

Spring `LocalValidatorFactoryBean` exposes:

```java
setValidationMessageSource(MessageSource messageSource)
```

Integration configuration example:

```java
@Configuration
public class ValidationConfig {

    @Bean
    public LocalValidatorFactoryBean validator(MessageSource messages) {
        LocalValidatorFactoryBean result = new LocalValidatorFactoryBean();
        result.setValidationMessageSource(messages);
        return result;
    }
}
```

This is a **Spring fragment** requiring imports and a Spring context; it is not part of the plain Hibernate Validator demo in Section 8. When used in Spring Boot, verify this is the validator actually used by MVC/services and avoid creating competing beans unintentionally.

According to the Spring API:

- `setValidationMessageSource(...)` plugs in a Spring `MessageSource` to resolve constraint messages rather than relying solely on Jakarta's default `ValidationMessages`.
- This integration point requires Hibernate Validator's `ResourceBundleMessageInterpolator`-related classes to be accessible.
- Do not configure both `setValidationMessageSource(...)` and `setMessageInterpolator(...)` expecting them to combine automatically.
- The Spring `MessageSource` used here should allow lookups to **fail to find a key** normally. Avoid `useCodeAsDefaultMessage=true` if it turns missing keys into literal messages and blocks provider fallback.
- Templates meant for Bean Validation must still use Bean Validation syntax, e.g., `{min}`, not Spring `MessageFormat`'s `{0}` by default.

Keeping two separate message sets can be simpler when system requirements do not need all keys shared.

## 12. Controller Integration and Multilingual Error Messages

Spring MVC has multiple validation paths:

- `@Valid @RequestBody DTO` without an adjacent result can throw `MethodArgumentNotValidException`.
- `@Valid @ModelAttribute Form` with `BindingResult` immediately after lets the controller handle errors inline.
- Direct constraints on controller method parameters or return values in Spring MVC 6.1+ can throw `HandlerMethodValidationException`.
- `@Validated` service beans via Spring AOP can throw `ConstraintViolationException` or `MethodValidationException` depending on configuration.

Do not format API errors by parsing `exception.getMessage()`. Extract structured `FieldError`/`ObjectError` or `ConstraintViolation` objects, keep machine codes stable, and apply the resolved locale before interpolating messages.

Illustrative controller advice example:

```java
@RestControllerAdvice
public class ApiValidationAdvice {

    private final MessageSource messages;

    public ApiValidationAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<List<ApiError>> handle(
            MethodArgumentNotValidException ex, Locale locale) {

        List<ApiError> body = ex.getBindingResult()
            .getAllErrors().stream()
            .map(error -> {
                String field = error instanceof FieldError fe
                    ? fe.getField() : "";
                return new ApiError(
                    field,
                    error.getCode(),
                    messages.getMessage(error, locale));
            })
            .toList();

        return ResponseEntity.badRequest().body(body);
    }

    public record ApiError(String field, String code, String message) {}
}
```

This is an integration fragment, not a standalone program; imports are required. It catches only one validation branch, so a real application may need to handle other exceptions at the API boundary. Never serialize `FieldError#getRejectedValue()` when the data could be a password, token, or PII.

## 13. Common Pitfalls

| Symptom | Cause | How to Handle |
| --- | --- | --- |
| Literal `{app.key}` appears in message | Key not found, wrong bundle or classpath | Check `ValidationMessages*.properties` |
| Created `messages_vi.properties` but Bean Validation ignores it | Confusing Spring `MessageSource` with Jakarta bundle | Create `ValidationMessages_vi.properties` or bridge explicitly |
| Always displays English | Validator uses JVM default locale | Check interpolator, request `Locale`, and Spring factory |
| Garbled Vietnamese diacritics | Wrong file encoding, resource loader, or build artifact | Save as UTF-8 and test end-to-end |
| `{min}` is not substituted | Wrong annotation attribute or non-Jakarta interpolation | Check descriptor and provider |
| Overriding key `min` replaces `3` | Key name collides with annotation attribute | Namespace custom keys |
| EL appears literally as `${...}` | Missing EL dependency, invalid expression, or provider restriction | Check Jakarta EL and configuration |
| Changing locale leaves violation with old text | Message was already interpolated during validation | Select locale before validation |
| Spring error code changes after renaming form | `@ModelAttribute` name changed | Design stable fallback codes/contract |
| Sensitive data exposed in message | Concatenating raw input or serializing full error objects | Output only safe codes and messages |
| `{0}` placeholder fails to work as expected | Confusing `MessageFormat` with Bean Validation params | Use each system's own syntax |
| Tests comparing `Set` order are flaky | Violation `Set` does not guarantee order | Sort by property path before asserting |

## 14. QA Checklist

1. Check that the bundle name `ValidationMessages` uses the exact capitalization.
2. Confirm `ValidationMessages.properties` and `_vi`/`_en` variants exist on the runtime classpath.
3. Verify UTF-8 encoding using Vietnamese messages with diacritics.
4. Test `getMessageTemplate()` and `getMessage()` for at least two locales.
5. Test `{min}`/`{max}`/`{value}` in templates.
6. Test user bundle overriding of the built-in `jakarta.validation.constraints.NotNull.message` key.
7. If you have custom constraints, test their default `message()` key.
8. If using EL, test the dependency, feature level, literal escaping, and avoid untrusted input in templates.
9. In MVC, test `Accept-Language` requests through the real Spring-managed validator.
10. Verify `messages.properties` and `ValidationMessages.properties` are not conflated.
11. If plugging Spring `MessageSource` into `LocalValidatorFactoryBean`, test missing keys and fallback behavior.
12. Never construct a new `ValidatorFactory` per request in production.
13. Verify responses never contain raw rejected values or sensitive data.
14. Keep translation keys consistent across all supported locales.

## 15. Summary

**`ValidationMessages.properties` is the default bundle for Jakarta Bean Validation message interpolation.** Constraints use `message="{app.key}"` to fetch translations by `Locale`; bundle entries can use `{min}`, `{max}`, `{value}`, or EL `${...}` when needed. `getMessageTemplate()` exposes the original descriptor, while `getMessage()` returns the interpolated sentence.

In Spring, distinguish Bean Validation bundles from Spring `MessageSource` and verify the locale resolution of `LocalValidatorFactoryBean`. Designing messages by keys, handling errors in structured form, and testing both languages prevent hardcoding, missing translations, and inconsistencies across validation paths.

## References

- Jakarta Bean Validation 3.0 — Message interpolation, section 6.3: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation API — `MessageInterpolator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/messageinterpolator
- Jakarta Validation API — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintviolation
- Hibernate Validator 8 — Reference Guide, message interpolation, section 4: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Hibernate Validator 8 — Locale resolution (provider extension): https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#section-custom-locale-resolution
- Spring Framework 6.2 — `LocalValidatorFactoryBean`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Framework 6.2 — `LocaleContextMessageInterpolator`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/beanvalidation/LocaleContextMessageInterpolator.html
- Spring Framework 6.2 — Bean Validation integration: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — MVC validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot — Internationalization: https://docs.spring.io/spring-boot/reference/features/internationalization.html