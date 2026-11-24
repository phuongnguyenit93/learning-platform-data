# Dedicated `configurationPropertiesValidator` in Spring Boot

## 1. Problem: Validating Configuration Before Serving Requests

Spring Boot lets you bind external configuration into Java objects using `@ConfigurationProperties`. Values can come from `application.yml`, `application.properties`, environment variables, Java system properties, command-line arguments, or Config Data imports.

For example, a service communicating with a payment gateway needs three parameters:

~~~yaml
app:
  delivery:
    endpoint: https://gateway.example.test
    connect-timeout: 5s
    max-retries: 3
~~~

Even when the YAML is syntactically valid and Spring Boot converts `5s` to `Duration`, the application can still receive **business-invalid configuration**:

- `endpoint` lacks an HTTPS scheme or host.
- `connect-timeout` is zero or negative.
- `max-retries` exceeds the service's safety limit.
- Two individually valid properties are **mutually incompatible**.
- A required field is omitted while the JavaBean is still instantiated.

These errors should be caught **at startup**, rather than waiting for a live request. Spring Boot supports Jakarta Bean Validation with `@Validated` and annotations like `@NotBlank`, `@Min`, and `@NotNull`. When custom validation logic is needed, Spring Boot also supports a **dedicated Spring `Validator`** registered under a specific convention bean name:

~~~text
configurationPropertiesValidator
~~~

This lesson explains how to write, register, and use that validator, why the `@Bean` method must be `static`, how it interacts with `@Validated`, how to report errors on specific fields, and startup pitfalls to avoid.

> **Key point:** the name `configurationPropertiesValidator` is a Spring Boot **integration contract**. Implementing `Validator` alone is not enough; the bean must carry that exact name for the configuration-properties infrastructure to discover it.

## 2. Distinguishing Validation from Binding and Type Conversion

When Spring Boot prepares a `@ConfigurationProperties` bean, picture the responsibilities:

~~~text
application.yml, environment, JVM -D, command-line, ...
                         |
                         v
                    Environment
               (resolve source precedence)
                         |
                         v
                  Configuration Binder
              (map keys -> Java properties)
                         |
                         v
                  Type Conversion
            ("5s" -> Duration, "3" -> int)
                         |
                         v
                   Validation
             (constraints on object)
                         |
                         v
                 Bean ready for use
~~~

Three error types to distinguish:

| Error Type | Example | Detection Mechanism |
| --- | --- | --- |
| Malformed configuration | `connect-timeout: not-a-duration` | Converter/Binder fails to convert to `Duration` |
| Simple constraint violation | `endpoint: ""` | `@NotBlank` or Spring `Validator` |
| Business rule violation | `max-retries: 100` even though it is a valid `int` | Constraint or Spring `Validator` range check |
| Invalid cross-property relationship | Synchronous mode with excessive retry count | Validator inspecting multiple fields of the same object |

Spring `Validator` does not replace the YAML parser, does not choose property sources, and does not convert arbitrary strings into Java types. It receives an **object already constructed/populated by the Binder** and validates it.

If binding fails before the object can be constructed, the validator may never get a chance to run. Therefore, never write a validator trying to "fix" converter errors; fix the input value or register an appropriate converter.

## 3. What Is the `configurationPropertiesValidator` Bean?

According to Spring Boot documentation, you can plug in a custom `org.springframework.validation.Validator` by registering a bean **named** `configurationPropertiesValidator`.

Pay attention to three distinct aspects:

1. **Interface type:** `org.springframework.validation.Validator` (Spring Framework).
2. **Spring bean name:** exact name `configurationPropertiesValidator`.
3. **Initialization timing:** the validator is needed by configuration-properties infrastructure **very early**, so the `@Bean` factory method must be declared `static` so Spring does not have to instantiate the enclosing `@Configuration` class prematurely.

Minimal declaration:

~~~java
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.Validator;

@Configuration(proxyBeanMethods = false)
public class PropertiesValidationConfiguration {

    @Bean(name = "configurationPropertiesValidator")
    public static Validator configurationPropertiesValidator() {
        return new DeliveryPropertiesValidator();
    }
}
~~~

Here `DeliveryPropertiesValidator` is a custom class implementing Spring's `Validator`, detailed in a later section.

You can also rely on the method name as the default bean name:

~~~java
@Bean
public static Validator configurationPropertiesValidator() {
    return new DeliveryPropertiesValidator();
}
~~~

Because the method name matches the required bean name, it registers properly. Still, using `@Bean(name = "configurationPropertiesValidator")` is **explicit** and remains intact if the Java method is later renamed.

Do not pick an arbitrary name such as:

~~~java
@Bean(name = "deliveryValidator")
public static Validator validator() {
    return new DeliveryPropertiesValidator();
}
~~~

expecting Spring Boot to recognize it as the **dedicated configuration properties validator** solely by return type `Validator`. For the dedicated hook, the exact bean name is mandatory.

