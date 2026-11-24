# Cross-Field Validation Across Multiple Configuration Properties

## 1. Problem: Individually Valid Fields, Yet an Invalid Overall Configuration

In Spring Boot Externalized Configuration, an application can receive parameters from **`application.yml`**, **`application.properties`**, environment variables, command-line arguments, external files, or other `PropertySource`s. **`@ConfigurationProperties`** maps those values into a typed Java object. **Bean Validation** helps detect missing or invalid data.

Annotations like **`@NotNull`**, **`@Min`**, **`@Max`**, and **`@NotBlank`** handle **single-field constraints** very well. Yet not every business rule can be evaluated on a single field in isolation.

Example:

~~~yaml
demo:
  http-client:
    connect-timeout: 8s
    request-timeout: 3s
~~~

Both **`8s`** and **`3s`** convert cleanly into valid **`Duration`** instances. However, if the client contract states **`request-timeout` must be greater than `connect-timeout`**, this pair conflicts.

Another example:

~~~yaml
demo:
  retry:
    enabled: true
    initial-delay: 5s
    max-delay: 1s
    max-attempts: 3
~~~

Both **`initial-delay`** and **`max-delay`** are valid on their own. Yet **`initial-delay > max-delay`** violates the retry rule. Or a feature is turned on via **`enabled: true`** while missing a URL required in enabled mode.

This is **cross-field validation**, or **validating relationships across multiple configuration fields**.

This lesson covers:

1. Distinguishing conversion errors, single-field validation, and cross-field validation.
2. Using **`@Validated`** and **`jakarta.validation`** to validate **`@ConfigurationProperties`**.
3. Expressing simple rules with **`@AssertTrue`** on a JavaBean getter.
4. Writing custom class-level constraints with **`@Constraint`** and **`ConstraintValidator`**.
5. Attaching error messages to the right property using **`ConstraintValidatorContext`**.
6. Validating nested objects with **`@Valid`**, handling **`null`**, and modeling enable/disable flags.
7. Testing both valid and invalid configurations using **`ApplicationContextRunner`**.
8. Distinguishing constraints within one object from constraints across multiple configuration beans.
9. Designing fail-fast checks to avoid runtime failures caused by settings that only clash when combined.

Context: **Spring Boot 3.3.x**, **Java 21**, **Jakarta Bean Validation**, and standalone examples that do not depend on live network connections.

## 2. Three Layers to Distinguish

Before writing validation code, separate three concerns:

| Layer | Example | Detected By |
| --- | --- | --- |
| **Type conversion / binding** | **`connect-timeout: abc`** cannot convert to `Duration` | Spring Boot Binder and `ConversionService` |
| **Single-field constraint** | **`max-attempts: 0`** violates minimum 1 | **`@Min(1)`**, **`@NotNull`**, **`@NotBlank`**, etc. |
| **Cross-field constraint** | **`request-timeout <= connect-timeout`** despite valid individual `Duration`s | **`@AssertTrue`**, custom class-level constraint, or dedicated validator |

A clearer illustration:

~~~text
connect-timeout = 5s       -> valid Duration type
request-timeout = 2s       -> valid Duration type
                              but invalid timeout relationship

max-attempts = 0           -> valid int type
                              but violates @Min(1)

connect-timeout = invalid  -> fails right at type conversion
~~~

**Do not put `@Min` or `@Max` on two `Duration` fields thinking that checks their relative ordering.** Single-field validation and relational validation solve different requirements.

The goal of cross-field validation is rejecting configurations that are **inconsistent as a whole**, before business logic ever consumes them.

## 3. Declaring Required Dependencies

In Spring Boot 3.3, Bean Validation constraints live in **`jakarta.validation`**. A compatible implementation must be on the classpath, normally added via **`spring-boot-starter-validation`**.

### 3.1. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

### 3.2. Maven

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

If your project uses **`spring-boot-starter-web`**, do not assume `starter-validation` is pulled in automatically across every version or build setup. Declare the validation dependency explicitly when your project needs it.

Annotations used in this lesson:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.validation.annotation.Validated;
~~~

**`jakarta.validation`** is the proper namespace for Spring Boot 3.3. Old **`javax.validation`** imports from Spring Boot 2.x tutorials should not be copied verbatim into Boot 3.x projects.

## 4. First Step: Creating a Structured Configuration Model

Suppose an HTTP client has these requirements:

- **`base-url`** is required.
- **`connect-timeout`** is required.
- **`request-timeout`** is required.
- Retry has an attempt count and delay bounds.
- **`request-timeout > connect-timeout`**.
- When retry is enabled, **`initial-delay <= max-delay`** and **`max-attempts >= 1`**.

Define a Java record:

~~~java
package com.example.crossfield;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.http-client")
public record HttpClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry) {

    public record Retry(
            boolean enabled,
            Integer maxAttempts,
            Duration initialDelay,
            Duration maxDelay) {
    }
}
~~~

This is the **starting model** used to explain the validation approaches; later sections add constraints to it.

### 4.1. Valid YAML Data

~~~yaml
demo:
  http-client:
    base-url: "https://api.example.invalid"
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      enabled: true
      max-attempts: 3
      initial-delay: 250ms
      max-delay: 3s
~~~

All values use dummy `.invalid` URLs and durations. No live network connection is needed to test binding.

### 4.2. Enabling Configuration Properties

One way to register the type is **`@ConfigurationPropertiesScan`**:

