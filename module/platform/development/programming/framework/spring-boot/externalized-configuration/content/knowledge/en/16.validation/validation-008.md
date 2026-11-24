# Creating Custom Constraints and `ConstraintValidator`s for Spring Boot Configuration Properties

## 1. Why Are Built-In Validation Annotations Sometimes Not Enough?

A Spring Boot application can load configuration from `application.yaml`, environment variables, Java system properties, or `--key=value` arguments. With `@ConfigurationProperties`, the Binder maps effective values into a typed Java object.

Consider an order-processing service:

~~~yaml
shop:
  store-code: ABC-1024
  batch-size: 200
~~~

From a type standpoint, `store-code` is a string and `batch-size` is an integer. Yet the application also enforces **business rules**:

- The store code must follow three uppercase letters, a hyphen, and four digits, e.g., `ABC-1024`.
- The number of items processed per batch must be at least 1.
- When a configuration group has `initial-delay` and `max-delay`, the maximum delay must be greater than or equal to the initial delay.
- A configured URL may need to use HTTPS or belong to an allowlisted domain.
- A group of parameters may be valid only when **multiple fields relate properly to one another**, which cannot be checked field by field in isolation.

Bean Validation offers built-in constraints such as `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@Size`, `@Pattern`, and `@Email`. When requirements exceed what those can express cleanly, you can define a **custom constraint annotation** and implement **`ConstraintValidator`**.

This lesson explains in detail how to build custom constraints in Spring Boot 3.x using `jakarta.validation`, integrate them with `@Validated` on `@ConfigurationProperties`, validate single fields and cross-field relationships, customize error messages, and write tests.

## 2. Distinguishing Binding and Validation in the Startup Flow

A valid configuration passes through several stages:

~~~text
application.yaml / .properties / OS environment / CLI
                         |
                         v
              Spring Environment
                         |
                         v
             @ConfigurationProperties
                         |
                         v
                Spring Boot Binder
          resolve keys, convert data types
                         |
                         v
         Configuration bean created / populated
                         |
                         v
           Bean Validation if enabled
             |                        |
             v                        v
    Constraint satisfied      Constraint violated
             |                        |
             v                        v
      Bean ready for use     Startup may fail
             |
             v
      Dependency Injection
             |
             v
           Service
~~~

Example:

~~~properties
shop.batch-size=abc
~~~

When Java declares `int batchSize`, the Binder cannot convert `abc` to `int`. That is a **type-conversion/binding error**, before any custom validator can decide whether `batchSize` is large enough.

Conversely:

~~~properties
shop.batch-size=0
~~~

The Binder converts `0` to `int` cleanly. `@Min(1)` then determines the value **violates the business rule**.

And:

~~~properties
shop.store-code=abc-1024
~~~

is a type-valid string that violates an uppercase-only convention. A custom `ConstraintValidator` handles this cleanly.

**Key takeaway:** the Binder converts and binds values; Bean Validation inspects values after binding. Defining a constraint does not automatically register a configuration bean or alter property source selection.

## 3. Bean Validation System in Spring Boot 3.x

Spring Boot 3.x uses **Jakarta Validation**. Its core types reside in:

~~~java
jakarta.validation
jakarta.validation.constraints
~~~

Key components:

| Component | Role |
| --- | --- |
| `@Constraint` | Marks an annotation as a Bean Validation constraint. |
| `ConstraintValidator<A, T>` | Validates a value of type `T` against constraint `A`. |
| `ConstraintValidatorContext` | Customizes violation messages and property paths. |
| `@Valid` | Enables validation to cascade into nested objects. |
| `@Validated` | Spring annotation enabling validation in supported contexts, including `@ConfigurationProperties`. |
| `Validator` | Jakarta API for running validation on objects. |
| `ConstraintViolation` | Describes a violation: property path, message, invalid value, and metadata. |

In Spring Boot 3.x, **do not** use `javax.validation.*` imports from Spring Boot 2.x guides:

~~~java
// Spring Boot 3.x
import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
~~~

Important note: `@Validated` belongs to **Spring**:

~~~java
import org.springframework.validation.annotation.Validated;
~~~

While `@Valid` belongs to Jakarta:

~~~java
import jakarta.validation.Valid;
~~~

These two annotations play different roles. On `@ConfigurationProperties`, `@Validated` triggers validation on the configuration bean, whereas `@Valid` triggers deep validation into nested members.

## 4. Required Dependencies

Defining annotations and implementing interfaces requires the Jakarta Validation API. Executing validation at runtime requires a compatible **Bean Validation provider**. In Spring Boot, the standard choice is the validation starter.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

If your project already pulls in a compatible provider via another starter, avoid duplicating it. Never assume `jakarta.validation-api` alone is enough to evaluate constraints at runtime.

The validation starter typically brings Hibernate Validator as the provider. Hibernate Validator here is a **Bean Validation engine**, and does not mean your app uses Hibernate ORM or a database.

Example project layout:

~~~text
src/main/java/com/example/demo/
├── DemoApplication.java
├── config/
│   ├── StoreProperties.java
│   └── RetryProperties.java
├── validation/
│   ├── StoreCode.java
│   ├── StoreCodeValidator.java
│   ├── ValidRetryPolicy.java
│   └── RetryPolicyValidator.java
└── service/
    └── StoreService.java

src/main/resources/
└── application.yaml
~~~

## 5. Check Built-In Constraints Before Creating Custom Ones

Examples:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
~~~

Common direct usages:

~~~java
@NotBlank
String name;

@Min(1)
int batchSize;

@Max(1000)
int maxAttempts;

@NotNull
URI endpoint;

@Size(min = 2, max = 32)
String username;

@Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
String storeCode;
~~~

If you only need a fixed regular expression on one field, `@Pattern` may suffice. Custom constraints shine when:

1. The rule deserves a clear **domain name**, such as `@StoreCode`.
2. The rule is shared across modules and needs a single source of truth.
3. The rule takes custom parameters, such as format limits or allowed categories.
4. You must check relationships across multiple properties of the same object.
5. You need structured error messages and targeted property paths.
6. Validation logic exceeds what a simple regex can express.

Avoid creating a custom validator merely to wrap an existing built-in constraint with no gain in reusability or domain clarity.

## 6. Example 1 — Defining the `@StoreCode` Annotation