## 4. Why Must `@Bean` Be `static`?

Spring Boot needs this validator while bootstrapping configuration-properties binding infrastructure, before the full application context and regular beans are ready.

Consider the **discouraged** registration style:

~~~java
@Configuration(proxyBeanMethods = false)
public class PropertiesValidationConfiguration {

    @Bean(name = "configurationPropertiesValidator")
    public Validator configurationPropertiesValidator() {
        return new DeliveryPropertiesValidator();
    }
}
~~~

This is an instance factory method. To invoke it, the container must instantiate `PropertiesValidationConfiguration` before other beans and `BeanPostProcessor`s have stabilized. That risks premature instantiation, warnings, and unexpected dependency/lifecycle issues.

Preferred style:

~~~java
@Configuration(proxyBeanMethods = false)
public class PropertiesValidationConfiguration {

    @Bean(name = "configurationPropertiesValidator")
    public static Validator configurationPropertiesValidator() {
        return new DeliveryPropertiesValidator();
    }
}
~~~

With `static`, the factory method can be invoked **without instantiating the `@Configuration` class**. That is the primary reason—not a performance micro-optimization.

### 4.1. `static` Does Not Mean the Validator Runs Only Once

A common misconception: if the `@Bean` method is `static`, does `validate(...)` only run once?

No. `static` only describes **how the factory method is invoked to create the bean**. The validator is registered as a Spring bean, and `validate(target, errors)` is invoked for each matching configuration-properties object during binding/validation.

### 4.2. Avoid Late-Initialized Dependencies

Do not make the validator depend on repositories, data sources, HTTP clients, or business services that are only ready after the context boots:

~~~java
// Unsuitable design for a validator initialized very early.
@Bean(name = "configurationPropertiesValidator")
public static Validator configurationPropertiesValidator(
        CustomerRepository repository) {
    return new ValidatorThatQueriesDatabase(repository);
}
~~~

In DI terms, Spring may try to resolve the parameter, pulling extra beans into early startup and risking circular dependencies or incompletely processed beans.

Configuration validators should be **pure**, operating solely on values of the target object using standard Java APIs, context-independent utilities, or simple known data. Never make network calls, query databases, or rely on fully started application state.

If a rule depends on external state (such as verifying an endpoint is reachable), separate it into a readiness, health, or dependency check rather than putting it into an early config validator.

## 5. The Spring `Validator` Interface Has Two Methods

Spring Framework defines:

~~~java
package org.springframework.validation;

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

### 5.1. `supports(Class<?>)`

Spring calls `supports` to determine whether the validator handles a given target class.

Example:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return DeliveryProperties.class.isAssignableFrom(clazz);
}
~~~

Meaning: supports `DeliveryProperties` and compatible subtypes.

Never return `true` for every class and unconditionally cast target to `DeliveryProperties`:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return true; // Likely causes ClassCastException with multiple properties beans.
}
~~~

An application typically contains dozens of `@ConfigurationProperties` beans, including Spring Boot and library types. The dedicated validator can be asked about other beans; `supports` scopes it safely so you never cast the wrong type.

### 5.2. `validate(Object, Errors)`

`validate` receives the bound object and an `Errors` collector to report field-level or object-level errors:

~~~java
@Override
public void validate(Object target, Errors errors) {
    DeliveryProperties props = (DeliveryProperties) target;

    if (props.getMaxRetries() < 0) {
        errors.rejectValue(
                "maxRetries",
                "delivery.maxRetries.invalid",
                "maxRetries must not be negative");
    }
}
~~~

Arguments to `rejectValue`:

1. The **JavaBean field name** (here `maxRetries`), not the full external path `app.delivery.max-retries`.
2. Error code, e.g., `delivery.maxRetries.invalid`.
3. Default message for logs and failure analysis.

Spring can resolve error codes to localized messages via `MessageSource` when configured. If no message bundle is configured, the default message still tells operators what failed.

For errors not tied to a single field, use:

~~~java
errors.reject("delivery.inconsistent",
        "Delivery configuration contains incompatible values");
~~~

Avoid throwing `IllegalArgumentException` for every rule when `Errors` can be used; using the error collector lets Spring infrastructure format binding/validation failures cleanly.

## 6. Complete Example: `DeliveryProperties` Model

Our demo project uses Java 17+ and Spring Boot 3.x. We want to validate:

- `endpoint` is non-blank and an HTTPS URI with a host.
- `connectTimeout` is positive and does not exceed an internal 60-second ceiling.
- `maxRetries` is between 0 and 10.
- When `enabled=true`, a usable endpoint must be supplied.
- When `enabled=false`, endpoint may be omitted per contract. In this example we set an explicit rule: **when enabled, endpoint is required; when disabled, endpoint may be omitted**.

File `src/main/resources/application.yml`:

~~~yaml
app:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test
    connect-timeout: 5s
    max-retries: 3
~~~

JavaBean-style properties class:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public class DeliveryProperties {

    private boolean enabled = false;
    private String endpoint;
    private Duration connectTimeout = Duration.ofSeconds(5);
    private int maxRetries = 2;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

Notes:

- `@ConfigurationProperties(prefix = "app.delivery")` groups keys under one prefix.
- `@Validated` indicates that the object participates in validation; Spring Boot handles configuration-properties validation.
- JavaBean field initializers supply fallback values if keys are absent.
- `Duration` binds `5s`, `30s`, etc., via Spring Boot conversion.
- `endpoint` uses `String` so the validator can enforce the HTTPS policy itself. You could bind directly to `URI`, yet you would still need scheme/host validation.
- Defaults in JavaBeans do not inject corresponding properties into `Environment` if no source declares them.

## 7. Implementing `DeliveryPropertiesValidator`

Here is a complete implementation requiring no Spring container or database access:

~~~java
package com.example.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class DeliveryPropertiesValidator implements Validator {

    private static final Duration MAX_TIMEOUT = Duration.ofSeconds(60);

    @Override
    public boolean supports(Class<?> clazz) {
        return DeliveryProperties.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        DeliveryProperties props = (DeliveryProperties) target;

        validateTimeout(props, errors);
        validateRetries(props, errors);

        if (props.isEnabled()) {
            validateRequiredEndpoint(props.getEndpoint(), errors);
        }
        else if (props.getEndpoint() != null
                && !props.getEndpoint().isBlank()) {
            // If an endpoint is provided while disabled, still validate it
            // to avoid hidden invalid configuration.
            validateRequiredEndpoint(props.getEndpoint(), errors);
        }
    }

    private void validateTimeout(
            DeliveryProperties props, Errors errors) {
        Duration timeout = props.getConnectTimeout();

        if (timeout == null || timeout.isZero()
                || timeout.isNegative()) {
            errors.rejectValue(
                    "connectTimeout",
                    "delivery.timeout.notPositive",
                    "connect-timeout must be positive");
            return;
        }

        if (timeout.compareTo(MAX_TIMEOUT) > 0) {
            errors.rejectValue(
                    "connectTimeout",
                    "delivery.timeout.tooLarge",
                    "connect-timeout must not exceed 60s");
        }
    }

    private void validateRetries(
            DeliveryProperties props, Errors errors) {
        int retries = props.getMaxRetries();

        if (retries < 0 || retries > 10) {
            errors.rejectValue(
                    "maxRetries",
                    "delivery.retries.outOfRange",
                    "max-retries must be between 0 and 10");
        }
    }

    private void validateRequiredEndpoint(
            String value, Errors errors) {
        if (value == null || value.isBlank()) {
            errors.rejectValue(
                    "endpoint",
                    "delivery.endpoint.required",
                    "endpoint must be configured when delivery is enabled");
            return;
        }

        try {
            URI uri = URI.create(value);

            if (!"https".equalsIgnoreCase(uri.getScheme())
                    || uri.getHost() == null) {
                errors.rejectValue(
                        "endpoint",
                        "delivery.endpoint.invalid",
                        "endpoint must be an absolute HTTPS URI with a host");
            }
        }
        catch (IllegalArgumentException ex) {
            errors.rejectValue(
                    "endpoint",
                    "delivery.endpoint.malformed",
                    "endpoint is not a valid URI");
        }
    }
}
~~~

This code intentionally calls `errors.rejectValue(...)` rather than throwing arbitrary exceptions. It supplies the field name, error code, and message so Spring Boot can aggregate all violations into a clear startup binding/validation failure.

How `enabled=false` is handled here is **this example's business choice**. Another project might require `endpoint` unconditionally, or skip checking `timeout` when disabled. Spring Boot imposes no universal business policy across applications.

In applications handling secrets, **never embed secret values in default messages**, even on invalid input. Mention only the property name and violated rule.

## 8. Registering the Validator with the Exact Name and Timing

Create a configuration class:

~~~java
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.Validator;

@Configuration(proxyBeanMethods = false)
public class DeliveryValidationConfiguration {

    @Bean(name = "configurationPropertiesValidator")
    public static Validator configurationPropertiesValidator() {
        return new DeliveryPropertiesValidator();
    }
}
~~~

**Why not just annotate `DeliveryPropertiesValidator` with `@Component`?**

Because default component scanning names the bean after the class—`deliveryPropertiesValidator`, not `configurationPropertiesValidator`. Boot will not automatically treat it as the dedicated validator just from its class name.

There is also no need to manually create a `LocalValidatorFactoryBean` just for this Spring `Validator`. `LocalValidatorFactoryBean` bridges Jakarta Bean Validation and addresses a different mechanism (though the two can coexist).

### 8.1. Are `@Primary` or `@Qualifier` Needed?

You do not need `@Primary` for Boot to discover this dedicated validator. **The bean name itself is the lookup key** under Spring Boot's contract.

Likewise, `@Qualifier("configurationPropertiesValidator")` only matters when injecting the bean elsewhere via DI, not for registering it with the Binder.

### 8.2. Never Register Multiple Beans with the Same Name

A context should not define multiple independent `configurationPropertiesValidator` beans. Depending on Spring Boot's bean-overriding settings, duplicate names will either fail startup or silently overwrite one bean with another.

If you have multiple rule sets, build **one composite/delegating validator** supporting multiple properties types, or pair with per-class validation mechanisms. Do not define a new `configurationPropertiesValidator` bean per properties class expecting Spring to invoke all of them.

### 8.3. The Configuration Class Must Be Discovered

`DeliveryValidationConfiguration` must live inside `@SpringBootApplication`'s component-scan scope or be explicitly imported into the context. If it sits in a package outside scan scope, use `@Import(DeliveryValidationConfiguration.class)` on a Spring-managed configuration class.

A properly written `static @Bean` method on an unregistered configuration class will still leave the bean absent.

## 9. Registering `@ConfigurationProperties` for Binding and Validation

The properties class must be registered through Spring Boot's mechanism.

### 9.1. Scanning with `@ConfigurationPropertiesScan`

~~~java
package com.example;

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

Assuming `DeliveryProperties` and `DeliveryValidationConfiguration` reside under `com.example`, Spring Boot scans the properties type, registers the bean, and binds values from `Environment`, while Spring processes `DeliveryValidationConfiguration` as a standard `@Configuration` class.

### 9.2. Explicit Registration with `@EnableConfigurationProperties`

~~~java
package com.example.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(DeliveryProperties.class)
public class DeliveryRegistrationConfiguration {
}
~~~

This option works cleanly when registering specific types explicitly, such as in auto-configuration or unit tests.

### 9.3. Why Not Validate Inside a Service on First Use?

Another option is calling `properties.getEndpoint()` and checking it during business execution. However, errors then appear only on the first request, possibly after the app has reported ready and accepted traffic.

With a configuration-properties validator, errors are caught while configuration beans are bound and validated, **typically failing `ApplicationContext` creation and halting startup**. This fits requirements that are mandatory for the service to function.

Keep in mind that beans marked `@Lazy` or created via special deferred paths can shift when errors surface. For system-wide critical settings, ensure beans register and initialize on the normal startup path.

## 10. Distinguishing `@Validated`, Jakarta Bean Validation, and Spring `Validator`

These terms are often conflated:

| Concept | Component | Role |
| --- | --- | --- |
| `@ConfigurationProperties` | Spring Boot | Binds external keys into Java objects |
| `@Validated` | Spring Framework | Marks validation intent and optional validation groups |
| `@NotBlank`, `@NotNull`, `@Min` | `jakarta.validation.constraints` | Declarative Bean Validation constraints |
| Bean Validation implementation | e.g., Hibernate Validator | Evaluates Jakarta constraints |
| `org.springframework.validation.Validator` | Spring Framework | Programmatic validation API via `supports` and `validate` |
| `configurationPropertiesValidator` bean | Spring Boot convention | Registers custom Spring `Validator` for config properties |

If you only need a non-blank name, string length, or numeric bounds, Jakarta Bean Validation requires less code:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        @NotBlank String endpoint,
        @Min(0) @Max(10) int maxRetries) {
}
~~~