~~~java
package com.example.crossfield;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CrossFieldApplication {

    public static void main(String[] args) {
        SpringApplication.run(CrossFieldApplication.class, args);
    }
}
~~~

An alternative is **`@EnableConfigurationProperties(HttpClientProperties.class)`** on a configuration class. With record constructor binding, use scanning or explicit enabling as supported by Spring Boot, rather than merely annotating the record with **`@Component`**.

### 4.3. Role of `@Validated`

**`@Validated`** on a **`@ConfigurationProperties`** class instructs Spring Boot to run validation with supported constraints.

**`@NotNull`** checks that a value is present; **`@Valid`** tells Bean Validation to descend into nested objects. With binding alone and no validation, the Binder can create objects even when business conditions are violated.

Yet even when both `Duration`s carry **`@NotNull`**, Spring Boot will not infer **`requestTimeout > connectTimeout`**. You must declare the relational rule yourself.

## 5. Approach 1: `@AssertTrue` for a Simple Relationship

**`@AssertTrue`** from Jakarta Bean Validation requires a `boolean`/`Boolean` value to be true. Placed on a JavaBean getter recognized as a property, it can evaluate a condition derived from multiple fields.

Example of a separate, mutable JavaBean:

~~~java
package com.example.crossfield;

import java.time.Duration;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.timeout")
public class TimeoutProperties {

    @NotNull
    private Duration connectTimeout;

    @NotNull
    private Duration requestTimeout;

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }

    @AssertTrue(
        message = "request-timeout must be greater than connect-timeout")
    public boolean isTimeoutOrderValid() {
        if (connectTimeout == null || requestTimeout == null) {
            return true;
        }
        return requestTimeout.compareTo(connectTimeout) > 0;
    }
}
~~~

Valid configuration:

~~~properties
demo.timeout.connect-timeout=2s
demo.timeout.request-timeout=10s
~~~

Invalid configuration:

~~~properties
demo.timeout.connect-timeout=8s
demo.timeout.request-timeout=3s
~~~

**`isTimeoutOrderValid()`** is a boolean getter following JavaBean naming, so Bean Validation recognizes it as a derived property. It needs no setter because we do not want the Binder setting **`timeout-order-valid`** from a config file.

### 5.1. Why Return `true` When Null?

The relational check only makes sense when both `Duration`s exist. **`@NotNull`** on each field is responsible for reporting missing values.

If the method returned `false` when one field was null, operators would see two simultaneous errors:

- Error: **`connect-timeout` must not be null**.
- Error: **invalid timeout order**.

The second message is noisy because no comparison was even possible. Therefore, a good design **skips the relational check when inputs are missing**, letting single-field constraints report missing values first.

### 5.2. Pros and Cons of `@AssertTrue`

Pros:

- No need to write a custom annotation and `ConstraintValidator`.
- Concise for a simple two-field relationship.
- Easy to read and test in small classes.

Limitations:

- The derived boolean method may appear in introspection tools or be treated as a bean property.
- Errors are typically attached to the derived property name like **`timeoutOrderValid`**, not directly to **`requestTimeout`**.
- When there are multiple conditional branches and distinct error messages, a single boolean method becomes awkward.
- For rules reused across multiple types, a custom class-level constraint is easier to maintain.

Use this approach for one or two simple conditions where a combined error message suffices.

## 6. Approach 2: Custom Class-Level Constraint

When comparing multiple fields, reusing a rule, or targeting errors precisely, you can create a **Jakarta Bean Validation constraint** placed on the class/record itself.

Main example: **`request-timeout` must be greater than `connect-timeout`**.

Steps:

1. Create the **`@ValidTimeoutWindow`** annotation.
2. Create **`ConstraintValidator<ValidTimeoutWindow, HttpClientProperties>`**.
3. Place the annotation on **`HttpClientProperties`**.
4. Ensure the class has **`@Validated`** and a validation implementation.
5. Run tests with valid and invalid combinations.

### 6.1. The `@ValidTimeoutWindow` Annotation

~~~java
package com.example.crossfield;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = TimeoutWindowValidator.class)
public @interface ValidTimeoutWindow {

    String message() default
            "request-timeout must be greater than connect-timeout";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

Key elements:

- **`@Target(TYPE)`**: the constraint sits on the whole object rather than an individual field.
- **`@Retention(RUNTIME)`**: keeps the annotation available when the validator runs.
- **`@Constraint(validatedBy = ...)`**: points to the validator class.
- **`message`**: default message when the rule fails.
- **`groups`** and **`payload`**: standard members required of custom Bean Validation constraints.

This annotation is defined in application code, not built into Spring Boot. **`ValidTimeoutWindow`** is purely an illustrative name.

### 6.2. Validator Comparing Two `Duration`s

~~~java
package com.example.crossfield;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class TimeoutWindowValidator
        implements ConstraintValidator<
            ValidTimeoutWindow, HttpClientProperties> {

    @Override
    public boolean isValid(
            HttpClientProperties value,
            ConstraintValidatorContext context) {

        if (value == null) {
            return true;
        }

        if (value.connectTimeout() == null
                || value.requestTimeout() == null) {
            return true;
        }

        boolean valid = value.requestTimeout()
                .compareTo(value.connectTimeout()) > 0;

        if (valid) {
            return true;
        }

        context.disableDefaultConstraintViolation();
        context.buildConstraintViolationWithTemplate(
                "request-timeout must be greater than connect-timeout")
                .addPropertyNode("requestTimeout")
                .addConstraintViolation();

        return false;
    }
}
~~~

The validator has a single job: checking the relationship between **two fields** already bound into `Duration`s.

The expression:

~~~java
requestTimeout.compareTo(connectTimeout) > 0
~~~

means:

~~~text
requestTimeout > connectTimeout
~~~

If actual business rules permit equality, change **`> 0`** to **`>= 0`**. Base that decision on the HTTP client's or business contract—never assume one formula fits every system.

### 6.3. Applying the Constraint to `HttpClientProperties`

~~~java
package com.example.crossfield;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ValidTimeoutWindow
@ConfigurationProperties(prefix = "demo.http-client")
public record HttpClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry) {

