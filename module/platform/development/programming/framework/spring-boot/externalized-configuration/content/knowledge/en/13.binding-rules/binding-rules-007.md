# Detecting Misspelled Keys Instead of Silently Ignoring Them

## 1. The problem: the application starts, yet configuration is wrong

In Spring Boot Externalized Configuration, settings are commonly placed in `application.yml`, `application.properties`, environment variables, or command-line arguments. As the number of properties grows, a tiny typo can leave the application using **default values** instead of what the operator intended.

Suppose a notification service has this configuration:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry-count: 5
  connect-timeout: 4s
```

The Java class expects to bind `notification.retry-count`. If the YAML author accidentally types:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retrty-count: 5       # ERROR: extra letter t
  connect-timeout: 4s
```

then `notification.retrty-count` is **not** `notification.retry-count`. Depending on binder configuration and fallback values, Spring Boot can ignore the unrecognized key while the application still starts normally.

This is dangerous because logs may show no obvious warning, while retries execute fewer times than intended. With timeouts, access limits, or other critical parameters, such a mistake can produce hard-to-diagnose behavior.

**Lesson objective:** understand how to instruct Spring Boot to detect unbindable configuration keys, distinguish key-name errors from data-type errors, and recognize the limits of strict checking.

## 2. Why can an unrecognized key be ignored?

Spring Boot uses the **Configuration Properties Binder** to map configuration properties onto beans annotated with `@ConfigurationProperties`. The Binder looks for values under a prefix, such as `notification`, and maps valid names onto fields or constructor parameters.

Example:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        String endpoint,
        int retryCount,
        java.time.Duration connectTimeout) {
}
```

Expected binding names include:

| Canonical property name | Java component | Java type |
| --- | --- | --- |
| `notification.endpoint` | `endpoint` | `String` |
| `notification.retry-count` | `retryCount` | `int` |
| `notification.connect-timeout` | `connectTimeout` | `Duration` |

If `notification.retrty-count` appears, the binder does not treat it as an alternate spelling of `retry-count`; it is a different name.

The `@ConfigurationProperties` annotation has an option:

```java
ignoreUnknownFields
```

The default of this option is **`true`**. That means during normal binding, configuration fields that the binder considers to have no matching target can be **ignored** rather than forcing startup to fail.

This aids compatibility with configuration sources containing many keys or extensions outside a single bean. However, for critical application-owned configuration, silent ignoring can mask key typos.

## 3. Enabling strict rejection of unknown keys

To tell the binder to detect unbound properties within a bean's scope, set:

```java
@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
```

Full record example:

```java
package com.example.configdemo;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        String endpoint,
        int retryCount,
        Duration connectTimeout) {
}
```

With valid YAML:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry-count: 5
  connect-timeout: 4s
```

the binder can bind all three properties to the three record components. Provided the Java code and other sources align, the bean is created successfully.

With YAML containing a wrong key:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retrty-count: 5
  connect-timeout: 4s
```

the binder can recognize `notification.retrty-count` as a property under the `notification` prefix that is **not bound** to any component. When ignoring unknown keys is disabled, bean creation can fail, with error details pointing to the unbound key.

Depending on the Spring Boot version and binding path, logs may contain a message like **"The elements ... were left unbound"**, along with related binding exceptions such as `UnboundConfigurationPropertiesException` or `ConfigurationPropertiesBindException` in the cause chain. Do not write logic depending on the exact wording of an error message because log formatting can vary.

**Scope note:** this mode checks properties that the binder sees when binding **registered configuration beans**. It is not a mechanism that automatically audits every key across all system configuration sources.

## 4. Runnable example with Spring Boot

Examples use Java 17 or higher and the standard Spring Boot 3.x `@ConfigurationProperties` registration style.

### 4.1. Configuration file

Create `src/main/resources/application.yml`:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry-count: 3
  connect-timeout: 5s
```

### 4.2. Configuration Properties class

