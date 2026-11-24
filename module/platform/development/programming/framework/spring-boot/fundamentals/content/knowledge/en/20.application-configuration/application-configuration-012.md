# `@Validated` and Detecting Invalid Configuration at Startup

Spring Boot allows configuring an application from `application.yml`, `application.properties`, environment variables, command-line arguments, and many other sources. These values often determine how services connect, processing limits, timeouts, or enabled features.

However, the fact that a value is **readable** does not mean it is **valid**. A blank endpoint, a max connection count of 0, or an out-of-range retry setting can cause failures that surface only after the application receives its first request. Spring Boot combines `@ConfigurationProperties` with `@Validated` and Jakarta Bean Validation to detect many of these errors right when configuration beans are created.

## 1. Distinguishing present, bindable, and valid configuration

Consider a notification service. It needs these properties:

~~~yaml
app:
  notifications:
    sender: no-reply@example.test
    gateway: https://notify.example.test
    max-batch-size: 20
    retry:
      max-attempts: 3
      delay: 2s
~~~

There are three distinct levels of checks:

1. **Reading values:** Spring Boot looks up `app.notifications.max-batch-size` across configuration sources by precedence.
2. **Binding and type conversion:** the Binder converts `20` to an integer, `2s` to a `Duration`, and the URL string to a `URI`.
3. **Validation:** business rules verify that `max-batch-size` is between 1 and 100, `sender` is not blank, and `retry.max-attempts` falls within the allowed range.

For example, `max-batch-size: abc` fails at the type conversion step, before `@Min` can even evaluate. By contrast, `max-batch-size: 0` converts to `int` cleanly yet fails the value constraint.

`@Validated` activates that third check for `@ConfigurationProperties` beans; it does not replace the Binder or input format checks.

## 2. Required annotations and dependencies

To use Jakarta Bean Validation constraints with Spring Boot, projects typically add the validation starter.

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

The starter provides the Bean Validation API and an appropriate provider, typically Hibernate Validator. Without a provider, merely placing constraint annotations in code is insufficient to guarantee values are validated as intended.

The annotations come from different packages:

| Component | Package | Role |
|---|---|---|
| `@ConfigurationProperties` | `org.springframework.boot.context.properties` | Binds a property group into a Java object |
| `@Validated` | `org.springframework.validation.annotation` | Requests validation when binding configuration properties |
| `@NotBlank`, `@NotNull`, `@Min`, `@Max` | `jakarta.validation.constraints` | Declares constraints |
| `@Valid` | `jakarta.validation` | Cascades validation into nested objects |
| `@ConfigurationPropertiesScan` | `org.springframework.boot.context.properties` | Scans and registers configuration properties classes |
| `@EnableConfigurationProperties` | `org.springframework.boot.context.properties` | Explicitly registers one or more configuration properties classes |

In Spring Boot 3, Bean Validation uses the `jakarta.validation.*` namespace. Older guides using `javax.validation.*` belong to the legacy Java EE ecosystem and should not be copied verbatim into Boot 3 applications.

## 3. Complete example with @ConfigurationProperties and @Validated

Define a Java record to hold notification configuration:

~~~java
package com.example.notifications.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.notifications")
public record NotificationProperties(
        @NotBlank String sender,
        @NotNull URI gateway,
        @Min(1) @Max(100) int maxBatchSize,
        @Valid @NotNull Retry retry
) {

    public record Retry(
            @Min(0) @Max(5) int maxAttempts,
            @NotNull Duration delay
    ) {
    }
}
~~~

`NotificationProperties` holds configuration data rather than notification delivery logic. Each property has an appropriate constraint:

- `sender`: uses `@NotBlank` because the string must not be `null`, empty, or whitespace-only.
- `gateway`: uses `@NotNull` because the endpoint must be supplied. Type `URI` also requires binding to convert from the string.
- `maxBatchSize`: uses `@Min(1)` and `@Max(100)` to bound batch size.
- `retry`: uses `@NotNull` to require the retry configuration object and `@Valid` to validate its inner fields.
- `maxAttempts`: allows 0 when the application disables retries, up to a maximum of 5.
- `delay`: must not be missing; this example does not yet constrain the duration to be positive.