    public record Retry(
            boolean enabled,
            Integer maxAttempts,
            Duration initialDelay,
            Duration maxDelay) {
    }
}
~~~

**This is the completed version for the lesson's illustration**, replacing the unconstrained record from section 4. Do not register two versions with the same class name in the same project.

Spring Boot binds fields from Config Data first, then validation inspects the object with already-converted values.

## 7. Attaching Errors to a Specific Property with `ConstraintValidatorContext`

A class-level constraint normally attaches its violation to the **root object**. In some setups, the resulting error states only that the object is invalid without pointing out which field to fix.

This block in the validator:

~~~java
context.disableDefaultConstraintViolation();

context.buildConstraintViolationWithTemplate(
        "request-timeout must be greater than connect-timeout")
        .addPropertyNode("requestTimeout")
        .addConstraintViolation();
~~~

tells Bean Validation to create a violation whose property path points to the Java field **`requestTimeout`**, rather than only the enclosing object.

One benefit is that when an error occurs, operators can easily trace it back to the canonical property:

~~~text
demo.http-client.request-timeout
~~~

The argument to **`addPropertyNode(...)`** should be the Java property name understood by Bean Validation—such as **`requestTimeout`**—not an arbitrary string like **`demo.http-client.request-timeout`**.

**Key takeaway:** when you need to tell operators which specific key to fix, use **`ConstraintValidatorContext`** to build a clear property path.

If an error applies to both fields equally, you can build multiple violations for different property nodes. However, avoid creating redundant identical messages that clutter logs.

## 8. Cross-Field Validation with Nested Objects

A configuration group can contain **`retry`** as a child object.

Requirements:

- **`retry.enabled = false`**: do not enforce active-retry rules.
- **`retry.enabled = true`**: **`max-attempts >= 1`**, and **`initial-delay`** and **`max-delay`** must be present.
- When retry is enabled, **`initial-delay <= max-delay`**.
- Per business policy, both delays must be greater than 0.

This is a conditional rule, not just a static comparison between two numbers.

### 8.1. Using `@AssertTrue` on the Child Record

You can add a boolean check method with clear rules to the nested record:

~~~java
package com.example.crossfield;

import java.time.Duration;
import jakarta.validation.constraints.AssertTrue;

public record RetrySettings(
        boolean enabled,
        Integer maxAttempts,
        Duration initialDelay,
        Duration maxDelay) {

    @AssertTrue(message =
        "When retry is enabled, max-attempts and delay bounds must be valid")
    public boolean isRetryPolicyConsistent() {

        if (!enabled) {
            return true;
        }

        if (maxAttempts == null || maxAttempts < 1
                || initialDelay == null || maxDelay == null) {
            return false;
        }

        if (initialDelay.isNegative()
                || initialDelay.isZero()
                || maxDelay.isNegative()
                || maxDelay.isZero()) {
            return false;
        }

        return initialDelay.compareTo(maxDelay) <= 0;
    }
}
~~~

With this design, when retry is disabled, the method returns **`true`** even if retry fields are omitted. When enabled, it checks everything thoroughly.

If the nested object sits inside a parent record:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public record WrapperProperties(
        @Valid @NotNull RetrySettings retry) {
}
~~~

then **`@Valid`** lets Bean Validation evaluate the constraint inside `RetrySettings`.

**Note:** the standalone **`RetrySettings`** example here illustrates one design option. In your exercise project, update the nested record **`HttpClientProperties.Retry`** with an equivalent method rather than maintaining two duplicate retry types side by side.

### 8.2. Avoid Unconditional `@NotNull` on Fields Only Needed When Enabled

If you put:

~~~java
@NotNull Duration initialDelay
~~~

directly on a configuration where **`enabled = false`**, Bean Validation can fail for missing `initial-delay` even though retry is turned off.

If the contract says those fields are only **required when `enabled = true`**, place that requirement inside the relational constraint or use carefully designed validation groups.

Another option is requiring full retry settings regardless of whether the feature is enabled. Which choice is right depends on your configuration contract. The critical rule is: **never let single-field annotations contradict your enable/disable rules**.

## 9. `@Valid` Traverses Nested Objects; It Does Not Compare Fields Automatically

In a Java record:

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.http-client")
public record HttpClientProperties(
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry) {
}
~~~

**`@Valid`** tells Bean Validation to descend into **`retry`** and evaluate its constraints when the object exists.

**`@NotNull`** states that the `retry` object must exist.

Yet **`@Valid` does not compare `retry.initialDelay` against `retry.maxDelay` on its own**. You still need a constraint on the child class or a custom validator that reads those fields.

Likewise, if a nested object carries constraints while the parent omits **`@Valid`**, validating the parent may fail to descend into the nested type's constraints as you expect.

Spring Boot documentation also highlights placing **`@Valid`** on nested properties to trigger validation consistently even when no child properties are supplied externally. With record constructor binding, if the entire branch is absent the nested object may not be instantiated; combine **`@NotNull`**, default binding, or constructor design per your contract.