Create `NotificationProperties.java`:

```java
package com.example.configdemo;

import java.time.Duration;
import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        URI endpoint,
        int retryCount,
        Duration connectTimeout) {
}
```

Using `URI` models the `endpoint` data clearly; using `Duration` lets the program work with time durations instead of manually parsing `"5s"`.

### 4.3. Registering the bean so the binder actually runs

In the main application class:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` scans configuration types in the appropriate packages and registers them as beans.

Another option is using:

```java
@EnableConfigurationProperties(NotificationProperties.class)
```

on a configuration class, importing `org.springframework.boot.context.properties.EnableConfigurationProperties`. Only one suitable registration method is needed; do not add `@Component` onto a record intended for constructor binding.

**If the bean is never registered**, no binding process runs for that bean to detect unknown keys. This is one of the most frequently overlooked limits during diagnosis.

### 4.4. Observing values in a service

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class NotificationPrinter implements ApplicationRunner {

    private final NotificationProperties properties;

    public NotificationPrinter(NotificationProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("endpoint = " + properties.endpoint());
        System.out.println("retryCount = " + properties.retryCount());
        System.out.println(
                "connectTimeout = " + properties.connectTimeout());
    }
}
```

With valid configuration, illustrative output:

```text
endpoint = https://notify.example.invalid
retryCount = 3
connectTimeout = PT5S
```

If you change `retry-count` to `retrty-count` and restart, we want strict binding to **reject an unknown key within the bean's scope**. Instead of printing wrong values, the application can stop during context creation and display a binding error.

## 5. Why does a wrong key sometimes cause no error?

Not every mistake in a configuration file is caught by `ignoreUnknownFields = false`. Distinguish the cases.

### 5.1. Wrong key directly inside the bound prefix

For example, the bean has `prefix = "notification"` and expects `retryCount`, while the source contains:

```properties
notification.retrty-count=3
```

This is the classic scenario that disabling unknown-field ignoring is designed to catch.

### 5.2. Mistyping the prefix itself

The bean expects `notification.*`, yet configuration says:

```properties
notificaton.retry-count=3
```

The typo is in the **prefix** `notificaton`. The binder binding prefix `notification` may not see properties outside that prefix. Therefore, setting `ignoreUnknownFields = false` alone **does not guarantee catching typos at the prefix level**.

To guard against missing an entire configuration group, add required-value constraints on key fields or test configuration per environment.

### 5.3. Key outside the governed group

The `NotificationProperties` bean should not fail just because the file also contains:

```yaml
server:
  port: 8080

logging:
  level:
    root: INFO

notification:
  retry-count: 3
```

Keys `server.*` and `logging.*` belong to other configuration scopes, not unknown fields under the bean's `notification` prefix.

### 5.4. Class is unregistered

Without `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or an equivalent mechanism, the bean may not exist. Without binding the bean, there is no detection of unbound keys for that bean.

### 5.5. Configuration source was not loaded

If you edit a file that does not participate in Config Data—such as `application-stage.yml` when profile `stage` is inactive—the binder cannot detect mistakes in a file it never read.

Thus, "strict binding is enabled and no error appeared" does not prove configuration is right by itself. Check **whether the file was loaded, whether the bean was registered, and whether the key lies inside the bound prefix**.

## 6. Default values can mask typos

Consider a record:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        @DefaultValue("3") int retryCount) {
}
```

With configuration:

```yaml
notification:
  retrty-count: 8
```

The key name `retrty-count` is wrong. The Binder cannot find `retry-count`, so it can fall back to `@DefaultValue("3")`. The application runs with `retryCount=3` even though the author thought they set `8`.

This is an example of a **functionally silent failure**: the feature still runs, but uses a different value from what was intended.

If you change the annotation to:

```java
@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        @DefaultValue("3") int retryCount) {
}
```

then `notification.retrty-count` can be flagged as unbound within the bean's scope instead of being accepted as a meaningless member of the configuration group.