For a record with one constructor matching its components, Spring Boot supports constructor binding. Values are passed to the constructor when the configuration properties bean is created, avoiding setter boilerplate.

### Registering the configuration properties bean

Merely defining the record does not automatically register it as a Spring bean. You can enable `@ConfigurationPropertiesScan`:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class NotificationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotificationApplication.class, args);
    }
}
~~~

Or register this class explicitly from a configuration class:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {
}
~~~

Choose one appropriate registration approach; there is no need to use both in the same application.

Once registered, the bean can be injected into services as usual:

~~~java
import org.springframework.stereotype.Service;

@Service
public class NotificationSender {

    private final NotificationProperties properties;

    public NotificationSender(NotificationProperties properties) {
        this.properties = properties;
    }

    public int batchLimit() {
        return properties.maxBatchSize();
    }
}
~~~

The service simply receives a strongly typed configuration object. It does not need to locate configuration sources, convert `String` to `Duration`, or duplicate value checks.

## 4. What happens when configuration is invalid?

Suppose `application.yml` contains:

~~~yaml
app:
  notifications:
    sender: "  "
    gateway: https://notify.example.test
    max-batch-size: 0
    retry:
      max-attempts: 9
      delay: 1s
~~~

All values convert to their target Java types cleanly. However:

- `sender` fails `@NotBlank`.
- `max-batch-size` fails `@Min(1)`.
- `retry.max-attempts` fails `@Max(5)`.

When Spring Boot creates and binds `NotificationProperties`, validation detects these violations. Context startup normally fails, preventing the application from reaching a running state.

The exact message format depends on the Spring Boot version, validation provider, and constraint types. Semantically, the failure details typically convey information such as:

~~~text
Binding to target NotificationProperties failed

Property: app.notifications.sender
Value: "  "
Reason: must not be blank

Property: app.notifications.max-batch-size
Value: 0
Reason: must be greater than or equal to 1

Property: app.notifications.retry.max-attempts
Value: 9
Reason: must be less than or equal to 5
~~~

This is an **illustrative summary of the error contents**, not a verbatim guarantee of a specific stack trace. In real logs, Spring Boot may include bean names, nested causes, source files, and property locations when origin metadata is available.

The key value is that errors are caught **during configuration bean binding and creation**, before dependent business services begin operating on invalid values.

### When might errors not appear immediately at startup?

In standard applications, non-lazy singletons are instantiated during context refresh, so invalid configuration usually fails startup. However, if a configuration properties bean is marked lazy and not requested during startup, binding/validation can be deferred until the bean is first requested.

If your requirement is **fail fast at startup**, ensure mandatory configuration beans are registered and created during regular startup. Do not confuse `@Validated` with an eager linter scanning every key in every configuration file the moment the JVM launches.

## 5. @NotNull, @NotBlank, @NotEmpty, and primitive types

Three annotations are often confused when validating strings and collections:

| Constraint | What it checks | Example usage |
|---|---|---|
| `@NotNull` | Value must not be `null` | `URI`, `Duration`, nested objects |
| `@NotEmpty` | Not `null` and size or length is non-zero | Collections, maps, strings |
| `@NotBlank` | String is not `null`, not empty, and not whitespace-only | Names, hosts, identifiers |

For example:

~~~java
@NotNull
URI gateway;

@NotBlank
String sender;

@NotEmpty
List<String> allowedRegions;
~~~

`@NotBlank` is not a general-purpose annotation for all types; use it for `CharSequence`.

### Note on int, boolean, and primitive types

A primitive `int` field cannot be `null`. If the property is omitted, its value may end up as 0 after binding, so `@NotNull` on `int` does not catch missing configuration.

Instead, place range constraints:

~~~java
@Min(1)
@Max(100)
int maxBatchSize;
~~~

If you need to distinguish **property omitted** from **explicitly set to 0**, use a wrapper type:

~~~java
@NotNull
@Min(0)
Integer maxAttempts;
~~~