## 10. Rules for Nulls, Missing Values, and Validation Order

Cross-field validation must account for three possibilities:

1. **Unbindable data**: e.g., **`connect-timeout: wrong`**.
2. **Bindable data with missing values**: e.g., **`request-timeout`** omitted.
3. **Complete data with invalid relationship**: e.g., **`connect-timeout=9s`**, **`request-timeout=3s`**.

A validator comparing two `Duration`s should typically write:

~~~java
if (value.connectTimeout() == null
        || value.requestTimeout() == null) {
    return true;
}
~~~

This is not ignoring missing errors; **`@NotNull`** annotations report missing values directly.

When data cannot bind at all, the Binder halts or fails before constructing a complete object. Do not rely on a relational validator to catch type conversion failures.

### 10.1. Avoiding `NullPointerException` in Validators

Do not write:

~~~java
return value.requestTimeout()
        .compareTo(value.connectTimeout()) > 0;
~~~

if fields can be null and you have not verified their presence first.

A validator throwing **`NullPointerException`** produces far more confusing diagnostics than a proper constraint violation.

### 10.2. Do Not Confuse Successful Parsing with Valid Values

Spring Boot can bind:

~~~text
connect-timeout = -2s
request-timeout = 0s
~~~

into negative or zero `Duration` objects. If your application requires both to be positive, add explicit validation for that.

Standard **`@Min`** and **`@Positive`** primarily target compatible numeric types; do not place them directly on **`Duration`** assuming a validator will support them. Use a custom constraint, boolean method, or explicit guard logic.

## 11. Conditional Case: URL Required When Feature Is Enabled

Suppose a system has a webhook feature:

~~~yaml
demo:
  webhook:
    enabled: true
    url: ""
~~~

When disabled, the URL can be left blank. When enabled, the URL must be configured.

A record:

~~~java
package com.example.crossfield;

import java.net.URI;
import jakarta.validation.constraints.AssertTrue;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.webhook")
public record WebhookProperties(
        boolean enabled,
        URI url) {

    @AssertTrue(message =
        "url is required when webhook.enabled=true")
    public boolean isWebhookConfigurationValid() {
        return !enabled || url != null;
    }
}
~~~

In this snippet, **`url`** uses **`URI`**; an empty string can convert into an empty `URI` depending on converter/source, so when a real URL with scheme and host is required, validate the contents more thoroughly than checking only for null.

A clearer version when validating text:

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.webhook")
public record WebhookTextProperties(
        boolean enabled,
        String url) {

    @AssertTrue(message = "url must be provided when webhook is enabled")
    public boolean isConfigured() {
        return !enabled || (url != null && !url.isBlank());
    }
}
~~~

These two records are **illustrative options**. In production designs, prefer `URI` paired with a custom validator checking scheme, host, and required security rules.

### 11.1. Do Not Replace a Clear Model with One Giant Regex

A regex on a URL cannot answer all of these rules:

- Is the URL required only when enabled?
- Is HTTP allowed in local environments?
- Is HTTPS mandatory in production?
- Are internal domains permitted?
- Can both a token and username/password be configured together?

These are relational rules; express them with readable models and validators.

## 12. Mutually Exclusive Options: Pick Exactly One Mode

Some systems support two authentication modes:

- Using **`api-key`**.
- Using **`username/password`**.

We want to forbid configuring both at once or configuring neither.

Example record:

~~~java
package com.example.crossfield;

import jakarta.validation.constraints.AssertTrue;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.auth")
public record AuthProperties(
        String apiKey,
        String username,
        String password) {

    @AssertTrue(message =
        "Choose exactly one mechanism: api-key or username/password")
    public boolean isExactlyOneAuthModeConfigured() {

        boolean hasApiKey =
                apiKey != null && !apiKey.isBlank();

        boolean hasUsername =
                username != null && !username.isBlank();

        boolean hasPassword =
                password != null && !password.isBlank();

        boolean hasUserPassword = hasUsername && hasPassword;
        boolean incompletePair = hasUsername != hasPassword;

        if (incompletePair) {
            return false;
        }

        return hasApiKey ^ hasUserPassword;
    }
}
~~~

The **`^`** operator is boolean XOR: true only when exactly one of the two modes is active.

Combinations:

| api-key | username/password | Outcome |
| --- | --- | --- |
| Present | Absent | Valid |
| Absent | Complete | Valid |
| Present | Complete | Invalid |
| Absent | Absent | Invalid |
| Absent | One field missing | Invalid |

**Never print `api-key` or `password` values into logs or validation messages.** When diagnosing, report only which key names are missing or conflicting.

This example uses `String` to illustrate mutual exclusion. In real applications, loading/storing credentials must follow proper secret management and access controls.

## 13. Cross-Field Constraints Across Different Configuration Groups

Example:

~~~text
demo.http-client.request-timeout = 10s
demo.worker.job-timeout          = 5s
~~~

A business rule may require **`job-timeout > request-timeout`**.

If each group binds to a separate class:

~~~java
@ConfigurationProperties(prefix = "demo.http-client")
public record HttpClientProperties(Duration requestTimeout) {
}

@ConfigurationProperties(prefix = "demo.worker")
public record WorkerProperties(Duration jobTimeout) {
}
~~~

then a custom constraint on **`HttpClientProperties`** should not inject **`WorkerProperties`**, a data source, or a service just to compare values. Spring Boot documentation recommends keeping configuration properties focused on **`Environment`** binding; configuration beans are created very early.