**Defaults serve one purpose, and strict binding serves another.** The two tools do not replace each other. Reasonable defaults are helpful; key-name error detection ensures users configure what they intend.

## 7. Distinguishing unknown keys from wrongly typed values

These are two distinct error categories.

### 7.1. Unknown field: unrecognized key name

Bean:

```java
@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(int retryCount) {
}
```

YAML:

```yaml
notification:
  retry-coutn: 4
```

`retry-coutn` is an unknown key relative to `retryCount`.

### 7.2. Invalid field: right name, unconvertible value

YAML:

```yaml
notification:
  retry-count: many
```

Here `retry-count` is the **right name**, yet `many` cannot convert to `int` under normal rules.

Spring Boot provides the `ignoreInvalidFields` option on `@ConfigurationProperties`. Its default is **`false`**, meaning type conversion errors are not ignored by default.

Comparison:

| Situation | Example | Error type |
| --- | --- | --- |
| Wrong key name | `retry-coutn=4` | Unknown / unbound property |
| Unconvertible value | `retry-count=many` | Binding/conversion failure |
| Missing key | No `retry-count` | Missing configuration |
| Key present but invalid for business rules | `retry-count=-4` | Validation/business constraint |
| Wrong prefix | `notificaton.retry-count=4` | May fall outside the bound bean's scope |

`ignoreUnknownFields = false` checks for **unbound keys**, not all of the errors listed above.

**Avoid using `ignoreInvalidFields = true` to bypass type conversion errors** on critical configuration, as the application could continue running without receiving the proper value.

## 8. Adding validation to catch missing or out-of-domain configuration

Even when all key names are valid, values may fail business requirements.

For example, `retry-count=0` converts cleanly to `int`, yet is invalid if the system requires at least 1 attempt.

With Spring Boot 3.x and Jakarta Validation, you can write:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        @NotNull URI endpoint,
        @Min(1) int retryCount,
        @NotNull Duration connectTimeout) {
}
```

Here:

- `ignoreUnknownFields = false` detects keys not bound by the binder within the group scope.
- `@NotNull` requires `endpoint` and `connectTimeout` not to be missing.
- `@Min(1)` requires `retryCount` to be at least 1.
- `@Validated` requests validation on the configuration bean.

To use Jakarta Bean Validation in a typical Spring Boot project, add the `spring-boot-starter-validation` dependency.

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

Validation constraints catch missing or invalid values even when a typo occurs **at the prefix level** and slips past unknown-field checks.

For instance, if `notification.endpoint` is missing because someone typed `notificaton.endpoint`, the binder may leave `endpoint` as `null`. `@NotNull` protects this required field.

**Practical formula for critical configuration: unknown-key checks + type checking + required-value validation.**

## 9. Relaxed binding does not mean ignoring spelling errors

Spring Boot supports **relaxed binding**, allowing multiple valid spellings to map to the same property.

Suppose a record has the component:

```java
int retryCount
```

In Properties or YAML configuration, the canonical form to use is:

```properties
notification.retry-count=4
```

The Binder can support variants in hyphens, casing, camelCase, or underscores depending on the source type. For OS environment variables, the canonical form of `notification.retry-count` is typically expressed as:

```text
NOTIFICATION_RETRYCOUNT
```

Meanwhile, strings such as:

```text
notification.retrty-count
notification.retry-coutn
notification.rety-count
```

contain **actual spelling errors**, not merely different formatting styles.

Understand:

> **Relaxed binding is flexible about how key names are formatted; it is not an autocorrect algorithm for misspelled words.**

If certain name variants are recognized by the binder as the same key, they should not be treated as unknown. So when testing strict mode, use an unambiguous typo like `retry-coutn` rather than just changing `retry-count` to `retryCount`.

Using **canonical kebab-case** in configuration docs, prefix names, and examples reduces the number of formatting variants, making typos easier to spot.

## 10. Nested keys: check the right branch

Real-world configuration often contains nested objects.

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry:
    attempts: 4
    delay: 2s
```