With `Integer`, `null` has a distinct meaning and `@NotNull` catches missing values. Your choice of data type should reflect the actual requirement: mandatory setting, defaulted setting, or optional setting.

## 6. Validating nested objects with @Valid

Configuration is not always flat. For instance, `app.notifications.retry` holds multiple related fields.

If you only put constraints inside `Retry` without telling the validator to descend into the object, nested rules may not run as expected. `@Valid` is Jakarta Bean Validation's cascading validation mechanism:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.notifications")
public record NotificationProperties(
        @NotBlank String sender,
        @Valid @NotNull Retry retry
) {

    public record Retry(
            @Min(0) @Max(5) int maxAttempts,
            @NotNull Duration delay
    ) {
    }
}
~~~

The two annotations on `retry` have distinct roles:

- `@NotNull` requires the `Retry` object itself to be present.
- `@Valid` requires validating the constraints inside `Retry` after it is bound.

`@Valid` alone does not treat `null` as invalid, because Bean Validation by default does not cascade into `null` references. When a nested object is mandatory, pair it with `@NotNull` as shown.

### Validating elements inside lists

For configuration containing lists, you can place constraints on both the collection and its elements:

~~~java
import java.util.List;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

public record RegionProperties(
        @NotEmpty List<@NotBlank String> regions
) {
}
~~~

`@NotEmpty` requires the list to contain at least one element. `List<@NotBlank String>` requires each string in the list to be non-empty and not whitespace-only.

If a list holds objects with their own constraints, use `@Valid` to cascade into each element. This structures multi-layer validation cleanly for complex configurations.

## 7. Validation does not replace type conversion

Spring Boot can bind many data types directly:

~~~yaml
app:
  notifications:
    gateway: https://notify.example.test
    max-batch-size: 30
    retry:
      max-attempts: 2
      delay: 750ms
~~~

The Binder converts:

- `https://notify.example.test` to `URI`.
- `30` to `int`.
- `750ms` to `Duration`.

If an operator sets:

~~~yaml
app:
  notifications:
    max-batch-size: several
~~~

`several` cannot convert to `int`. Startup can fail with a binding error before Bean Validation ever checks `@Min` or `@Max`.

Similarly, a malformed URI fails conversion; a syntactically valid URI that violates a business rule (such as requiring HTTPS) may need an additional constraint.

Distinguishing the two failure categories guides tool selection:

- **Wrong type or syntax:** check property name, data format, and conversion.
- **Right type, invalid rule:** use Jakarta Bean Validation, custom constraints, or cross-field consistency checks.

A missing property usually does not trigger a conversion error if Java can accept `null` or a default value. If the property is mandatory, declare the appropriate constraint.

## 8. Checking more complex rules

Standard constraints handle simple rules well:

~~~java
@NotBlank
String sender;

@Min(1)
@Max(100)
int maxBatchSize;

@Pattern(regexp = "[a-z0-9-]+")
String tenantCode;
~~~

When you need to compare multiple fields or check domain-specific rules, you can build a custom Bean Validation constraint and validator.

For example, an internal library might require timeouts to be positive, endpoints to use HTTPS, or two authentication fields to appear together. Such rules are not always expressible with `@NotNull` and `@Min` alone.

A simple option for checking a derived property rule is `@AssertTrue`:

~~~java
import java.time.Duration;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

public record RetryOptions(@NotNull Duration delay) {

    @AssertTrue(message = "delay must be greater than zero")
    public boolean isDelayPositive() {
        return delay != null
                && !delay.isZero()
                && !delay.isNegative();
    }
}
~~~

`isDelayPositive()` is a boolean getter evaluated by Bean Validation. In an enclosing configuration properties class, you still need `@Valid` so the validator reaches `RetryOptions`.

For complex logic or errors tied to multiple fields, custom class-level constraints are easier to extend and test. Keep validation focused on **configuration validity**, not on reaching out to network services.

### Do not call external systems inside constraints

Never use a configuration validator to make slow HTTP requests or check whether a database is online. Validation runs during startup, so transient infrastructure hiccups could prevent the application from booting.