A clean alternative is a dedicated component that validates **after both configuration beans are created**:

~~~java
package com.example.crossfield;

import org.springframework.stereotype.Component;

@Component
public class StartupConfigurationGuard {

    public StartupConfigurationGuard(
            HttpClientProperties client,
            WorkerProperties worker) {

        if (client.requestTimeout() == null
                || worker.jobTimeout() == null) {
            throw new IllegalStateException(
                    "Both request-timeout and job-timeout are required");
        }

        if (worker.jobTimeout()
                .compareTo(client.requestTimeout()) <= 0) {
            throw new IllegalStateException(
                    "demo.worker.job-timeout must be greater than "
                    + "demo.http-client.request-timeout");
        }
    }
}
~~~

Here, **`StartupConfigurationGuard`** is a Spring bean created during `ApplicationContext` startup. If the condition fails, bean creation fails and can halt application startup.

**This option fits rules spanning multiple beans**, rather than replacing a class-level constraint on a single object. If you need to guarantee this check executes before other beans initialize using that configuration, establish explicit bean dependencies/initialization ordering rather than relying on incidental singleton creation order.

### 13.1. Why Not Inject Services Into a `ConstraintValidator`?

Some Bean Validation providers support creating validators integrated with Spring DI. However, configuration validation during boot happens early; adding dependencies on databases, network clients, or business services can introduce complex lifecycle issues, circular dependencies, or side effects.

**Prefer pure validators** that only compare bound values. When a rule truly spans multiple subsystems, enforce it in a dedicated orchestration layer or startup guard once dependencies are ready.

## 14. Spring `Validator` Instead of a Jakarta Class-Level Constraint

Beyond Jakarta Bean Validation, Spring Boot also lets you integrate a custom **`org.springframework.validation.Validator`** for configuration properties.

Basic Spring `Validator` example:

~~~java
package com.example.crossfield;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class HttpClientSpringValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return HttpClientProperties.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        HttpClientProperties value =
                (HttpClientProperties) target;

        if (value.connectTimeout() == null
                || value.requestTimeout() == null) {
            return;
        }

        if (value.requestTimeout()
                .compareTo(value.connectTimeout()) <= 0) {
            errors.rejectValue(
                    "requestTimeout",
                    "timeout.order",
                    "request-timeout must be greater than connect-timeout");
        }
    }
}
~~~

In Spring Boot, a custom bean **named `configurationPropertiesValidator`** is automatically used to validate configuration properties. Because the validator is created **very early** in the lifecycle, Spring Boot documentation recommends declaring the **`@Bean`** factory method as **`static`**:

~~~java
package com.example.crossfield;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.Validator;

@Configuration(proxyBeanMethods = false)
public class ConfigValidationSetup {

    @Bean
    public static Validator configurationPropertiesValidator() {
        return new HttpClientSpringValidator();
    }
}
~~~

**Be careful with scope**: this bean participates in checking configuration properties across the context; **`supports(...)`** must return true only for intended types to avoid `ClassCastException` or applying rules to unrelated groups.

When a rule applies to a single type, a **Jakarta class-level constraint** on that type is usually clearer and easier to reuse. Use a Spring `Validator` when the project specifically prefers it or integrates with Spring's `Errors` infrastructure.

**Do not register all approaches simultaneously** in the same demo; each is an alternative solution.

## 15. Time Relationships: Which Condition Is Actually Right?

Not every system defines timeouts identically:

- **`connect-timeout`**: limit for establishing the TCP/TLS connection.
- **`read-timeout`**: limit for a read operation or idle gap between packets, depending on the client.
- **`request-timeout`**: overall request limit or higher-level call timeout.
- **`retry.initial-delay`**, **`retry.max-delay`**: wait intervals between attempts.

The rule **`request-timeout > connect-timeout`** makes sense for **certain client designs**, yet not every HTTP library models timeouts with those semantics.

Before writing a validator, determine:

1. Do the two fields govern the same pipeline or independent phases?
2. Should the comparison be **`>`**, **`>=`**, or simply non-negative?
3. Does **`0`** carry special meaning such as infinite or disabled?
4. Do you need to compute a total retry budget?
5. When a feature is disabled, does the condition still apply?
6. What should the upper bound be?

Example retry budget limit:

~~~text
total-budget >= request-timeout + estimated-retry-delays
~~~

This is an advanced rule requiring **`Duration`** arithmetic, overflow guards for huge values, and knowledge of the retry strategy (exponential backoff, jitter, max attempts).

Never invent a constraint solely because an inequality looks numerically neat if it contradicts how the consuming library interprets those timeouts.

## 16. Using `@DefaultValue` Without Masking Relational Errors

Spring Boot constructor binding supports **`@DefaultValue`**:

~~~java
package com.example.crossfield;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.timeouts")
public record DefaultTimeoutProperties(
        @DefaultValue("2s") Duration connectTimeout,
        @DefaultValue("10s") Duration requestTimeout) {
}
~~~

Defaults populate the model when config sources omit keys. However, if an operator overrides just one:

~~~text
demo.timeouts.connect-timeout=15s
~~~

then the final pair becomes:

~~~text
connectTimeout = 15s
requestTimeout = 10s
~~~

Each value is valid individually, yet **their relationship is invalid**. Even with defaults, class-level constraints remain essential.

### 16.1. Defaults Do Not Replace Validation

Good defaults make local development easy; good constraints guarantee the final combination stays valid after every environment override.