Corresponding record:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        URI endpoint,
        Retry retry) {

    public record Retry(
            int attempts,
            Duration delay) {
    }
}
```

Valid keys include:

```text
notification.endpoint
notification.retry.attempts
notification.retry.delay
```

If YAML is misspelled:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry:
    attemps: 4
    delay: 2s
```

then `notification.retry.attemps` does not match the `attempts` component of the nested record.

When strict binding is enabled on this configuration bean, unbindable properties in the configuration tree under prefix `notification` can cause binding to fail.

However, distinguish a misspelled property in a branch from **the nested branch being completely absent**. If `notification.retry` is not supplied, constructor binding may receive `null` for that branch. Use `@NotNull` together with `@Valid` (and constraints on nested components) if the application requires that branch to always exist and its inner data to be valid.

## 11. Maps and dynamic key names are a special case

Not every name appearing under a prefix needs to match a fixed Java field.

For instance, suppose a user declares a dynamic map:

```yaml
integration:
  labels:
    department: "sales"
    cost-center: "c001"
    owner: "team-a"
```

Record:

```java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "integration",
        ignoreUnknownFields = false)
public record IntegrationProperties(
        Map<String, String> labels) {
}
```

In this design, `department`, `cost-center`, and `owner` are **map data keys**, not three fixed fields on the record. The Binder can bind them into `labels` without treating them as "unknown" simply because the record did not define each name individually.

This means **`ignoreUnknownFields = false` is not a schema validator for the entire contents of a dynamic map**. If the application requires the map to contain only valid labels, use business validation or a more explicit typed structure instead of a map.

For example, if only `department` and `owner` are allowed, a record with two fixed fields and validation is better suited than allowing arbitrary keys in `Map<String,String>`.

## 12. Not every key in `application.yml` belongs in the bean

An `application.yml` file can hold configuration for Spring Boot and many libraries:

```yaml
server:
  port: 9090

management:
  endpoints:
    web:
      exposure:
        include: health,info

notification:
  endpoint: "https://notify.example.invalid"
  retry-count: 3
  connect-timeout: 5s
```

A bean with `prefix = "notification"` is responsible only for the `notification.*` group. There is no reason for that bean to reject `server.port` or `management.endpoints.web.exposure.include` just because it lacks `port` or `include` fields.

That is the clean design boundary of `@ConfigurationProperties`: each class governs a clearly scoped configuration area.

To catch errors in application-owned configuration:

1. Choose distinct, meaningful prefixes such as `notification`, `billing`, `storage`.
2. Register a corresponding `@ConfigurationProperties` bean for each group.
3. Enable unknown-field checks on beans needing strictness.
4. Use validation for required constraints.
5. Test both valid configurations and typo scenarios.

Do not expect a single `NotificationProperties` bean to police every property of Spring Framework, the server, logging, the database, and other libraries.

## 13. Testing key-name errors with `ApplicationContextRunner`

A useful way to confirm the application rejects wrong keys is writing **small-scoped binding tests**. Spring Boot Test provides `ApplicationContextRunner` to spin up a test ApplicationContext with specific properties.

First, use the record:

```java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(
        String endpoint,
        int retryCount) {
}
```