When you need custom rules such as **endpoint must be HTTPS when `enabled=true`**, or mode-dependent timeouts, a custom Spring `Validator` fits naturally.

**Both mechanisms can complement each other.** Jakarta constraints handle simple checks; custom Spring `Validator` handles complex relationships. Avoid duplicating the exact same rule in both places, which can produce duplicate error messages.

In Spring Boot 3.x, Jakarta validation uses `jakarta.validation.*`, unlike `javax.validation.*` in Spring Boot 2.x. Spring `Validator` remains `org.springframework.validation.Validator` and does not require writing a `ConstraintValidator`.

### 10.1. Is the Validation Starter Required?

If you use Jakarta Bean Validation annotations in Spring Boot 3.x, you need a compatible implementation, typically via:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

By contrast, `org.springframework.validation.Validator` is part of core Spring Framework. You can write custom rules using Spring's `Validator` and `Errors` without turning every rule into a Jakarta constraint. If a project uses both, the validation dependency is still needed to evaluate `@NotBlank`, `@Min`, `@Valid`, etc.

Verify your project's actual dependency graph: another starter might transitively include an implementation, yet never assume that blindly.

## 11. Does One Dedicated Validator Serve All Beans?

A bean named `configurationPropertiesValidator` acts **globally across configuration-properties infrastructure**. Consequently, your validator must explicitly declare which types it supports.