Runtime checks for external dependencies belong in dedicated mechanisms such as health indicators, readiness probes, runners, or connection logic with bounded timeouts and retries.

## 9. Source precedence still applies

Validation does not check every stale copy of a value across every property source individually. It validates the final bound values after Spring Boot resolves property-source precedence.

Suppose the packaged file has:

~~~yaml
app:
  notifications:
    max-batch-size: 20
~~~

An operator overrides it via an environment variable:

~~~bash
APP_NOTIFICATIONS_MAXBATCHSIZE=0
~~~

Because this environment variable has higher precedence than the file, the Binder receives `0` and `@Min(1)` fails even though `application.yml` contains a valid `20`.

Conversely, if a classpath file holds an invalid value while a higher-precedence source supplies a valid replacement, the bean can bind cleanly. What gets validated is the **final winning value** for the bean, not every value that appeared anywhere.

In Spring Boot, converting a property name to an environment variable typically replaces dots with underscores, removes dashes, and uppercases characters. For instance, `app.notifications.max-batch-size` becomes `APP_NOTIFICATIONS_MAXBATCHSIZE`.

If the application reads the wrong value, inspect active profiles, external files, environment variables, and command-line arguments before concluding that the validator is broken.

## 10. Testing startup failures with ApplicationContextRunner

An application can have dozens of configuration properties. Rather than booting the entire server to test every edge case, use `ApplicationContextRunner` from Spring Boot Test to construct a minimal context and inspect its state.