Then write the test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class NotificationPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void acceptsCorrectPropertyNames() {
        runner.withPropertyValues(
                "notification.endpoint=https://notify.example.invalid",
                "notification.retry-count=5"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            NotificationProperties props =
                    context.getBean(NotificationProperties.class);

            assertThat(props.retryCount()).isEqualTo(5);
        });
    }

    @Test
    void rejectsMisspelledPropertyName() {
        runner.withPropertyValues(
                "notification.endpoint=https://notify.example.invalid",
                "notification.retry-coutn=5"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(NotificationProperties.class)
    static class TestConfiguration {
    }
}
```

Meaning of the two tests:

- The first confirms valid key names can bind.
- The second intentionally passes a misspelled key under the same prefix and requires the test context **not to start successfully**.
- `@EnableConfigurationProperties` ensures the bean goes through the binder process.
- `ApplicationContextRunner` isolates the test from the full web server or other dependencies.

In real application tests, you can also inspect the exception type or a representative message for unbound keys. However, exact error messages vary across versions, so avoid asserting against the entire log string.

### 13.1. Testing prefix typos

To guard against completely mistyping `notification` as `notificaton`, a test checking only `hasFailed()` from unknown fields is **not enough**. Add required validation (like `@NotBlank` or `@NotNull`) so failing to receive the main configuration fails the context.

That is why you should test both **unrecognized extra keys** and **missing required keys**.

## 14. Using `@SpringBootTest` to test realistic configuration

When an application has multiple Config Data sources, profiles, and auto-configuration, an integration test can be more suitable than a standalone binder test.

Example:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "notification.endpoint=https://notify.example.invalid",
        "notification.retry-count=7",
        "notification.connect-timeout=2s"
})
class NotificationConfigurationIntegrationTest {

    @Autowired
    private NotificationProperties properties;

    @Test
    void bindsConfiguration() {
        assertThat(properties.retryCount()).isEqualTo(7);
    }
}
```

For the test to run, the application must register `NotificationProperties` via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. Values supplied by `@SpringBootTest(properties=...)` participate in the test's configuration.

For tests expecting bad configuration to fail context startup, `ApplicationContextRunner` is usually more convenient because you can inspect startup failures inside the callback rather than letting the test framework fail before entering the test method.

A standalone test does not guarantee all production environments are correct, but it verifies the bean's defensive behavior at the technical level.

## 15. Help while typing keys: metadata and IDEs

Startup checks are one layer of defense. Another layer is **catching key typos as you author configuration files**.

Spring Boot has a configuration metadata mechanism for `@ConfigurationProperties` types. When an appropriate annotation processor is configured, the project generates metadata so IDEs can autocomplete property names, types, and descriptions.

In a Maven project, the common dependency is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

In Gradle:

```groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
```

Once the IDE, extensions, and build pick up the metadata, writing:

```yaml
notification:
  retry-coutn: 5
```

can trigger an IDE warning that no matching property exists, or omit it from autocomplete suggestions.

Distinguish:

- **Metadata/IDE completion:** assists configuration authors while editing.
- **Strict binding:** checks during actual bean binding in the application.
- **Validation:** checks required constraints and type/domain bounds.
- **Tests:** verify these safeguards actually work in the project.

Do not rely on IDE warnings as your sole proof. A missing IDE plugin, stale metadata, or keys from another library can cause support levels to vary.

## 16. Differences between `@Value` and `@ConfigurationProperties`

`@Value` works well for single values:

```java
@Component
public class NotificationService {

    private final int retryCount;

    public NotificationService(
            @Value("${notification.retry-count:3}") int retryCount) {
        this.retryCount = retryCount;
    }
}
```

If YAML is mistyped as `notification.retry-coutn`, the `notification.retry-count` placeholder finds no value and can fall back to default `3`.

There is no equivalent `ignoreUnknownFields = false` option applying to **all keys** simply by using `@Value` on a regular bean. `@Value` resolves placeholders requested by the bean; it does not automatically validate all extra properties under a namespace.

For a group of properties sharing a responsibility, `@ConfigurationProperties` offers advantages:

- Groups fields in a single Java type.
- Supports systematic relaxed binding.
- Can enable `ignoreUnknownFields = false`.
- Supports centralized validation.
- Can generate IDE metadata.
- Enables constructor binding and immutable design.

That does not mean every `@Value` is wrong. When a bean only needs one standalone value outside a large config group, `@Value` remains concise. But when the primary goal is **not silently ignoring wrong configuration keys**, grouped configuration with `@ConfigurationProperties` provides much clearer control boundaries.

## 17. Other configuration sources can carry wrong keys too

A wrong key does not only appear in YAML. An operator might type:

```bash
java -jar app.jar --notification.retry-coutn=9
```

or put a wrong key in a Properties file:

```properties
notification.retry-coutn=9
```

or pass an environment variable name that does not correspond to the expected property.

With strict binding, the binder can detect unbound properties within the bean's scope and from sources it processes. However, **not every misnamed environment variable is guaranteed to be caught as an unknown property of the bean**: how variables map to configuration names and the source scope involved are part of that process.

Examples of variable-name differences:

```text
Canonical name: notification.retry-count
Standard env var form: NOTIFICATION_RETRYCOUNT

Obvious typo:
NOTIFICATION_RETRTYCOUNT
```

Especially when providing variables via deployment systems, verify:

1. Does the variable actually enter the Java process?
2. Is the variable name mapped by Spring to the expected key?
3. Did a higher-precedence source override it?
4. Is the configuration bean processed by the binder?
5. Does validation catch missing required configuration?

Do not assume that simply setting `ignoreUnknownFields = false` gives the application a full scanner over all environment variables.

## 18. Source precedence and wrong keys are separate issues

Example:

```yaml
# application.yml
notification:
  retry-count: 3
```

Run:

```bash
java -jar app.jar --notification.retry-count=8
```

The effective value can be `8` because command-line arguments take precedence over Config Data.

If changed to:

```bash
java -jar app.jar --notification.retry-coutn=8
```

then the new argument is **not the `notification.retry-count` key**. It can appear as a different property in the environment. If the binder treats that key as unbound within the bean's prefix and `ignoreUnknownFields = false` is active, the application can fail rather than silently using `3`.

Remember: **higher precedence cannot fix a wrong key name**. A higher-precedence source providing a different name does not override the expected property name.

Conversely, if a higher-precedence source supplies the right key, strict binding does not reject it just because a lower-precedence source also supplies that same valid key.

## 19. Enabling strict mode does not mean rejecting every property outside the contract

Consider a file containing:

```yaml
notification:
  endpoint: "https://notify.example.invalid"
  retry-count: 3

database:
  pool-size: 20
```

The `NotificationProperties` bean with prefix `notification` has no obligation to recognize `database.pool-size`. If the application has another bean with prefix `database`, that bean can bind the property above.

Even inside a prefix, a property consumed into a `Map<String,String>` or dynamic-name structure can be valid.

Therefore, design a **clear configuration contract**:

- For fixed-name fields, use concrete Java components.
- For allowed dynamic key sets, use a Map while considering content validation.
- For required fields, use validation.
- For namespaces outside the application, do not try to use a single bean to police everything.

A good strict configuration is not one that rejects everything unknown across the entire JVM; it is one that knows **which scope belongs to each group's responsibility**.

## 20. How to troubleshoot when the application reports an unbound key error

Suppose Spring Boot fails to start and logs mention `notification.retry-coutn` left unbound.

### Step 1: locate the key in effective sources

Check Properties/YAML files, active profiles, command-line arguments, and external configuration sources. Do not look only at a single `application.yml` if the application imports other files or uses multiple environments.

### Step 2: compare against the `@ConfigurationProperties` type

If the record is:

```java
@ConfigurationProperties(
        prefix = "notification",
        ignoreUnknownFields = false)
public record NotificationProperties(int retryCount) {
}
```

the expected canonical name is `notification.retry-count`. The key `notification.retry-coutn` has transposed letters.

### Step 3: fix directly at the source, do not disable protection just to run

Fix:

```yaml
notification:
  retry-count: 5
```

Do not resolve the error by immediately flipping `ignoreUnknownFields = true` before understanding why the key was deemed unknown.

### Step 4: rerun tests or restart the application

Confirm the bean is created and receives the right values. If binding tests exist, rerun both the valid and typo test cases.

### Step 5: check required keys

If the typo caused a required property to disappear, ensure validation annotations or constructor checks still detect missing values after fixing the key name.

### Step 6: review metadata and IDE tooling

If such mistakes happen frequently, configure metadata and IDE hints to catch them earlier. Keep a list of canonical key names in deployment documentation.

This diagnostic routine turns a confusing startup error into a repeatable verification workflow.

## 21. Distinguishing "strict binding" from a standalone schema validator

You can view a `@ConfigurationProperties` bean as a configuration contract for a group of properties. However, `ignoreUnknownFields = false` is not a general-purpose YAML analyzer:

- It does not validate YAML syntax before the parser runs.
- It does not assert that every key across all application files is declared in one global schema.
- It does not validate the business meaning of type-valid values.
- It does not protect secrets or source permissions by itself.
- It does not replace testing each profile and deployment method.
- It does not inspect a file that was never loaded into the environment.

For instance, if broken YAML indentation causes a parser error, that is a syntax/document error, not an unbound-field error. If `retry-count=-2` still converts to `int`, that is a business-validation issue, not an unknown field.

A solid design combines **parser + binder + validation + tests**, instead of piling every responsibility onto one annotation.

## 22. When should `ignoreUnknownFields = false` be enabled?

Disabling unknown-field ignoring usually fits:

1. **Application-owned configuration groups** with a fixed set of fields governed as a contract.
2. **Critical operational parameters** such as retries, timeouts, limits, routing, or feature toggles.
3. **Multi-environment systems** where a typo might not surface in development.
4. **Projects needing fail fast**, stopping early on bad configuration input instead of running with unexpected values.
5. **Teams with configuration tests** and deployment pipelines able to catch and fix errors before production.

Consider carefully when:

- Configuration is shared with components having extensions not owned by the current bean.
- A namespace is designed for dynamic map keys.
- The project is migrating versions and obsolete keys need their status clarified.
- Part of configuration is loaded from a source containing many keys outside the bean's scope.

In these cases, do not pick `true` or `false` by gut feel. Choose the **right prefix boundaries** and data models, then write tests for the actually supported sources.

## 23. A complete design template for critical configuration

Suppose an email-sending application has a configuration group:

```yaml
delivery:
  smtp:
    host: "smtp.example.invalid"
    port: 2525
    connect-timeout: 4s
    retries: 3
```

With Spring Boot 3.x, you can use an immutable record:

```java
package com.example.configdemo;

import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "delivery.smtp",
        ignoreUnknownFields = false)
public record SmtpProperties(
        @NotBlank String host,
        @Min(1) @Max(65535) int port,
        @NotNull Duration connectTimeout,
        @Min(0) int retries) {
}
```

Register via:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

The bean combines:

- **Specific prefix:** manages only `delivery.smtp.*`.
- **Constructor binding:** no setters needed.
- **Unknown-key checking:** `ignoreUnknownFields = false`.
- **Data validation:** `@NotBlank`, `@Min`, `@Max`, `@NotNull`.
- **Semantic types:** `Duration` instead of raw time strings.

A typo:

```yaml
delivery:
  smtp:
    host: "smtp.example.invalid"
    port: 2525
    connect-timeout: 4s
    retrise: 3
```

places `delivery.smtp.retrise` inside the bean's scope without a matching field. Strict binding can reject this configuration.

If instead the operator omits the entire `delivery.smtp` branch, required constraints like `@NotBlank host`, `@Min(1) port`, and `@NotNull connectTimeout` prevent the bean from missing vital inputs.

Do not log the entire configuration object if it might contain an SMTP password. Records auto-generate `toString()`; if secrets are added to a record, printing the record can leak sensitive values.

## 24. Exercise A: spot the misspelled key

Given the record:

```java
@ConfigurationProperties(
        prefix = "payment",
        ignoreUnknownFields = false)
public record PaymentProperties(
        String provider,
        int retryCount,
        boolean auditEnabled) {
}
```

And configuration:

```yaml
payment:
  provider: demo
  retry-count: 4
  audit-enabld: true
```

**Question:** which key is likely to be left unbound?

**Answer:** `payment.audit-enabld`. The expected name is `payment.audit-enabled`, matching the `auditEnabled` component.

**Follow-up:** if `audit-enabld` is changed to `auditEnabled`, is that guaranteed to be an error too?

Not necessarily. Relaxed binding can support valid naming variants; **spelling errors** must be distinguished from **formatting convention differences**. However, use kebab-case `audit-enabled` as the canonical form in YAML.

## 25. Exercise B: wrongly typed value or wrong key?

Given:

```java
@ConfigurationProperties(
        prefix = "queue",
        ignoreUnknownFields = false)
public record QueueProperties(
        int batchSize,
        java.time.Duration pollInterval) {
}
```

Consider three configurations:

**Case 1**

```properties
queue.batch-size=not-a-number
queue.poll-interval=5s
```

**Case 2**

```properties
queue.batch-szie=100
queue.poll-interval=5s
```

**Case 3**

```properties
queue.batch-size=100
queue.poll-interval=5s
```

Answers:

| Case | Issue |
| --- | --- |
| 1 | `batch-size` name is right, but value fails to convert to `int` |
| 2 | `batch-szie` name is wrong and may be flagged as unbound |
| 3 | Both keys match; data can bind successfully |

This exercise shows that `ignoreUnknownFields` and type conversion address two different failure modes.

## 26. Exercise C: is a wrong prefix guaranteed to be caught?

Bean:

```java
@Validated
@ConfigurationProperties(
        prefix = "gateway",
        ignoreUnknownFields = false)
public record GatewayProperties(
        @jakarta.validation.constraints.NotBlank String baseUrl) {
}
```

Configuration source:

```yaml
gatway:
  base-url: "https://gateway.example.invalid"
```

**Question:** does `ignoreUnknownFields = false` alone guarantee catching the `gatway` typo?

**No.** The key lies outside the `gateway` prefix bound by the bean. However, if the bean is registered, validation with `@NotBlank` can catch `baseUrl` being missing/blank.

The best solution is not picking one mechanism over the other, but combining them and testing prefix-typo scenarios.

## 27. Exercise D: unloaded configuration

The application has:

```text
application.yml
application-prod.yml
```

In `application-prod.yml`:

```yaml
notification:
  retrty-count: 5
```

Yet the application runs only with profile `dev` and nothing loads `application-prod.yml`.

**Question:** does `NotificationProperties` strict binding necessarily detect the misspelled key in `application-prod.yml` during this run?

**No.** If that configuration document is not loaded, the binder never sees that key in the current run. Test `prod` profile configurations or use appropriate static checks before deployment.

This exercise explains why configuration tests should cover real profiles, not just development settings.

## 28. Key takeaways

- With `@ConfigurationProperties`, `ignoreUnknownFields` defaults to **`true`**, so some unmapped keys can be ignored.
- Set **`ignoreUnknownFields = false`** when you want the binder to detect unbound keys within a configuration bean's scope.
- This mechanism is scoped by **prefix and actually registered/bound beans**, not a global scanner of all properties from all sources.
- **Wrong key name**, **wrong value type**, **missing value**, **wrong prefix**, and **business-rule violations** are distinct cases.
- `ignoreInvalidFields` relates to binding/conversion failures, while **Bean Validation** enforces required values and business constraints.
- Relaxed binding accepts valid formatting variants, yet **does not autocorrect typos**.
- For maps with dynamic keys, strict binding does not replace schema checks for individual map keys.
- Generate **configuration metadata** and leverage IDE hints to catch errors early while editing configuration.
- Write `ApplicationContextRunner` tests covering both the happy path and misspelled keys causing context failure.
- For critical configuration, the reliable formula is **clear prefixes + strict binding + validation + testing all supported profiles/sources**.