Suppose an application has:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public class DeliveryProperties { /* ... */ }

@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties { /* ... */ }

@ConfigurationProperties(prefix = "app.mail")
public class MailProperties { /* ... */ }
~~~

If a custom validator is meant only for delivery, write:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return DeliveryProperties.class.isAssignableFrom(clazz);
}
~~~

When infrastructure encounters `CacheProperties` or `MailProperties`, this validator will never attempt to cast them to `DeliveryProperties`.

If a project needs one bean to validate multiple types, build a **delegating validator**:

~~~java
public final class AppConfigurationValidator implements Validator {

    private final Validator delivery = new DeliveryPropertiesValidator();
    private final Validator cache = new CachePropertiesValidator();

    @Override
    public boolean supports(Class<?> clazz) {
        return delivery.supports(clazz) || cache.supports(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        if (delivery.supports(target.getClass())) {
            delivery.validate(target, errors);
        }
        if (cache.supports(target.getClass())) {
            cache.validate(target, errors);
        }
    }
}
~~~

This example assumes `CachePropertiesValidator` also implements Spring `Validator` without depending on late-initialized beans.

Register one bean:

~~~java
@Bean(name = "configurationPropertiesValidator")
public static Validator configurationPropertiesValidator() {
    return new AppConfigurationValidator();
}
~~~

As configuration types grow, use a plain Java collection/map of validators and clean dispatch logic. Avoid injecting a list of late-initialized validator beans into the early-startup dedicated validator.

## 12. When to Use `Errors.rejectValue` vs. `Errors.reject`

### 12.1. Attaching an Error to a Field

Use `rejectValue` when a specific field is invalid:

~~~java
if (properties.getConnectTimeout() == null) {
    errors.rejectValue(
            "connectTimeout",
            "delivery.timeout.required",
            "connect-timeout is required");
}
~~~

Passing the JavaBean property name `connectTimeout` matches the object being validated. Infrastructure maps it cleanly to the external configuration path `app.delivery.connect-timeout` in error output.

### 12.2. Attaching an Error to the Whole Object

Use `reject` when a combination of multiple fields is invalid:

~~~java
if (properties.isEnabled()
        && properties.getMaxRetries() > 5
        && properties.getConnectTimeout().compareTo(
                Duration.ofSeconds(30)) > 0) {
    errors.reject(
            "delivery.retryTimeout.incompatible",
            "Retry count and timeout are too high when delivery is enabled");
}
~~~

This snippet assumes `connectTimeout` is already non-null. In real validators, always check for null before calling methods to prevent `NullPointerException`.

Prefer actionable messages stating the violated condition and affected field names, rather than generic text like `"Invalid configuration"`.

### 12.3. Should You Throw Exceptions Directly?

A validator can throw an exception for internal programming errors, yet for **invalid configuration data**, prefer `Errors` to record validation failures. That lets Spring wrap errors cleanly into the binding/validation report with clear property names.

For trivial checks where a Spring `Validator` is unnecessary, throwing in a constructor or `@Bean` factory method can also achieve fail-fast behavior. However, that is a **different pattern**, not the dedicated `configurationPropertiesValidator` mechanism covered here.

## 13. When Does the Validator Run in the Startup Lifecycle?

Consider a simplified flow:

~~~text
1. main -> SpringApplication.run(args)
2. Spring Boot prepares Environment and Config Data
3. Spring initializes early infrastructure bean definitions
4. Spring Boot looks up the dedicated configurationPropertiesValidator
5. Spring creates and binds @ConfigurationProperties objects
6. Spring runs validation via binding infrastructure
7. If errors exist -> binding/validation failure
8. If valid -> beans are consumed by application services
~~~

Exact ordering varies across versions and bean registration styles, yet the **crucial contract** is that the dedicated validator is retrieved very early. That is why `static @Bean` avoids prematurely instantiating the enclosing configuration class.

Do not treat Spring `Validator` as a file-watcher listener that re-runs whenever an operator edits `application.yml`. Standard Spring Boot **loads and binds Config Data at startup**; editing files at runtime does not re-trigger validation or update beans unless an explicit refresh mechanism is configured per its own contract.

## 14. Testing with `ApplicationContextRunner`

`ApplicationContextRunner` spins up a minimal application context with explicit configuration, making it ideal for verifying how a validator affects startup.

Test dependency usually includes:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

A test for Spring Boot 3.x:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ConfigurationPropertiesAutoConfiguration.class))
            .withUserConfiguration(
                Registration.class,
                DeliveryValidationConfiguration.class);

    @Test
    void acceptsValidConfiguration() {
        runner.withPropertyValues(
                "app.delivery.enabled=true",
                "app.delivery.endpoint=https://gateway.example.test",
                "app.delivery.connect-timeout=5s",
                "app.delivery.max-retries=3")
            .run(context -> {
                assertThat(context).hasNotFailed();
                DeliveryProperties props =
                    context.getBean(DeliveryProperties.class);
                assertThat(props.getMaxRetries()).isEqualTo(3);
            });
    }

    @Test
    void rejectsInvalidEndpointAtStartup() {
        runner.withPropertyValues(
                "app.delivery.enabled=true",
                "app.delivery.endpoint=http://unsafe.example.test",
                "app.delivery.connect-timeout=5s",
                "app.delivery.max-retries=3")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure()).isNotNull();
            });
    }

    @Test
    void rejectsOutOfRangeRetries() {
        runner.withPropertyValues(
                "app.delivery.enabled=true",
                "app.delivery.endpoint=https://gateway.example.test",
                "app.delivery.max-retries=99")
            .run(context -> {
                assertThat(context).hasFailed();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class Registration {
    }
}
~~~

In this example:

- `Registration` ensures Spring creates and binds `DeliveryProperties`.
- `DeliveryValidationConfiguration` registers the dedicated validator with the exact name via `static @Bean`.
- The valid test checks that the context starts and the bean receives bound values.
- The invalid tests check that the `ApplicationContext` **fails to start**.
- To inspect specific messages, check the cause chain of `getStartupFailure()`; avoid asserting exact verbatim wording that can vary across Spring Boot versions.

This tests **rejection of bad configuration**, not live connectivity to a gateway. `example.test` is purely for syntax testing.

## 15. Unit Testing the `Validator` Directly Without a Spring Context

Most validator logic can be tested as plain Java using `BeanPropertyBindingResult` to collect errors:

~~~java
package com.example.config;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesValidatorTest {

    private final DeliveryPropertiesValidator validator =
            new DeliveryPropertiesValidator();

    @Test
    void rejectsNonHttpsEndpoint() {
        DeliveryProperties props = new DeliveryProperties();
        props.setEnabled(true);
        props.setEndpoint("http://unsafe.example.test");
        props.setConnectTimeout(Duration.ofSeconds(5));
        props.setMaxRetries(3);

        Errors errors = new BeanPropertyBindingResult(props, "delivery");
        validator.validate(props, errors);

        assertThat(errors.hasFieldErrors("endpoint")).isTrue();
    }

    @Test
    void acceptsValidSettings() {
        DeliveryProperties props = new DeliveryProperties();
        props.setEnabled(true);
        props.setEndpoint("https://gateway.example.test");
        props.setConnectTimeout(Duration.ofSeconds(5));
        props.setMaxRetries(3);

        Errors errors = new BeanPropertyBindingResult(props, "delivery");
        validator.validate(props, errors);

        assertThat(errors.hasErrors()).isFalse();
    }
}
~~~

Direct unit tests verify `supports`, field error codes, and business rules without booting an `ApplicationContext`. However, they **do not prove** Spring Boot registered the bean with the right name or invoked it during binding.

Therefore, combine both:

- **Validator unit tests:** verify logic and `Errors`.
- **Context tests:** verify `configurationPropertiesValidator` wiring and fail-fast behavior in `@ConfigurationProperties` binding.

With only unit tests, a missing `static` modifier or misspelled bean name could go undetected.

## 16. Distinguishing the Dedicated Validator from Web/MVC Validators

Spring has several "validators," serving different purposes:

| Component | Scope | How Selected |
| --- | --- | --- |
| `configurationPropertiesValidator` | Config properties binding/validation | Spring Boot looks up bean by **exact special name** |
| Spring MVC/`WebDataBinder` validator | Request form/model binding | MVC/web infrastructure and validator registration |
| `LocalValidatorFactoryBean` | Jakarta Bean Validation adapter | Validator bean/factory for Bean Validation |
| `ConstraintValidator<A,T>` | Custom constraint annotations | Jakarta Bean Validation engine |
| `@InitBinder` validator | Controller request model binding | Applied per controller/`WebDataBinder` |

Consequently, implementing:

~~~java
@Override
public void addValidators(Validator... validators) {
    // MVC config does not register the dedicated configuration properties validator.
}
~~~

or configuring `@InitBinder` does not replace a bean named `configurationPropertiesValidator`.

Similarly, a bean named `validator` used elsewhere is not automatically treated as the configuration-properties validator. **Exact bean name and the Spring `Validator` interface** are both required.

## 17. Combining a Custom `Validator` with Jakarta Constraints

A class can use `@Validated` alongside Jakarta constraints:

~~~java
package com.example.config;

import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public class DeliveryProperties {

    @NotNull
    private Duration connectTimeout = Duration.ofSeconds(5);

    @Min(0)
    @Max(10)
    private int maxRetries = 2;

    private boolean enabled;
    private String endpoint;

    // getters and setters as in section 6
}
~~~

With this setup, Jakarta validation checks that `connectTimeout` is non-null and `maxRetries` is in `0..10`, while the custom validator enforces the HTTPS URL and 60-second timeout ceiling.

Do not duplicate the `maxRetries >= 0 && <= 10` check in both places in real projects unless deliberately testing the mechanism—duplicating rules produces duplicate errors. Pick one clear home per constraint.

### 17.1. Cross-Field Rules

A natural use case for Spring `Validator`: when `enabled=true`, `endpoint` must be present; when `enabled=false`, it may be blank.

Rules of the form "field A is required **only when** field B equals C" are awkward to express with standalone field annotations. A custom validator can inspect the whole object and call `errors.rejectValue(...)` on the offending field.

### 17.2. Nested Properties

Suppose you have:

~~~yaml
app:
  delivery:
    security:
      mode: bearer
      token: "${DELIVERY_TOKEN}"
~~~

If the object has a nested `Security security` field, the custom validator can inspect `security.getMode()` and `security.getToken()`. Check `security != null` first, and pass the nested field path to `rejectValue`, e.g., `"security.token"`.

With Jakarta Bean Validation, nested objects typically use `@Valid` to cascade. With a custom Spring `Validator`, you can also use `errors.pushNestedPath("security")`, invoke a child validator, and call `popNestedPath()` inside a `try/finally` block so the error collector path never gets corrupted.

Never include token values in error messages.

## 18. Safety When Validating Credentials and URLs

Validators often inspect sensitive fields, yet must avoid side effects and data leaks.

**Do:**

- Check that secrets are non-null/non-blank without logging them.
- Verify URLs use allowed schemes and valid hosts.
- Enforce bounds on timeouts and retry counts.
- Validate queue/topic names against clear patterns.
- State the failing field name in messages.

**Do not:**

- Make HTTP requests to endpoints inside a validator just to test reachability.
- Query a database to verify passwords during early startup.
- Log entire configuration objects containing `password` or `apiKey`.
- Include user-supplied URLs containing query-parameter tokens in exception messages.
- Mutate configuration data or property sources inside `validate(...)`.

A validator's job is **reading and evaluating state**, not opening infrastructure connections or rewriting bound values. Network checks belong in connectivity, readiness, or startup health checks with proper timeouts and retry policies.

## 19. Common Errors and Fixes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Validator never invoked on bind | Bean not named exactly `configurationPropertiesValidator` | Declare `@Bean(name = "configurationPropertiesValidator")` |
| Bean has exact name yet never runs | `@Configuration` class not scanned/imported by Spring | Put inside scan path or use `@Import` |
| Early bean creation warnings | `@Bean` method is not `static`, or depends on late beans | Make it `static` and keep validator standalone |
| `ClassCastException` inside `validate` | `supports` returns `true` for unsupported types | Restrict `supports` to specific target classes |
| Startup passes with bad endpoint | Rule forgot `errors.rejectValue`, bean unbound/unvalidated, or bad wiring | Write separate validator unit test and context test |
| Multiple beans with same name | Several modules define `configurationPropertiesValidator` | Consolidate into one bean/delegating validator |
| Property missing on bound object | YAML typo or missing config | Check prefix and relaxed binding |
| Fails to parse `connect-timeout` | Invalid `Duration` syntax | Fix input before validator logic runs |
| Error message unclear about field | Used `errors.reject` for a single-field error | Use `rejectValue` with the appropriate Java field |
| Validator unit tests pass yet app fails to check | Unit tests do not test Spring Boot wiring | Add `ApplicationContextRunner` tests |
| Bean Validation annotations ignored | Missing `@Validated` or provider implementation | Add configuration and `spring-boot-starter-validation` |
| Validator hits repository too early and crashes startup | Depends on unready business beans | Remove I/O and late dependencies from custom validator |
| Secret validation leaks into logs | Logging whole object or actual rejected value | Report only field name and violated policy |

Startup failures may be wrapped across multiple exception layers, such as bean-creation or `@ConfigurationProperties` binding exceptions. Read the root cause along with field/error codes and source precedence—never stop at the first line of the stack trace.

## 20. When Should You Use the Dedicated `configurationPropertiesValidator`?

This approach fits well when:

1. You have **cross-field validation rules** that are awkward to express with individual annotations.
2. You prefer keeping validation logic outside properties classes so configuration types remain pure data holders.
3. You want one centralized validator covering multiple `@ConfigurationProperties` types via clear `supports` checks.
4. You want Spring `Errors` and field error codes that can be unit tested independently.
5. You want fail-fast enforcement during configuration-properties binding instead of scattering checks across services.

You do not necessarily need a dedicated validator for a few simple checks:

~~~java
@NotBlank String endpoint;
@Min(1) int poolSize;
@NotNull Duration timeout;
~~~

For those constraints, `@Validated` with Jakarta Bean Validation is more concise. Choose a custom validator when it makes rules **clearer**, not simply because the hook sounds more powerful.

Another option is validating inside constructors/compact constructors of immutable classes or records. That protects invariants even when instantiated manually, though it lacks Spring `Errors`/field error codes and does not replace registering a dedicated validator if binder-level `Errors` integration is the goal.

## 21. Case Study Exercises

### 21.1. Problem Setup

Given YAML:

~~~yaml
app:
  delivery:
    enabled: true
    endpoint: http://gateway.example.test
    connect-timeout: -5s
    max-retries: 20
~~~

Registered:

~~~java
@Bean(name = "configurationPropertiesValidator")
public static Validator configurationPropertiesValidator() {
    return new DeliveryPropertiesValidator();
}
~~~

And `DeliveryProperties` is scanned via `@ConfigurationPropertiesScan`.

**Question 1:** How many rules in section 7's validator are violated?

**Answer:** At least three:
- `endpoint` uses HTTP instead of HTTPS.
- `connect-timeout` is negative.
- `max-retries=20` exceeds the maximum of 10.

The validator calls `errors.rejectValue(...)` for all three fields, producing clear startup diagnostics.

**Question 2:** If `connect-timeout` is changed to `"not-a-duration"`, where does the error come from?

**Answer:** Conversion/binding to `Duration` fails **before** semantic timeout validation in the validator. This is not a case of `errors.rejectValue` on a bound `Duration`.

**Question 3:** What if the bean is named `customPropertiesValidator`?

**Answer:** It breaks the `configurationPropertiesValidator` naming contract. Spring Boot will not recognize it as the dedicated configuration-properties validator solely from its `Validator` return type.

**Question 4:** If `static` is removed, is the application guaranteed to crash?

**Answer:** Not necessarily. However, it risks premature instantiation of the `@Configuration` class and lifecycle issues; Spring Boot documentation strongly recommends declaring the method `static`.

**Question 5:** If the validator returns `supports(...)=true` unconditionally and the app adds `CacheProperties`, what happens?

**Answer:** When the validator receives a target that is not `DeliveryProperties`, the cast throws `ClassCastException`. Restrict `supports` by type or use a delegating validator dispatching by class.

### 21.2. Extension Exercise: Checking Timeout-Retry Relationship

Add the rule:

~~~text
If enabled = true:
    maxRetries * connectTimeout <= 120s
~~~

Wait—check lines 1083-1086 in `validation-009.md`: they use `~~~text` and `~~~`, not triple backticks! Keep `~~~` cleanly.

With Java:

~~~java
if (props.isEnabled()
        && props.getConnectTimeout() != null
        && !props.getConnectTimeout().isNegative()
        && props.getMaxRetries() >= 0) {
    long timeoutSeconds = props.getConnectTimeout().getSeconds();
    if (timeoutSeconds > 0
            && props.getMaxRetries() > 0
            && timeoutSeconds > 120L / props.getMaxRetries()) {
        errors.reject(
                "delivery.retryBudget.exceeded",
                "Total retry timeout budget must not exceed 120s");
    }
}
~~~

Checking `timeoutSeconds > 120L / maxRetries` avoids `long` multiplication overflow when testing the ceiling, though it truncates to whole seconds and is unsuitable if millisecond or nanosecond precision is required. When sub-second precision matters, compare using `Duration` or nanoseconds with proper overflow guards.

Write additional unit tests covering `enabled=false`, `maxRetries=0`, `timeout=30s` with 4 retries, and `timeout=60s` with 3 retries.

## 22. Key Takeaways

- **Required bean name:** `configurationPropertiesValidator`, exact camelCase.
- **Type:** `org.springframework.validation.Validator`, with `supports(Class<?>)` and `validate(Object, Errors)`.
- **Declaration:** `@Bean(name = "configurationPropertiesValidator")` and a `static` factory method to avoid premature `@Configuration` instantiation.
- **Scope:** `supports` must accept only the `@ConfigurationProperties` types the validator understands, preventing bad casts.
- **Reporting errors:** use `errors.rejectValue(...)` for fields and `errors.reject(...)` for object-level rules; never log secrets.
- **Combining tools:** `@Validated` + Jakarta Bean Validation excels for declarative rules; custom Spring `Validator` excels for cross-field logic.
- **Startup failures:** type mismatches fail at binding first; semantic rules fail during validation when beans are registered and bound via configuration properties.
- **Testing:** combine direct `Validator` unit tests with context tests verifying bean name, timing, and startup rejection.
- **No I/O:** the dedicated validator initializes very early; avoid complex dependency graphs, databases, network calls, and side effects.

### References

- Spring Boot Reference — Externalized Configuration, `@ConfigurationProperties` Validation: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation
- Spring Boot 3.3 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework Reference — Validation by Using Spring's Validator Interface: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Framework Javadoc — `Validator`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Validator.html
- Spring Framework Javadoc — `Errors`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Errors.html