Example using `NotificationProperties` above:

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class NotificationPropertiesTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ValidationAutoConfiguration.class
                    ))
                    .withUserConfiguration(PropertiesConfig.class);

    @Test
    void validConfigurationStarts() {
        runner.withPropertyValues(
                "app.notifications.sender=no-reply@example.test",
                "app.notifications.gateway=https://notify.example.test",
                "app.notifications.max-batch-size=20",
                "app.notifications.retry.max-attempts=3",
                "app.notifications.retry.delay=2s"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(NotificationProperties.class);

            NotificationProperties properties =
                    context.getBean(NotificationProperties.class);

            assertThat(properties.maxBatchSize()).isEqualTo(20);
        });
    }

    @Test
    void invalidBatchSizePreventsStartup() {
        runner.withPropertyValues(
                "app.notifications.sender=no-reply@example.test",
                "app.notifications.gateway=https://notify.example.test",
                "app.notifications.max-batch-size=0",
                "app.notifications.retry.max-attempts=3",
                "app.notifications.retry.delay=2s"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(NotificationProperties.class)
    static class PropertiesConfig {
    }
}
~~~

This test loads `ValidationAutoConfiguration` to provide validation infrastructure in the minimal context when a provider is on the classpath. In the main application, the validation starter and Spring Boot auto-configuration handle that automatically.

You can expand the test suite to cover:

- Blank or whitespace-only `sender`.
- Missing or malformed `gateway`.
- `max-batch-size` below 1 or above 100.
- `retry.max-attempts` outside the 0–5 range.
- Entire `retry` group missing or an inner required field missing.
- An override from a higher-precedence source changing the validation outcome.

When testing startup failures, avoid asserting on the entire exception string since exact wording can vary across framework versions. Assert that failure occurred and, where useful, check stable details such as the property name or violated constraint.

## 11. Debugging when validation does not run

If you added `@Validated` yet the application still starts with invalid settings, check these common causes.

### Configuration properties bean is not registered

For example, the class has `@ConfigurationProperties` but is not picked up by `@ConfigurationPropertiesScan`, not registered by `@EnableConfigurationProperties`, and not declared via another appropriate bean mechanism.

If the class is never instantiated as a bean, Spring never binds or validates that configuration. Verify the bean is actually part of the `ApplicationContext`.

### Missing Bean Validation provider

`jakarta.validation.constraints.*` annotations require a runtime provider. Without `spring-boot-starter-validation` or an equivalent provider, validation may not behave as expected. Verify actual dependencies rather than checking Java imports alone.

### @Validated placed in the wrong location

For configuration properties, place `@Validated` on the bound properties class or ensure validation is enabled via the bean registration mechanism. Putting `@Validated` on an unrelated service does not automatically validate configuration beans.

Do not confuse this with `@Valid` on Spring MVC controller parameters used to validate HTTP request bodies; both use Bean Validation, yet run at completely different phases.

### Missing @Valid for nested configuration

If constraints live inside a child object, cascade validation with `@Valid` on the property holding that child object. If the child object itself is required, add `@NotNull` to catch when it is completely absent.

### Constraint does not detect missing values

`@NotNull` has no practical effect on a primitive `int`. A missing value becomes `0`; use `@Min(1)` or a wrapper `Integer` with `@NotNull` depending on your requirements.

### Bean is lazy and has not bound yet

If the configuration bean is not instantiated during startup, validation can be delayed. For critical settings that must fail fast, avoid accidentally deferring bean creation until the first request.

### Reading a different property than the one validated

A service might read `Environment` under a different name or instantiate a configuration object with `new`, bypassing the validated `@ConfigurationProperties` bean. Inject the bound configuration bean itself instead of maintaining parallel lookup paths.

## 12. Validation and default values

Defaults are helpful tools, provided they are designed intentionally.

An optional property can specify a default in code:

~~~java
@ConfigurationProperties(prefix = "app.worker")
@Validated
public record WorkerProperties(
        @DefaultValue("10") @Min(1) @Max(100) int parallelism
) {
}
~~~

In this example, `@DefaultValue` belongs to `org.springframework.boot.context.properties.bind`. When `app.worker.parallelism` is omitted, the Binder uses `10`; `@Min` and `@Max` still evaluate against the bound value.

If an operator passes `--app.worker.parallelism=0`, `0` overrides the default and validation fails.

Do not add defaults for properties that are genuinely required and should fail if missing. For instance, a production endpoint should probably use `@NotNull` without a default so the app never silently connects to a test endpoint.

When multiple configuration sources exist, defaults in Java classes and defaults in `application.yml` both have uses, though having too many fallback layers makes it harder for readers to tell what the real value is.

## 13. Do not use @Validated to replace other defense layers

Valid configuration is a necessary condition, not a guarantee that the system will operate flawlessly.

- `@NotNull URI gateway` verifies only that a gateway was provided, not that DNS resolves or the remote API is healthy.
- `@Min(1) int maxBatchSize` ensures a positive limit, not that the server has enough memory for every configured value.
- `@NotBlank String sender` rejects blanks, without verifying the sender address is authorized by the mail provider.
- A syntactically valid `Duration` can still be too short or too long operationally; add domain bounds if needed.

When designing validation, separate:

1. **Syntax and types:** Binder and conversion.
2. **Static configuration rules:** Bean Validation with `@Validated`.
3. **External system state:** runtime checks, health/readiness, or connection resilience.
4. **Per-request business rules:** API/domain-layer validation.

Separating these layers cleanly keeps flaky network calls out of startup validation and yields clearer error messages.

## 14. Workflow for adopting validation in a Spring Boot project

To catch invalid configuration early and consistently:

1. Group related properties into a `@ConfigurationProperties` class or record with a clear prefix.
2. Add `spring-boot-starter-validation` or a compatible Bean Validation provider.
3. Annotate the configuration class with `@Validated`.
4. Apply appropriate constraints to each field: `@NotBlank`, `@NotNull`, `@Min`, `@Max`, `@Pattern`, and others.
5. Use `@Valid` for nested objects, paired with `@NotNull` when the nested object itself is mandatory.
6. Register the configuration via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
7. Ensure mandatory configuration beans instantiate during startup for fail-fast behavior.
8. Test valid configs, out-of-range values, missing properties, and invalid formats.
9. When startup fails, inspect the property name, value source, and binding/validation cause before editing config.
10. Inject the validated `@ConfigurationProperties` bean into services rather than maintaining separate config-reading paths.

Used properly, `@Validated` turns configuration mistakes from unpredictable runtime incidents into immediate, actionable errors caught when the application starts. Combining validation with strongly typed binding, transparent configuration sources, and startup tests makes Spring Boot applications substantially more reliable in production.