Do not invent dummy defaults for settings operators must supply, such as production URLs or credentials.

## 17. Checking Combinations Across Profiles and Multiple Sources

Spring Boot loads profile-specific configuration:

**`application.yml`**:

~~~yaml
demo:
  http-client:
    connect-timeout: 2s
    request-timeout: 10s
~~~

**`application-prod.yml`**:

~~~yaml
demo:
  http-client:
    connect-timeout: 8s
~~~

Run command:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

When no other source overrides it, **`connect-timeout=8s`** and **`request-timeout=10s`**, so the relationship remains valid.

But if an operator passes:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --demo.http-client.request-timeout=5s
~~~

then the final values become **`8s`** and **`5s`**, violating the rule.

**Validation must run against the final effective post-binding values**, rather than checking individual YAML files in isolation. This is a key reason to attach cross-field validation to **`@ConfigurationProperties`**.

### 17.1. Corresponding Environment Variables

~~~text
demo.http-client.connect-timeout
    -> DEMO_HTTPCLIENT_CONNECTTIMEOUT

demo.http-client.request-timeout
    -> DEMO_HTTPCLIENT_REQUESTTIMEOUT
~~~

Per Spring Boot's environment binding rules:

- **`.`** becomes **`_`**.
- **`-`** is removed.
- Characters become uppercase.

**`DEMO_HTTP_CLIENT_CONNECT_TIMEOUT`** is not the canonical conversion of **`demo.http-client.connect-timeout`**. Do not insert extra underscores between kebab-case words.

## 18. Scaling Up with Multiple Optional Fields

An object might have:

~~~text
cache.enabled
cache.ttl
cache.max-size
cache.eviction-policy
~~~

Example requirements:

- When cache is **disabled**, TTL/size values may be omitted.
- When cache is **enabled**, TTL must be positive and `max-size > 0`.
- If eviction-policy is **time-based**, TTL is required.
- If eviction-policy is **size-based**, `max-size` is required.

In this situation, do not force `@NotNull` unconditionally on fields required only in specific modes.

A clean strategy:

1. Bind an object holding the mode/flag and optional fields.
2. Validate independent values (e.g., valid enum constant).
3. Use a class-level constraint or **`@AssertTrue`** to verify compatibility between mode and fields.
4. Return error messages naming the keys and violated condition.

As logic grows, split into focused validators or domain config classes. Never dump every rule into one giant method that cannot be unit tested cleanly.

## 19. Testing with `ApplicationContextRunner`

**`ApplicationContextRunner`** is a Spring Boot test utility that creates a small `ApplicationContext` with explicit property values. It is ideal for testing configuration properties, validation, and startup failures without launching an entire web app.

Assume you have the classes shown earlier:

- **`HttpClientProperties`** annotated with **`@Validated`**, **`@ValidTimeoutWindow`**, and nested `Retry`.
- **`ValidTimeoutWindow`**.
- **`TimeoutWindowValidator`**.
- **`spring-boot-starter-validation`** and **`spring-boot-starter-test`** dependencies.

### 19.1. Valid and Invalid Tests

~~~java
package com.example.crossfield;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class HttpClientPropertiesValidationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(HttpClientProperties.class)
    static class TestConfiguration {
    }

    @Test
    void acceptsValidTimeoutOrder() {
        runner.withPropertyValues(
                "demo.http-client.base-url=https://api.example.invalid",
                "demo.http-client.connect-timeout=2s",
                "demo.http-client.request-timeout=10s",
                "demo.http-client.retry.enabled=true",
                "demo.http-client.retry.max-attempts=3",
                "demo.http-client.retry.initial-delay=250ms",
                "demo.http-client.retry.max-delay=3s"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            HttpClientProperties properties =
                    context.getBean(HttpClientProperties.class);

            assertThat(properties.connectTimeout())
                    .isEqualTo(Duration.ofSeconds(2));
            assertThat(properties.requestTimeout())
                    .isEqualTo(Duration.ofSeconds(10));
        });
    }

    @Test
    void rejectsRequestTimeoutShorterThanConnectTimeout() {
        runner.withPropertyValues(
                "demo.http-client.base-url=https://api.example.invalid",
                "demo.http-client.connect-timeout=8s",
                "demo.http-client.request-timeout=3s",
                "demo.http-client.retry.enabled=false",
                "demo.http-client.retry.max-attempts=1",
                "demo.http-client.retry.initial-delay=100ms",
                "demo.http-client.retry.max-delay=1s"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
    }
}
~~~

In the second test, both `Duration`s are syntactically valid, yet **`@ValidTimeoutWindow`** rejects the invalid relationship.

**No live API connection needed**: URLs using the **`.invalid`** domain are only bound into `URI`, never called over HTTP.

### 19.2. Matrix Testing Multiple Combinations

Build a test matrix:

| connect-timeout | request-timeout | Expected |
| --- | --- | --- |
| **`1s`** | **`10s`** | Pass |
| **`3s`** | **`3s`** | Fail if strict greater-than required |
| **`8s`** | **`2s`** | Fail |
| Missing | **`10s`** | Fail via `@NotNull` |
| **`bad-value`** | **`10s`** | Fail during bind/conversion |

For retry:

| enabled | initial-delay | max-delay | max-attempts | Expected |
| --- | --- | --- | --- | --- |
| false | absent | absent | absent | Passes if design permits |
| true | 100ms | 2s | 3 | Pass |
| true | 5s | 1s | 3 | Fail |
| true | 100ms | 2s | 0 | Fail |
| true | absent | 2s | 3 | Fail |