Suppose store codes follow this contract:

~~~text
ABC-1024  valid
HCM-2026  valid

abc-1024  invalid (lowercase)
AB-1234   invalid (two letters)
ABCD-1234 invalid (four letters)
ABC-123   invalid (three digits)
ABC1234   invalid (missing -)
~~~

We create an annotation named `@StoreCode`.

File `StoreCode.java`:

~~~java
package com.example.demo.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = StoreCodeValidator.class)
@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.RECORD_COMPONENT
})
@Retention(RetentionPolicy.RUNTIME)
public @interface StoreCode {

    String message() default
            "store code must match ABC-1234";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

A Bean Validation constraint annotation must declare standard members:

- `message()`: default violation message.
- `groups()`: validation groups; defaults to the default group when omitted.
- `payload()`: extensible metadata, not business data for the validated value.

And it requires:

- `@Constraint(validatedBy = StoreCodeValidator.class)` to link the annotation to its validator class.
- `@Retention(RUNTIME)` so metadata remains available to the runtime validator.
- `@Target(...)` specifying valid placement on fields, getters, constructor parameters, or record components.
- `@Documented` so the annotation appears in Javadoc when appropriate.

### Do Not Confuse `@Constraint` with `@Validated`

`@Constraint` defines **a validation rule type**. `@Validated` on a `@ConfigurationProperties` class **triggers validation** when Spring Boot processes the configuration bean.

Creating `@StoreCode` does not apply the rule to every `String` field in the application—only targets explicitly annotated with `@StoreCode` are checked.

## 7. Implementing `StoreCodeValidator`

File `StoreCodeValidator.java`:

~~~java
package com.example.demo.validation;

import java.util.regex.Pattern;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class StoreCodeValidator
        implements ConstraintValidator<StoreCode, String> {

    private static final Pattern CODE_PATTERN =
            Pattern.compile("[A-Z]{3}-[0-9]{4}");

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {

        // Null is left to @NotNull / @NotBlank.
        if (value == null) {
            return true;
        }

        return CODE_PATTERN.matcher(value).matches();
    }
}
~~~

Generic type arguments meaning:

~~~java
ConstraintValidator<StoreCode, String>
                    |          |
                    |          +-- data type being validated
                    +------------- constraint annotation type
~~~

`isValid(...)` returns:

- `true`: value satisfies the rule.
- `false`: value violates the constraint, causing the provider to create a `ConstraintViolation`.

### Why Use `matches()`?

`Pattern.matcher(value).matches()` requires the **entire string** to match the pattern. A partial-matching operation could accidentally accept strings like `prefix-ABC-1234-suffix`.

### Why Does `null` Return `true`?

This is an **intentional design decision**: `@StoreCode` checks **format when a value is present**, while mandatory presence is expressed with `@NotBlank` or `@NotNull`.

Example:

~~~java
@NotBlank
@StoreCode
String storeCode;
~~~

When `storeCode` is `null`:

- `@StoreCode` returns `true` per this design convention.
- `@NotBlank` reports a violation because the value is required.

When `storeCode` is an empty string, both `@NotBlank` and `@StoreCode` can report violations. That is normal behavior; if you want to suppress duplicate messages, consider a composite constraint or adjusted logic. Never have a validator silently mutate `null` into a default code.

### Never Mutate the Value Inside `isValid`

A validator should strictly inspect, never do:

~~~java
value = value.trim().toUpperCase();
~~~

and attempt to store it back on the object. `isValid` returns a boolean, not a data-transformation API. To normalize values before validation, perform that in conversion or configuration preparation.

## 8. Applying `@StoreCode` in `@ConfigurationProperties`

File `StoreProperties.java`:

~~~java
package com.example.demo.config;

import com.example.demo.validation.StoreCode;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop")
public record StoreProperties(

        @NotBlank
        @StoreCode
        String storeCode,

        @Min(1)
        int batchSize) {
}
~~~

File `application.yaml`:

~~~yaml
shop:
  store-code: HCM-2026
  batch-size: 200
~~~

When the `StoreProperties` bean is properly registered, Spring Boot:

1. Finds `shop.store-code` and `shop.batch-size` in `Environment`.
2. Uses the Binder to bind them into `storeCode` and `batchSize`.
3. Runs the Bean Validation provider on `@NotBlank`, `@StoreCode`, and `@Min(1)` because the class has `@Validated`.
4. If no violations occur, makes the properties bean available for injection into services.

### Registering the Bean in the Application

File `DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

With this package layout, `StoreProperties` sits under `com.example.demo` and is discovered by `@ConfigurationPropertiesScan`.

An alternative is explicit registration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(StoreProperties.class)
public class StoreConfiguration {
}
~~~

This suits setups without scanning or when the class lies outside scanned packages. Remember to import `org.springframework.context.annotation.Configuration` and `org.springframework.boot.context.properties.EnableConfigurationProperties`.

**Key distinction:** `@Validated` enables validation, yet does not replace bean registration via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

## 9. Consuming the Validated Configuration Bean

A service simply injects the bean via its constructor:

~~~java
package com.example.demo.service;

import com.example.demo.config.StoreProperties;
import org.springframework.stereotype.Service;

@Service
public class StoreService {

    private final StoreProperties properties;

    public StoreService(StoreProperties properties) {
        this.properties = properties;
    }

    public String describe() {
        return "store=" + properties.storeCode()
                + ", batchSize=" + properties.batchSize();
    }
}
~~~

In standard setups, the bean is already bound and validated before being injected as a valid dependency. If configuration violates constraints and Spring Boot fails to create the bean, context startup normally aborts.

This is ideal for settings that *must be valid before serving traffic*, such as partner codes, timeout policies, quantity bounds, routing parameters, or broker settings.

## 10. What Happens When Configuration Is Invalid?

Change YAML to:

~~~yaml
shop:
  store-code: hcm-2026
  batch-size: 0
~~~

Both values are type-valid in Java:

- `hcm-2026` is a string.
- `0` is an integer.

Yet they violate:

- `@StoreCode`, because the store code lacks three uppercase letters in the expected format.
- `@Min(1)`, because batch size must be at least 1.

When Spring Boot binds and validates `StoreProperties`, startup fails with details about the `shop` prefix, the offending properties, the bound values, and the violated constraints.

Outer wrapper exceptions vary across versions and contexts—such as a `ConfigurationPropertiesBindException` wrapping validation causes. Always look at the **property path** and **constraint message**, rather than assuming every startup failure is a dependency injection problem.

Diagnostic checklist:

1. Which configuration-properties bean failed initialization?
2. Which key is invalid: `shop.store-code` or `shop.batch-size`?
3. Did type conversion succeed?
4. Which constraint reported a violation?
5. Did the value come from YAML, an environment variable, CLI, or a higher-precedence source?
6. Is the custom constraint's business rule clearly stated in its message?

There is no need to alter `@ConfigurationProperties(prefix = "shop")` just because the store code format failed.

## 11. Customizing Error Messages

The annotation includes a default message:

~~~java
String message() default
        "store code must match ABC-1234";
~~~

At usage sites, you can override it:

~~~java
@StoreCode(message = "shop.store-code must match the format HCM-2026")
String storeCode;
~~~

Messages should explain the rule clearly. Write messages that are:

- Concise, stating expectations clearly.
- Non-blaming toward operators.
- Free of tokens, passwords, or sensitive data.
- Helpful with a valid format example when useful.
- Independent of any single environment-specific hardcoded value.

### Using Message Bundles

Under Jakarta Validation, messages can reference a key from a resource bundle:

~~~java
String message() default "{validation.storeCode.invalid}";
~~~

Example `ValidationMessages.properties` on the classpath:

~~~properties
validation.storeCode.invalid=Store code must match ABC-1234
~~~

The Bean Validation provider resolves message keys through message interpolation, supporting localization or message updates without changing annotation code.

To use bundles cleanly in your project, configure and test message interpolation for your active provider. That concerns **message presentation**, without changing `isValid` logic.

## 12. Creating Parameterized Constraints

`@StoreCode` checks a fixed pattern. Other custom constraints may need parameters such as lengths, algorithm names, allowed statuses, or validation modes.

Example annotation `@AllowedRegion`:

~~~java
package com.example.demo.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = AllowedRegionValidator.class)
@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.RECORD_COMPONENT
})
@Retention(RetentionPolicy.RUNTIME)
public @interface AllowedRegion {

    String message() default "region is not in the allowed list";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    String[] value();
}
~~~

Validator:

~~~java
package com.example.demo.validation;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class AllowedRegionValidator
        implements ConstraintValidator<AllowedRegion, String> {

    private Set<String> allowedRegions;

    @Override
    public void initialize(AllowedRegion annotation) {
        allowedRegions = Arrays.stream(annotation.value())
                .collect(Collectors.toUnmodifiableSet());
    }

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || allowedRegions.contains(value);
    }
}
~~~

Usage:

~~~java
@NotBlank
@AllowedRegion({"apac", "emea", "americas"})
String region;
~~~

When `region="apac"`, the validator returns `true`. When `region="moon"`, it returns `false`. The allowlist comes from the **annotation parameter**, not dynamically from `application.yaml`.

### What Is `initialize` Used For?

`initialize(...)` lets the validator prepare state from the annotation, such as:

- Allowed value sets.
- Numeric bounds.
- Precompiled regex patterns.
- Case-sensitivity flags.

Because a provider can reuse validator instances, avoid mutable per-call state inside `isValid(...)`. Here, `allowedRegions` is computed once in `initialize` and read safely thereafter.

**For a simple static rule**, you do not need to override `initialize`; that is why `StoreCodeValidator` earlier implemented only `isValid`.

## 13. Comparing Multiple Properties: Field-Level Constraints Are Not Enough

Suppose retry configuration is:

~~~yaml
client:
  retry:
    initial-delay: 2s
    max-delay: 30s
    max-attempts: 5
~~~

Business rules:

1. `initial-delay` must be positive.
2. `max-delay` must be positive.
3. `max-delay` must be **greater than or equal to** `initial-delay`.
4. `max-attempts` must be at least 1.

`@NotNull` catches missing values. `@Min(1)` checks the attempt count. Yet `maxDelay >= initialDelay` spans **two fields**, so a class-level constraint expresses it much better.

We create:

~~~java
@ValidRetryPolicy
public record RetryProperties(...) {
}
~~~

`@ValidRetryPolicy` sits on the **class/record** rather than a single member.

## 14. Defining the Class-Level Annotation `@ValidRetryPolicy`

File `ValidRetryPolicy.java`:

~~~java
package com.example.demo.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = RetryPolicyValidator.class)
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidRetryPolicy {

    String message() default
            "invalid retry configuration";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

`@Target(TYPE)` indicates the annotation checks the **entire object** after the Binder constructs it, unlike `@StoreCode` which validates a single `String`.

A class-level constraint fits well when:

- Start time must precede end time.
- `minConnections` cannot exceed `maxConnections`.
- Two flags must be enabled together.
- When `mode=secure`, `tls.enabled` must be true.
- Maximum retry backoff cannot be smaller than initial backoff.

These rules depend on **relationships between fields** rather than single-field values alone.

## 15. Implementing `RetryPolicyValidator`

File `RetryPolicyValidator.java`:

~~~java
package com.example.demo.validation;

import java.time.Duration;

import com.example.demo.config.RetryProperties;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class RetryPolicyValidator
        implements ConstraintValidator<ValidRetryPolicy, RetryProperties> {

    @Override
    public boolean isValid(
            RetryProperties value,
            ConstraintValidatorContext context) {

        if (value == null) {
            return true;
        }

        Duration initial = value.initialDelay();
        Duration maximum = value.maxDelay();

        // @NotNull on each field reports missing values.
        if (initial == null || maximum == null) {
            return true;
        }

        if (initial.isZero() || initial.isNegative()) {
            return violation(
                    context,
                    "initialDelay",
                    "initial-delay must be greater than 0");
        }

        if (maximum.isZero() || maximum.isNegative()) {
            return violation(
                    context,
                    "maxDelay",
                    "max-delay must be greater than 0");
        }

        if (maximum.compareTo(initial) < 0) {
            return violation(
                    context,
                    "maxDelay",
                    "max-delay must not be less than initial-delay");
        }

        return true;
    }

    private boolean violation(
            ConstraintValidatorContext context,
            String property,
            String message) {

        context.disableDefaultConstraintViolation();

        context.buildConstraintViolationWithTemplate(message)
                .addPropertyNode(property)
                .addConstraintViolation();

        return false;
    }
}
~~~

Technical highlights:

- The second generic argument is `RetryProperties`, because this validator checks the entire object.
- Returning `true` on null lets `@NotNull` report missing fields and prevents `NullPointerException`.
- Checks `Duration` directly via `isZero`, `isNegative`, and `compareTo`, rather than parsing strings like `2s`.
- On violation, uses `ConstraintValidatorContext` to direct the error at the relevant Java property.
- Helper `violation(...)` builds one targeted violation for the failing branch and returns `false`.

### Why Use `addPropertyNode`?

Class-level constraints default to attaching errors to the object itself. Often you want to highlight the specific field to fix, such as `maxDelay`.

This snippet:

~~~java
context.buildConstraintViolationWithTemplate(
        "max-delay must not be less than initial-delay")
        .addPropertyNode("maxDelay")
        .addConstraintViolation();
~~~

gives the violation a specific property path. Here `maxDelay` is the **Java member name**, not necessarily the kebab-case YAML string `max-delay`.

For an error genuinely pertaining to the group as a whole, you can keep the violation at object level—just describe the cross-field relationship clearly so operators know what to adjust.

### Do Not Build a Violation and Forget `addConstraintViolation`

`buildConstraintViolationWithTemplate(...)` only starts constructing the violation path. You must call `addConstraintViolation()` to register it. If you call `disableDefaultConstraintViolation()` and return `false` without adding a replacement violation, the provider treats that as an invalid state.

## 16. Applying `@ValidRetryPolicy` to `@ConfigurationProperties`

File `RetryProperties.java`:

~~~java
package com.example.demo.config;

import java.time.Duration;

import com.example.demo.validation.ValidRetryPolicy;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ValidRetryPolicy
@ConfigurationProperties(prefix = "client.retry")
public record RetryProperties(

        @NotNull
        Duration initialDelay,

        @NotNull
        Duration maxDelay,

        @Min(1)
        int maxAttempts) {
}
~~~

Valid configuration:

~~~yaml
client:
  retry:
    initial-delay: 2s
    max-delay: 30s
    max-attempts: 5
~~~

Invalid configuration:

~~~yaml
client:
  retry:
    initial-delay: 20s
    max-delay: 2s
    max-attempts: 5
~~~

In the invalid configuration:

- The Binder converts both `20s` and `2s` to `Duration`.
- `@NotNull` passes because both fields are present.
- `@ValidRetryPolicy` compares both `Duration`s and reports a violation because `maxDelay < initialDelay`.

This illustrates the core use case for class-level custom constraints: **valid types and present fields, yet an overall object that violates business rules**.

## 17. Why Is `@Validated` Required on the Configuration Class?

Spring Boot validates `@ConfigurationProperties` when the class carries `@Validated` and a compatible Bean Validation provider exists.

Example:

~~~java
@Validated
@ConfigurationProperties(prefix = "client.retry")
@ValidRetryPolicy
public record RetryProperties(...) {
}
~~~

Here:

- `@ConfigurationProperties` tells the Binder the prefix.
- `@ValidRetryPolicy` declares the class-level constraint.
- `@Validated` triggers Spring Boot's configuration-bean validation.

If you add `@ValidRetryPolicy` **without enabling** configuration validation, do not assume your custom validator runs at startup.

Conversely, having `@Validated` without a compatible Bean Validation provider will not execute constraints either.

### Registering the Configuration Class Remains a Separate Step

`RetryProperties` must still be registered via `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties(RetryProperties.class)`, or another supported mechanism.

Three separate tasks:

1. **Bean registration:** so Spring knows to instantiate the class.
2. **Configuration binding:** to resolve and convert values into fields/constructors.
3. **Validation:** to evaluate constraints on the bound object.

Do not confuse a "missing bean" failure with "constraints not working."

## 18. Combining Field-Level and Class-Level Constraints

A common pattern:

~~~java
@Validated
@ValidRetryPolicy
@ConfigurationProperties(prefix = "client.retry")
public record RetryProperties(
        @NotNull Duration initialDelay,
        @NotNull Duration maxDelay,
        @Min(1) int maxAttempts) {
}
~~~

Meaning:

- `@NotNull` ensures required timing fields are present.
- `@Min(1)` ensures attempt count is at least 1.
- `@ValidRetryPolicy` verifies positivity and ordering across both `Duration`s.

When a field is missing, the class-level validator returns `true` early so standard constraints report the missing field. That is a **clean separation of concerns**, not a strict requirement of Jakarta Validation—if you prefer one validator checking everything, design accordingly while avoiding null exceptions and ensuring clear messages.

### Multiple Violations Can Occur Together

If YAML contains:

~~~yaml
client:
  retry:
    initial-delay: 20s
    max-delay: 2s
    max-attempts: 0
~~~

the provider may report both:

- `max-attempts` violating `@Min(1)`.
- `max-delay >= initial-delay` failing.

Never rely on a fixed violation order. In logs and tests, inspect the **set of property paths/messages** rather than assuming one violation always comes first.

## 19. Nested Objects: When Is `@Valid` Needed?

A configuration class can contain a child object:

~~~java
package com.example.demo.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Min;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(

        @NotNull
        @Valid
        Connection connection) {

    public record Connection(
            @NotBlank String host,
            @Min(1) int port) {
    }
}
~~~

YAML:

~~~yaml
service:
  connection:
    host: api.example.test
    port: 8443
~~~

Here, `@Valid` on `connection` tells Bean Validation to **descend into the child object** and check `host`/`port`.

If `connection` is missing completely, `@NotNull` catches the missing object. If `connection` is present with an empty `host`, `@Valid` triggers inner validation and `@NotBlank` fails.

Per Spring Boot's documentation, put `@Valid` on nested fields when you want validation triggered consistently even if no child properties are supplied. For JavaBeans with eagerly instantiated nested objects, `@Valid` is especially important.

### Comparing `@Valid` and `@Validated`

| Annotation | Typical Placement | Primary Role |
| --- | --- | --- |
| `@Validated` | `@ConfigurationProperties` class, Spring bean, or method | Enables validation in Spring integration; can specify groups. |
| `@Valid` | Field/record component holding a child object | Enables cascaded validation into nested objects. |
| `@Constraint` | Custom constraint annotation definition | Declares a constraint type and its validator. |
| `@StoreCode`, `@ValidRetryPolicy` | Target element to validate | Declares a specific business rule. |

`@Valid` itself is not a formatting rule like `@Pattern`; it is the **cascaded validation** trigger.

## 20. Sharing Custom Constraints Between Records and JavaBeans

A field-level annotation such as `@StoreCode` works on a record component:

~~~java
public record StoreProperties(
        @NotBlank @StoreCode String storeCode) {
}
~~~

Or on a JavaBean field:

~~~java
public class MutableStoreProperties {

    @NotBlank
    @StoreCode
    private String storeCode;

    public String getStoreCode() {
        return storeCode;
    }

    public void setStoreCode(String storeCode) {
        this.storeCode = storeCode;
    }
}
~~~

The validator remains:

~~~java
ConstraintValidator<StoreCode, String>
~~~

because the validated type is still `String`.

By contrast, `RetryPolicyValidator` is a class-level validator targeting `RetryProperties`. It does not automatically apply to another class like `LegacyRetryProperties` just because it shares similarly named fields. To reuse checks across distinct classes, introduce an interface/abstraction or provide dedicated validators per target type.

### Caution with Annotations on Getters

Jakarta Validation also supports constraints on property getters when `METHOD` is in `@Target`. However, avoid annotating both the field **and** the getter of the same property unintentionally, as providers may treat them as two separate constraint locations and emit duplicate violations.

## 21. Unit Testing Validators Without Booting Spring Boot

Custom constraints are standard Jakarta Validation components. You can test their logic through `jakarta.validation.Validator` without starting the whole application.

Example test:

~~~java
package com.example.demo.validation;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;

import com.example.demo.config.StoreProperties;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.Test;

class StoreConstraintTest {

    @Test
    void acceptsValidStoreCode() {
        ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory();

        try {
            Validator validator = factory.getValidator();

            StoreProperties value =
                    new StoreProperties("HCM-2026", 100);

            Set<ConstraintViolation<StoreProperties>> violations =
                    validator.validate(value);

            assertTrue(violations.isEmpty());
        } finally {
            factory.close();
        }
    }

    @Test
    void rejectsLowercaseStoreCode() {
        ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory();

        try {
            Validator validator = factory.getValidator();

            StoreProperties value =
                    new StoreProperties("hcm-2026", 100);

            Set<ConstraintViolation<StoreProperties>> violations =
                    validator.validate(value);

            assertFalse(violations.isEmpty());
        } finally {
            factory.close();
        }
    }
}
~~~

This test exercises **annotation/validator rules**, without verifying whether Spring Boot loaded the YAML file. You can share one `ValidatorFactory` across tests in a suite rather than creating a new factory in every method.

### Inspecting the Property Path

For an object with a `storeCode` violation, `ConstraintViolation.getPropertyPath()` reveals where the error occurred:

~~~java
for (ConstraintViolation<StoreProperties> violation
        : violations) {

    System.out.println(
            violation.getPropertyPath() + ": "
                    + violation.getMessage());
}
~~~

Example output:

~~~text
storeCode: store code must match ABC-1234
~~~

Do not rely on `Set` iteration order. In real tests, assert that the collection **contains** the expected path.

## 22. Testing a Class-Level `ConstraintValidator`

We already have:

~~~java
@Validated
@ValidRetryPolicy
@ConfigurationProperties(prefix = "client.retry")
public record RetryProperties(
        @NotNull Duration initialDelay,
        @NotNull Duration maxDelay,
        @Min(1) int maxAttempts) {
}
~~~

Construct objects directly:

~~~java
RetryProperties valid = new RetryProperties(
        Duration.ofSeconds(2),
        Duration.ofSeconds(30),
        5);

RetryProperties invalid = new RetryProperties(
        Duration.ofSeconds(20),
        Duration.ofSeconds(2),
        5);
~~~

Call `Validator.validate(...)` on both to verify:

- `valid` yields zero violations.
- `invalid` produces a violation targeting `maxDelay`, matching `addPropertyNode("maxDelay")`.

### Example Test

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.time.Duration;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.Test;

class RetryPolicyConstraintTest {

    @Test
    void rejectsMaximumSmallerThanInitial() {
        ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory();

        try {
            Validator validator = factory.getValidator();

            RetryProperties props = new RetryProperties(
                    Duration.ofSeconds(20),
                    Duration.ofSeconds(2),
                    5);

            var violations = validator.validate(props);

            assertFalse(violations.isEmpty());

            assertTrue(
                    violations.stream()
                            .anyMatch(v ->
                                    v.getPropertyPath()
                                            .toString()
                                            .equals("maxDelay")));
        } finally {
            factory.close();
        }
    }
}
~~~

In this test, import `RetryProperties` from its config package. This tests **constraint logic on Java objects**; it does not test relaxed binding, profiles, or `PropertySource` precedence.

## 23. Integration Testing: Does Spring Boot Actually Validate at Startup?

A custom constraint passing standalone Jakarta tests does not guarantee the `@ConfigurationProperties` bean is registered and validated inside the application.

For integration testing, use Spring Boot's `ApplicationContextRunner`. It builds a small controlled context letting you assert startup success or failure.

Example:

~~~java
package com.example.demo;

import com.example.demo.config.StoreProperties;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class StorePropertiesContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ConfigurationPropertiesAutoConfiguration.class,
                            ValidationAutoConfiguration.class))
                    .withUserConfiguration(TestConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(StoreProperties.class)
    static class TestConfig {
    }

    @Test
    void startsWithValidConfiguration() {
        runner.withPropertyValues(
                "shop.store-code=HCM-2026",
                "shop.batch-size=100")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            StoreProperties.class);
                });
    }

    @Test
    void failsWithInvalidStoreCode() {
        runner.withPropertyValues(
                "shop.store-code=bad-value",
                "shop.batch-size=100")
                .run(context ->
                        assertThat(context).hasFailed());
    }
}
~~~

Meaning:

- `@EnableConfigurationProperties` registers the bean to bind.
- `withPropertyValues(...)` supplies test configuration properties.
- Spring Boot infrastructure performs binding and validation.
- The passing test confirms the context provides a valid bean.
- The failing test proves validation executes during the startup lifecycle.

In real projects, ensure matching auto-configurations and dependencies (`spring-boot-starter-test` and `spring-boot-starter-validation`) are on the test classpath.

### Testing Multiple Configuration Sources

After testing valid and invalid single values, test CLI or environment overrides to confirm the **final effective value** is what gets validated. Testing a class-level validator directly does not prove YAML-vs.-CLI precedence.

## 24. How Validators Receive Null, Empty, and Wrong-Type Inputs

These are three distinct categories:

| Input | Scenario | Appropriate Layer |
| --- | --- | --- |
| Missing `shop.store-code` key | Value can be null | `@NotNull` or `@NotBlank`. |
| `shop.store-code=` | Empty string | `@NotBlank`; custom constraint may also fail. |
| `shop.store-code=hcm-2026` | String with invalid format | `@StoreCode`. |
| `shop.batch-size=abc` | Cannot convert to integer | Binding/conversion. |
| `shop.batch-size=0` | Valid integer violating policy | `@Min(1)`. |
| `maxDelay < initialDelay` | Two individually valid `Duration`s with invalid order | `@ValidRetryPolicy`. |

A single custom validator does not need to catch all cases. Separating responsibilities yields clearer errors and simpler maintenance.

### Do Not Throw Exceptions Just to Report Invalid Values

Inside `isValid(...)`, when a value violates a rule, return `false` instead of throwing a business exception like:

~~~java
throw new IllegalArgumentException(
        "Invalid store code");
~~~

An unexpected exception may be treated by the provider as a validator execution error, obscuring messages and error flow. Exceptions are for unrecoverable execution bugs, not normal `ConstraintViolation` reporting.

## 25. What Are Validation Groups Used For?

Every custom constraint defines:

~~~java
Class<?>[] groups() default {};
~~~

Jakarta Validation allows grouping constraints so different subsets run in different contexts.

Example marker interface:

~~~java
public interface ProductionChecks {
}
~~~

A constraint can target it:

~~~java
@StoreCode(groups = ProductionChecks.class)
String storeCode;
~~~

When validating only the **default group**, constraints belonging to `ProductionChecks` are not evaluated unless that group is explicitly requested in the validator call or Spring configuration.

With `@ConfigurationProperties`, keep rules **essential across all environments** in the default group so production never skips validation due to an inactive group.

Never equate `spring.profiles.active` with validation group names:

- Spring profiles select active beans and configuration sources.
- Validation groups select which constraints are evaluated.

They do not map one-to-one automatically.

## 26. Can You Write a Custom Spring `Validator` Instead of `ConstraintValidator`?

Yes. Spring Framework provides:

~~~java
org.springframework.validation.Validator
~~~

with `supports(...)` and `validate(Object, Errors)`.

Spring Boot also supports a special bean named `configurationPropertiesValidator` for Spring-style validation during configuration binding. Per Spring Boot docs, that validator bean is initialized very early, so its `@Bean` method inside a configuration class should be declared `static` to avoid premature configuration class instantiation.

However, that is a **different extension mechanism** from defining Jakarta Bean Validation annotations and `ConstraintValidator`s.

| Requirement | Typical Best Fit |
| --- | --- |
| Reuse a field-level constraint across many classes | Jakarta `@Constraint` + `ConstraintValidator`. |
| Validate relationships across fields in one class | Jakarta class-level `@Constraint`. |
| Combine `@NotBlank`, `@Min`, `@Valid`, and Bean Validation provider | Jakarta Validation. |
| Need validation integrated directly with Spring `Errors` | Spring `Validator`. |
| Add infrastructure-level configuration properties validator | `configurationPropertiesValidator` per Spring Boot docs. |

In this lesson, the primary choice is **Jakarta Bean Validation** because it declares rules directly on classes and fields and reuses cleanly.

## 27. Should You Inject Spring Beans Into a `ConstraintValidator`?

In a properly integrated Spring Boot environment, `ConstraintValidator` instances can be created through Bean Validation wiring supporting dependency injection. However, do not assume every `ValidatorFactory` outside Spring supports injecting Spring beans.

Especially with `@ConfigurationProperties`, validation occurs **during application context initialization**. A validator depending on services, database clients, or beans awaiting configuration can create circular dependencies or premature initialization failures.

For pure configuration rules, prefer validators that:

- Have no side effects.
- Make no network or database calls.
- Perform no file writes.
- Do not rely on mutable runtime state.
- Are easy to unit test with plain Java objects.
- Operate solely on annotation parameters and the object under validation.

`StoreCodeValidator` with a constant `Pattern` and `RetryPolicyValidator` comparing two `Duration`s are pure checks needing no external services.

If business logic truly requires live state from another system, ask whether it belongs in **startup configuration validation** or in **readiness/connectivity checks** later. Bean Validation is not a remote system health monitor.

## 28. Property Precedence Affects What Reaches the Validator

A validator does not know which file a value came from unless you inspect origin metadata separately. It sees only the bound object or field supplied by the Binder.

Example YAML:

~~~yaml
shop:
  store-code: HCM-2026
  batch-size: 100
~~~

Run command:

~~~bash
java -jar app.jar --shop.store-code=invalid --shop.batch-size=100
~~~

In a standard Spring Boot run, command-line arguments override YAML. `StoreProperties.storeCode()` therefore receives `invalid`, and the custom validator fails even though the `application.yaml` open in your editor has a valid code.

Diagnose in two steps:

1. **Which source supplied the effective value?** Determined by `Environment` and `PropertySource` precedence.
2. **Is that value valid?** Determined by Bean Validation.

Never loosen the regex in your validator when the real culprit is an environment variable or CLI flag overriding your config.

### Profiles Have Similar Effects

~~~yaml
# application-prod.yaml
shop:
  store-code: HCM-2026
~~~

Wait—check lines 1450-1454 in `validation-008.md`: it's `~~~yaml` and `~~~`, let's keep `~~~` consistently!

When the `prod` profile is active, this document participates in Config Data. Yet a higher-precedence source can still override `shop.store-code`. Constraints always evaluate the final values on the properties bean.

## 29. Reporting Violations on a Property Path vs. Object Level

With a field-level constraint `@StoreCode`, the provider naturally knows the property path is `storeCode`.

With a class-level constraint `@ValidRetryPolicy`, violations default to the `RetryProperties` object itself. To point operators specifically to `max-delay`, we added:

~~~java
context.disableDefaultConstraintViolation();

context.buildConstraintViolationWithTemplate(
        "max-delay must not be less than initial-delay")
        .addPropertyNode("maxDelay")
        .addConstraintViolation();
~~~

This attaches the error to the Java property `maxDelay`. In Spring Boot startup error reports, key names may appear in kebab-case config form or Java property paths depending on version. Never write brittle assertions against exact log formatting across versions.

### Multiple Errors for One Class-Level Rule

You can also emit multiple violations after calling `disableDefaultConstraintViolation()`, such as one on `initialDelay` and one on `maxDelay`. Be deliberate so you do not emit noisy duplicate messages.

A custom validator should not duplicate `@NotNull` or `@Min` errors if individual field constraints already cover them, unless unified error formatting requires it.

## 30. Protecting Secrets During Validation

`@ConfigurationProperties` objects can hold passwords, API tokens, connection strings, or environment secrets. Error messages must never print secret values.

**Do not**:

~~~java
return violation(context,
        "password",
        "Invalid password: " + value.password());
~~~

Such messages end up in startup logs or CI/CD output, leaking credentials.

**Do**:

~~~text
app.credentials.password does not meet minimum length policy
~~~

when an error message is needed. Avoid putting raw secrets into message templates, exceptions, or debug logs.

`ConstraintViolation` instances themselves can retain the invalid value. If you log violations manually, select only safe fields to output. Also protect diagnostic endpoints such as `/actuator/configprops` and `/actuator/env`.

Constraints decide **valid vs. invalid**; they do not automatically encrypt or mask secrets.

## 31. Performance and Statefulness Considerations for Validators

A Jakarta Validation provider can reuse `ConstraintValidator` instances. Therefore:

- Never store the validated value in a mutable field on the validator.
- Precompile regexes into `static final Pattern` fields like `StoreCodeValidator`.
- When annotations take parameters, prepare data in `initialize` and treat it as read-only inside `isValid`.
- Never use static variables to remember "the last validated value."
- Never depend on the order in which a provider invokes different validators.
- Keep `isValid` pure and free of side effects whenever possible.

A custom constraint may run repeatedly: in unit tests, during config binding, and in service or request validation if reused. Pure design guarantees consistent results.

## 32. Common Mistakes When Writing Custom `ConstraintValidator`s

### Mistake 1: Using `javax.validation` in Spring Boot 3.x

Code copied from Spring Boot 2.x may import:

~~~java
import javax.validation.ConstraintValidator;
~~~

In Spring Boot 3.x, use:

~~~java
import jakarta.validation.ConstraintValidator;
~~~

Also confirm validation dependencies match your project's Jakarta version.

### Mistake 2: Forgetting `@Constraint`

An annotation with `@Target` and `@Retention` but missing:

~~~java
@Constraint(validatedBy = StoreCodeValidator.class)
~~~

is not recognized as a complete constraint by the provider.

### Mistake 3: Omitting `message()`, `groups()`, or `payload()`

These are required members of a Bean Validation constraint definition. Omitting them causes providers to reject the annotation as an invalid constraint declaration.

### Mistake 4: Wrong `@Target`

An annotation with only `@Target(FIELD)` cannot be placed at class level or on constructor parameters where needed. Include `FIELD`, `METHOD`, `PARAMETER`, `RECORD_COMPONENT`, or `TYPE` matching where the constraint is applied.

### Mistake 5: Forgetting `@Retention(RUNTIME)`

Without runtime retention, providers cannot inspect the constraint metadata.

### Mistake 6: Incompatible Generic Type

~~~java
ConstraintValidator<StoreCode, Integer>
~~~

cannot directly validate a `String storeCode`. The validator's second generic type must match the validated Java type.

### Mistake 7: Throwing Exceptions Instead of Returning `false`

An invalid input value should yield a `ConstraintViolation`, not an unexpected exception. Exceptions signal validator execution failures to the provider.

### Mistake 8: Not Handling `null`

If a validator writes:

~~~java
return value.matches("[A-Z]{3}-[0-9]{4}");
~~~

and `value=null`, it throws `NullPointerException`. Define your null policy and coordinate with `@NotNull`/`@NotBlank`.

### Mistake 9: Adding Annotations Without `@Validated`

A `@ConfigurationProperties` class carrying custom constraints without enabling validation may not be checked during binding. Add `@Validated` and a compatible provider.

### Mistake 10: Omitting `@Valid` on Nested Objects

To evaluate constraints inside a child object, place `@Valid` on the member holding it. `@Validated` on the parent alone does not replace cascading.

### Mistake 11: Using YAML Names Instead of Java Property Names in Nodes

In `ConstraintValidatorContext.addPropertyNode(...)`, pass the Java property name understood by Bean Validation, such as `maxDelay`. Do not assume kebab-case names like `max-delay` work as JavaBean property nodes directly.

### Mistake 12: Forgetting `addConstraintViolation()`

After customizing message/path and disabling the default violation, complete the new violation before returning `false`.

### Mistake 13: Mixing Conversion Logic Into Validation

Validators should not parse `"30s"` into `Duration` or normalize data. The Binder and converters handle conversion; validators receive typed values and check them.

### Mistake 14: Stateful Validators

Shared mutable fields storing the previous call's state make outcomes order-dependent when validators are reused. Keep state immutable or scoped per annotation instance.

### Mistake 15: Querying a Database During Startup Validation

Startup can fail merely because the network or database is temporarily unreachable, even when local syntax and policies are completely valid. Separate **configuration validity** from **external system availability**.

## 33. Practice Exercises with Answers

### Exercise 1 — Choosing Where to Place a Field Constraint

Given:

~~~properties
shop.store-code=ABC-1024
~~~

Goal: accept only `AAA-9999` (three uppercase letters and four digits).

**Suggested Answer:** create `@StoreCode` with `@Constraint(validatedBy = StoreCodeValidator.class)`; the validator uses `Pattern.compile("[A-Z]{3}-[0-9]{4}")` and `matches()`. Place it on the `String storeCode` field/record component, paired with `@NotBlank` if required.

### Exercise 2 — Distinguishing Missing Keys from Bad Formats

Suppose you have:

~~~java
@NotBlank
@StoreCode
String storeCode;
~~~

Predict outcomes:

| Value | `@NotBlank` | Example `@StoreCode` |
| --- | --- | --- |
| `null` | Violation | Valid per custom validator's null policy. |
| `""` | Violation | Violation because regex does not match. |
| `"abc-1234"` | Passes non-blank check | Violation because lowercase. |
| `"ABC-1234"` | Passes | Passes. |

### Exercise 3 — Choosing the Constraint Level

Rule: `max-delay` must not be smaller than `initial-delay`.

**Answer:** class-level constraint, because both fields must be inspected simultaneously. A single-field constraint on `maxDelay` alone could not access `initialDelay` cleanly without extra context; class-level is the idiomatic Bean Validation solution.

### Exercise 4 — Classifying Errors

~~~properties
shop.batch-size=abc
~~~

and Java:

~~~java
@Min(1)
int batchSize;
~~~

**Answer:** failing to convert `abc` to `int` is a binding/conversion error, not `@Min(1)` rejecting a valid integer.

### Exercise 5 — Missing `@Validated`

You wrote:

~~~java
@StoreCode
String storeCode;
~~~

inside a `@ConfigurationProperties` class registered via `@ConfigurationPropertiesScan`, without `@Validated`.

**Answer:** registering the bean and annotating fields does not enable Spring Boot validation. Add `@Validated`, ensure a Bean Validation provider is present, and confirm with a context test.

### Exercise 6 — Custom Violation Path

In a class-level validator, you want the error attached to the Java property `maxDelay` instead of only the object level.

**Answer:**

~~~java
context.disableDefaultConstraintViolation();

context.buildConstraintViolationWithTemplate(
        "max-delay must not be less than initial-delay")
        .addPropertyNode("maxDelay")
        .addConstraintViolation();

return false;
~~~

### Exercise 7 — Testing Without Booting Spring

You want to prove `@StoreCode` accepts `HCM-2026` and rejects `hcm-2026`.

**Answer:** use `Validation.buildDefaultValidatorFactory()` to get a `Validator`, call `validator.validate(new StoreProperties(...))`, and inspect `ConstraintViolation`s. A full `@SpringBootTest` is unnecessary for testing pure constraint rules.

### Exercise 8 — Testing Startup Behavior

You want to guarantee the app refuses to start when `shop.store-code=bad-value`.

**Answer:** write a context test registering `StoreProperties`, enabling Bean Validation, supplying invalid configuration, and asserting that context startup fails. This integration-tests the Binder together with validation.

### Exercise 9 — Nested Validation

~~~java
@Validated
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(Connection connection) {
    public record Connection(@NotBlank String host) {
    }
}
~~~

You want deep validation enabled for `host`.

**Answer:** place `@Valid` on `connection`; if `connection` itself is required, add `@NotNull`.

### Exercise 10 — Should Validation Make HTTP Requests?

Goal: verify that a configured URL uses `https` and belongs to an allowlisted domain group.

**Answer:** in almost all cases, check scheme and host with pure logic on `URI`. Never call the live endpoint to "check if the URL is valid"; whether the remote service is currently responding belongs in health/readiness checks.

### Exercise 11 — Which Source's Value Gets Validated?

YAML has:

~~~properties
shop.store-code=HCM-2026
~~~

Yet the app runs with:

~~~bash
java -jar app.jar --shop.store-code=bad-value
~~~

**Answer:** under default precedence, CLI overrides YAML; the validator receives `bad-value` from the properties bean and reports a violation.

### Exercise 12 — Error Messages Without Leaking Secrets

A custom validator checks that a token meets a minimum length. Never include the actual token in the message.

**Answer:** use a message such as `"security.api-token does not meet minimum length"` rather than concatenating the token value into messages or exceptions.

## 34. Choice Summary Table

| Need | Choice |
| --- | --- |
| Non-blank string | `@NotBlank`. |
| Integer at least 1 | `@Min(1)`. |
| String matching a simple regex | `@Pattern`, if no domain abstraction is needed. |
| Reusable domain store code rule | Custom `@StoreCode` + `ConstraintValidator<StoreCode, String>`. |
| Relationship between two `Duration`s | Class-level `@ValidRetryPolicy` + object validator. |
| Nested configuration needing inner checks | `@Valid` on the field/component holding the child object. |
| Spring Boot validating config bean on bind | `@Validated` on `@ConfigurationProperties` plus provider. |
| Targeting a specific field from class-level validator | `ConstraintValidatorContext.addPropertyNode(...)`. |
| Separate rule sets for different contexts | Bean Validation groups. |
| Testing constraint logic without Spring | `Validator.validate(object)`. |
| Testing startup failure on bad config | Spring Boot context test / `ApplicationContextRunner`. |
| Custom validation tied directly to Spring `Errors` | Spring `Validator` or `configurationPropertiesValidator` as needed. |

## 35. Conclusion

In Spring Boot, a **custom constraint** packages a domain validation rule into a reusable annotation. `@Constraint` links the annotation to a `ConstraintValidator`; `isValid(...)` evaluates the input and returns true/false; and `ConstraintValidatorContext` customizes error messages and target property paths.

When applied to `@ConfigurationProperties`, keep the full lifecycle clear:

1. Spring Boot loads config sources and the Binder maps data into typed Java objects.
2. Properties classes are registered via `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or an equivalent mechanism.
3. `@Validated` together with a Bean Validation provider evaluates declared constraints.
4. Field-level constraints check individual values; class-level constraints check cross-field relationships; `@Valid` enables nested object cascading.
5. When values are invalid, Spring Boot can halt startup and surface configuration errors immediately.

Prefer built-in constraints for simple rules; write custom `ConstraintValidator`s when you need clear, testable, reusable domain rules. Keep validation logic pure, never convert or mutate data inside validators, avoid external calls unless truly warranted, and never leak sensitive configuration in error messages.

## References

- [Spring Boot 3.3 — Externalized Configuration, ConfigurationProperties Validation section](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation).
- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0).
- [Jakarta Validation — ConstraintValidator API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintvalidator).
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html).