**This table is a test contract for your validation design**, not a mandatory specification for every Spring Boot HTTP client.

## 20. Testing Validators Directly with Jakarta `Validator`

Not every test needs to spin up a Spring Boot context. If the validator is pure Java, you can unit test its rules directly via Jakarta Bean Validation.

Example using **`jakarta.validation.Validation`**:

~~~java
package com.example.crossfield;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class TimeoutWindowConstraintTest {

    @Test
    void detectsInvalidTimeoutWindow() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            HttpClientProperties properties =
                    new HttpClientProperties(
                        URI.create("https://api.example.invalid"),
                        Duration.ofSeconds(8),
                        Duration.ofSeconds(3),
                        new HttpClientProperties.Retry(
                            false, null, null, null));

            var violations = validator.validate(properties);

            assertThat(violations).isNotEmpty();
            assertThat(violations.stream()
                    .anyMatch(v -> v.getMessage()
                        .contains("request-timeout")))
                    .isTrue();
        }
    }
}
~~~

This tests Bean Validation on manually constructed objects without testing YAML or env binding. Therefore, keep **both test layers** for critical configuration: one verifying the validator logic, and one verifying Spring Boot binding plus validation end-to-end.

If a custom validator depends on Spring-injected services, standalone tests using **`Validation.buildDefaultValidatorFactory()`** will lack that injection wiring. That is another reason to keep configuration validators pure.

## 21. Distinguishing Bind Errors from Validation Errors at Startup

An invalid configuration can halt startup at different stages.

### 21.1. Type Mismatch

~~~yaml
demo:
  http-client:
    connect-timeout: not-a-duration
~~~

The Binder cannot construct a `Duration` from the invalid string, resulting in a conversion/binding failure.

### 21.2. Missing Required Field

~~~yaml
demo:
  http-client:
    request-timeout: 10s
~~~

If the record defines **`@NotNull Duration connectTimeout`** with validation enabled, the error indicates the missing required field.

### 21.3. Invalid Relationship

~~~yaml
demo:
  http-client:
    connect-timeout: 8s
    request-timeout: 3s
~~~

Both values convert to `Duration`; the custom constraint detects the relational violation.

Instead of stopping at the outer `"Failed to bind properties"` line, read the cause chain, property path, and constraint message.

Avoid asserting exact exception class names across versions; a durable integration test asserts context **`hasFailed()`**, while a validator unit test asserts specific constraint messages.

## 22. When to Use `@AssertTrue`, Custom Constraints, or a Startup Guard?

| Scenario | Usually Best Choice |
| --- | --- |
| One simple boolean relationship inside a small object | **`@AssertTrue`** on an appropriate getter |
| Need to attach the violation to a specific field | **Class-level constraint + `ConstraintValidatorContext`** |
| Want to reuse the same rule across multiple types | Reusable custom annotation |
| Conditional rule inside nested config | Constraint on nested object, cascaded via **`@Valid`** |
| Relationship between two independent configuration beans | Startup guard or dedicated validation orchestration |
| Third-party configuration class you cannot annotate | Spring `Validator` or external check class |
| Pure unit testing without a Spring context | Jakarta `Validator` on Java objects |
| Testing full binding and fail-fast startup | **`ApplicationContextRunner`** |

There is no reason to stack multiple mechanisms for one relationship. Pick the simplest approach that expresses the contract cleanly and produces actionable messages.

## 23. Common Mistakes

### Mistake 1: Validating Only Individual Fields, Ignoring Relationships

**`@NotNull`** on two timeouts does not guarantee `request-timeout` exceeds `connect-timeout`. Add a relational rule.

### Mistake 2: Forcing `@Min`/`@Max` Onto `Duration`

Numeric constraints do not support `Duration` by default; check provider support or use a fitting constraint.

### Mistake 3: Forgetting `@Validated`

If a **`@ConfigurationProperties`** class is not wired into validation, constraints may never execute as expected.

### Mistake 4: Missing Validation Implementation

Importing `jakarta.validation` annotations without a runtime implementation on the classpath prevents Bean Validation from running. Add `starter-validation` in standard Spring Boot projects.

### Mistake 5: Forgetting `@Valid` on Nested Objects

Validating the parent does not automatically check nested object constraints. Use **`@Valid`** to cascade.

### Mistake 6: Validator Throwing `NullPointerException`

Validators should skip the relational check when inputs are missing—letting **`@NotNull`** report absence—or explicitly guard against nulls.

### Mistake 7: Constraining Optional Fields Unconditionally

If retry is off and delays are unnecessary, putting **`@NotNull`** on delays will reject valid business configurations. Align annotations with enable/disable semantics.

### Mistake 8: Message Does Not State the Relationship

**"invalid configuration"** is too vague. Say **"request-timeout must be greater than connect-timeout"**, without printing sensitive values.

### Mistake 9: Adding Network Dependencies to Validators

Config validators run early. Never open DB or HTTP connections inside validation methods; inspect only bound values.

### Mistake 10: Testing Only One Valid Combination

Also test equal boundary values, missing fields, disabled mode, enabled mode, wrong types, and env/CLI overrides.

### Mistake 11: Comparing Strings Instead of `Duration`s

**`"10s"`** and **`"2s"`** cannot be compared lexicographically. Bind to `Duration` and use **`compareTo(...)`**.

### Mistake 12: Checking Individual YAML Files and Ignoring Overrides

Final settings combine base files, profile-specific files, environment variables, and command-line flags. Validation must inspect the bound object built from effective sources.

### Mistake 13: Relying on Implicit Bean Initialization Order

For rules spanning two configuration beans, a startup guard needs explicit dependencies so other beans cannot consume invalid settings before the guard runs. Never rely on accidental singleton initialization order.

### Mistake 14: Treating Bean Validation as a Cure-All for Business Rules

Rules depending on live DB state, external APIs, or dynamic runtime data do not belong in configuration-properties validation. Separate pure config validation from readiness/integration checks in the right lifecycle phase.

## 24. Practice Exercises

### Exercise A — Comparing Two Timeouts

1. Set **`demo.http-client.connect-timeout=2s`** and **`request-timeout=10s`**.
2. Write **`@AssertTrue`** or a custom constraint for `requestTimeout > connectTimeout`.
3. Change `request-timeout` to **`1s`**.
4. Observe context startup failing.
5. Restore **`10s`**.

Result: fields can be type-valid yet relationally invalid.

### Exercise B — Replacing `@AssertTrue` with a Class-Level Constraint

1. Create **`@ValidTimeoutWindow`**.
2. Write **`ConstraintValidator`** using **`Duration.compareTo`**.
3. Use **`addPropertyNode("requestTimeout")`**.
4. Re-run with the invalid configuration.

Result: validation pinpoints the exact relevant field.

### Exercise C — Conditional Retry

1. Define **`retry.enabled`**, **`max-attempts`**, **`initial-delay`**, and **`max-delay`**.
2. When `enabled=false`, allow retry fields to be omitted if desired by contract.
3. When `enabled=true`, require positive delays, `maxAttempts >= 1`, and `initialDelay <= maxDelay`.
4. Test all branches.

Result: conditional validation beats putting unconditional `@NotNull` everywhere.

### Exercise D — Environment Override

1. Declare valid timeouts in **`application.yml`**.
2. Set **`DEMO_HTTPCLIENT_CONNECTTIMEOUT=8s`**.
3. Supply a lower `request-timeout` via command-line flag or profile.
4. Observe validation rejecting the final combination.

Result: fail fast before any live client uses inconsistent timeouts.

### Exercise E — Testing Without a Server

1. Use **`ApplicationContextRunner`** with `@EnableConfigurationProperties`.
2. Write success and failure tests.
3. Assert **`hasNotFailed()`** for valid config.
4. Assert **`hasFailed()`** for an invalid relationship.
5. Use standalone `Validator` to verify the violation message.

Result: catch misconfigurations early with no API, DB, or message broker needed.

### Exercise F — Relationship Across Two Prefixes

1. Create groups **`demo.http-client`** and **`demo.worker`**.
2. Define the rule `worker jobTimeout > client requestTimeout`.
3. Write a startup guard taking both configuration beans.
4. Test valid and invalid combinations.
5. Establish explicit dependency ordering if a service requires the guard to run first.

Result: cross-group validation works cleanly without turning a configuration properties class into an orchestration service.

## 25. Cross-Field Validation Design Checklist

Before shipping a constraint, verify:

1. What is the exact business relationship?
2. Are all fields in one object or across multiple configuration beans?
3. Is the relationship **`>`**, **`>=`**, **`<`**, **`<=`**, or mutually exclusive?
4. When a field is missing, who reports it: **`@NotNull`** or the custom constraint?
5. When the feature is disabled, does the condition still apply?
6. For `Duration`, do zero and negative values carry special meaning?
7. Have values already bound into the right Java types before comparison?
8. Should the violation attach to a specific property node?
9. Does the error message explain which key or relationship to fix?
10. Is the validator pure, free of I/O or runtime infrastructure dependencies?
11. Do nested objects carry **`@Valid`** when cascading is needed?
12. Is the properties type registered via scanning or explicit enabling?
13. Is the Bean Validation dependency included?
14. Do tests cover boundaries, missing data, and environment overrides?
15. Is there any risk of leaking secrets in messages or logs?
16. Does fail-fast execution occur before dependent features start operating?

## 26. Summary

- **Single-field validation** cannot catch conflicting combinations of individually valid settings.
- **`@ConfigurationProperties`** paired with **`@Validated`** validates configuration after binding into Java objects.
- **`@AssertTrue`** works well for a simple boolean condition derived from multiple fields.
- **Custom class-level constraints** with **`@Constraint`** and **`ConstraintValidator`** fit complex or reusable rules.
- **`ConstraintValidatorContext.addPropertyNode(...)`** targets violations at a specific field rather than only the whole object.
- **`@Valid`** cascades validation into nested objects; it does not infer relational rules automatically.
- Validators should handle nulls intentionally to avoid duplicate errors and side effects.
- Conditional relationships should account for flags like **`enabled`** instead of putting unconditional `@NotNull` on every field.
- Constraints spanning multiple configuration beans belong in a startup guard or dedicated orchestration layer.
- **`ApplicationContextRunner`** and Jakarta `Validator` let you test both full binding and isolated constraint logic.
- Validation must run against **effective values after all sources are resolved**, not isolated YAML files.

## Official References

- Spring Boot 3.3 — Externalized Configuration, *@ConfigurationProperties Validation* and *Type-safe Configuration Properties* sections: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Jakarta Bean Validation 3.0 — Specification: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation API — `@AssertTrue`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/asserttrue
- Jakarta Validation API — `ConstraintValidator` and `ConstraintValidatorContext`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintvalidator
- Spring Boot 3.3 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html