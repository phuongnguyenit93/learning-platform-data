# Providing Default Values with @DefaultValue in Spring Boot

When using `@ConfigurationProperties` with **constructor binding** or a Java `record`, an application can declare default values directly on constructor parameters or record components using `@DefaultValue`. The Spring Boot Binder uses these defaults **when the corresponding property is absent from configuration sources**, then converts the string declared in the annotation to the target Java type.

This is a structured configuration design that brings property names, data types, and fallback values together into a single Java contract. It is especially useful when you want to:

- Provide sensible defaults for timeouts, retry counts, batch sizes, feature flags, or role lists.
- Keep a group of settings as a read-only record after startup.
- Allow deployment environments to override values without modifying Java code.
- Create a nested configuration object even when no keys exist for that group.
- Avoid repeating `@Value("${property:default}")` expressions across multiple beans.

This lesson uses **Spring Boot 3.3.x and Java 21**. The focus is on the meaning of `@DefaultValue` in the Binder, how to apply it to constructors and records, the annotation's limitations, and practical testing scenarios.

## 1. Where Does @DefaultValue Sit in the Configuration System?

Spring Boot can pull properties from `application.yml`, `application.properties`, environment variables, Java system properties, command-line arguments, and many other sources. Values are aggregated by precedence into `Environment`; `@ConfigurationProperties` uses the **Binder** to map them onto typed objects.

Diagram:

~~~text
application.yml / application-prod.yml
environment variables / system properties / CLI
                       |
                       v
             Environment + Binder
                       |
                       v
        @ConfigurationProperties record
                       |
                       +--> Is the property supplied by a source?
                       |       |
                       |       +--> Yes: bind source value
                       |       |
                       |       +--> No: use @DefaultValue if present
                       |
                       v
                Bound object
~~~

`@DefaultValue` **does not create an additional PropertySource** and does not write a new value into configuration files. It is an instruction to the Binder on how to populate a constructor parameter when no matching property exists.

For instance, suppose you have a record:

~~~java
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(
        @DefaultValue("500") int maxRows) {
}
~~~

If `app.report.max-rows` is absent, the Binder can create `ReportProperties(500)`. However, if the environment supplies `app.report.max-rows=1000`, the value `1000` is used instead of the default.

## 2. Importing and Placing @DefaultValue Correctly

The annotation belongs to Spring Boot:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;
~~~

It is used on:

- **Constructor parameters** of classes using constructor binding.
- **Record components** of Java records using constructor binding.

Record example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("500ms") Duration backoff) {
}
~~~

When these properties are omitted, the three components receive `true`, `3`, and `Duration.ofMillis(500)`.

The annotation is not a mechanism for assigning values to **arbitrary Java fields** and does not replace constructor parameters of regular service beans. It takes effect while the Spring Boot Binder constructs configuration objects.

### Basic API

In Spring Boot 3.3, the conceptual shape of the annotation is:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.PARAMETER, ElementType.RECORD_COMPONENT})
public @interface DefaultValue {
    String[] value() default {};
}
~~~

Notable points:

- The annotation value has type `String[]`; single-string syntax like `@DefaultValue("5s")` is valid.
- Multiple strings can be specified, e.g. `@DefaultValue({"CSV", "JSON"})` for collections.
- `@DefaultValue` **with no arguments** is also valid and has a special meaning for nested objects.
- Each string must be a **valid Java annotation constant**; it is not an expression evaluated at runtime.

## 3. Simple Example with a Java Record

Create `src/main/java/com/example/configdemo/config/ReportProperties.java`:

~~~java
package com.example.configdemo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("500") int maxRows,
        @DefaultValue("10s") Duration timeout,
        @DefaultValue("summary") String format) {
}
~~~

In `src/main/resources/application.yml`, you might declare only:

~~~yaml
app:
  report:
    max-rows: 200
~~~

The Spring Boot Binder reads `maxRows=200` from the file and uses defaults for the missing components:

| Record Component | Property | Final Value in Example | Source |
| --- | --- | --- | --- |
| `enabled` | `app.report.enabled` | `true` | `@DefaultValue("true")` |
| `maxRows` | `app.report.max-rows` | `200` | YAML |
| `timeout` | `app.report.timeout` | `PT10S` | `@DefaultValue("10s")` |
| `format` | `app.report.format` | `summary` | `@DefaultValue("summary")` |

`PT10S` is the ISO-8601 string form produced by `Duration.toString()` representing a 10-second duration.

With a record, components are initialized together via its constructor; no setters are needed, and **`@ConstructorBinding` is not needed** if the record has only its regular eligible constructor.

## 4. Registering the Configuration Bean Before Use

A record annotated with `@ConfigurationProperties` must be registered through a mechanism that supports configuration properties. A common approach is `@ConfigurationPropertiesScan` on the main class:

~~~java
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
~~~

`ReportProperties` resides under `com.example.configdemo`, so it is scanned. An alternative is:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ReportProperties.class)
public class ConfigDemoApplication {
    // main method...
}
~~~

In the second option, add the import for your project's `ReportProperties`. Typically only **one** registration mechanism is needed for a class.

Do not place `@Component` on a constructor-bound record expecting Spring to automatically bind all constructor parameters from `Environment`. For constructor binding, Spring Boot requires registration via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, rather than regular `@Component`/`@Bean` creation mechanisms.

### Reading Values from the Bean

~~~java
package com.example.configdemo;

import com.example.configdemo.config.ReportProperties;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportPrinter {

    @Bean
    ApplicationRunner printReportSettings(ReportProperties settings) {
        return args -> {
            System.out.println("enabled = " + settings.enabled());
            System.out.println("maxRows = " + settings.maxRows());
            System.out.println("timeout = " + settings.timeout());
            System.out.println("format = " + settings.format());
        };
    }
}
~~~

With the YAML in Section 3, expected output:

~~~text
enabled = true
maxRows = 200
timeout = PT10S
format = summary
~~~

Components are simply consumed as typed data; services do not need to call `Environment.getProperty` or parse timeout strings manually.

## 5. Defaults Apply Only When the Property Is Not Found

This is the core rule of `@DefaultValue`:

> The value in the annotation is only used if the Binder **cannot find the property** in the property sources. If the property exists, the source value is bound; the annotation does not overwrite it.

Example:

~~~java
@ConfigurationProperties(prefix = "app.search")
public record SearchProperties(
        @DefaultValue("20") int pageSize,
        @DefaultValue("false") boolean debug) {
}
~~~

Scenarios:

| Configuration Provided | `pageSize` | `debug` |
| --- | ---: | --- |
| Neither property present | 20 | false |
| `app.search.page-size=50` | 50 | false |
| `app.search.debug=true` | 20 | true |
| Both properties supplied | Supplied value | Supplied value |

**An empty value does not mean the property does not exist.** The Spring Boot 3.3 API documentation explicitly states that when a property is present in the Environment, `@DefaultValue` is not used even if the property's value is empty.

Example:

~~~properties
app.search.page-size=
~~~

Because `app.search.page-size` is present with an empty string, do not expect it to automatically receive the default `20`. The subsequent outcome depends on the Binder, the target type, and conversion/validation; it can lead to an unexpected value or a binding failure. If you want empty values treated like missing ones, add explicit validation rules suited to your domain.

### Missing Property vs. Empty Property

~~~text
app.search.page-size is absent from all PropertySources
    → Binder considers @DefaultValue("20")

app.search.page-size has value "50"
    → Binder uses 50

app.search.page-size is present with value ""
    → @DefaultValue is not automatically chosen just because the string is empty
~~~

Keep this rule distinct from how your application handles null/blank values after binding.

## 6. Type Conversion from Annotation Strings

Although `@DefaultValue` takes strings, the Binder converts them to the target parameter types using Spring Boot's conversion service.

Example:

~~~java
package com.example.configdemo.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.download")
public record DownloadProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("4") int maxParallel,
        @DefaultValue("3s") Duration connectTimeout,
        @DefaultValue("10MB") DataSize maxSize,
        @DefaultValue("https://download.example.org") URI endpoint) {
}
~~~

The defaults represent:

- `true` → `boolean`.
- `4` → `int`.
- `3s` → three-second `Duration`.
- `10MB` → `DataSize`.
- `https://download.example.org` → `URI`.

Use suffixed time and size units to avoid ambiguity. For example, `"3s"` is clearer than `"3000"` when the Java type is `Duration`.

### Duration and @DurationUnit

Example:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DurationUnit;

public record Limits(
        @DurationUnit(ChronoUnit.SECONDS)
        @DefaultValue("30")
        Duration timeout) {
}
~~~

In this case, `@DurationUnit(ChronoUnit.SECONDS)` specifies how to interpret a unitless value. When the property is absent, the default `"30"` can be converted to 30 seconds. Declaring `@DefaultValue("30s")` embeds the unit directly in the string, which is usually easier to read.

### Unconvertible Values

~~~java
@DefaultValue("ten") int maxAttempts
~~~

`ten` is not a valid integer string. When the Binder needs to use this default to create the bean, converting to `int` can fail, preventing the application from starting. `@DefaultValue` does not bypass data-type checking.

When using an enum, the default string must match the enum or the active conversion rules. For a custom type, if the conversion service lacks an appropriate converter, the default value will also fail to bind.

## 7. Defaults for Enums

Suppose an application has business logging levels:

~~~java
package com.example.configdemo.config;

public enum ReportMode {
    SUMMARY,
    DETAIL,
    ARCHIVE
}
~~~

Record:

~~~java
package com.example.configdemo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.report")
public record ReportModeProperties(
        @DefaultValue("SUMMARY") ReportMode mode) {
}
~~~

If `app.report.mode` is not declared, the default mode is `ReportMode.SUMMARY`.

However, if you have:

~~~yaml
app:
  report:
    mode: DETAIL
~~~

the configured value `DETAIL` is bound instead of the default. If an operator enters a value that cannot be converted to `ReportMode`, binding fails; defaults do not automatically replace an existing value that has an invalid type.

## 8. Defaults for Lists and Arrays

The `@DefaultValue` API accepts a string array. This allows specifying one or more default elements for collection or array properties.

Example:

~~~java
package com.example.configdemo.config;

import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.export")
public record ExportProperties(
        @DefaultValue({"CSV", "JSON"}) List<String> formats,
        @DefaultValue({"vn", "sg"}) String[] regions) {
}
~~~

When `app.export.formats` and `app.export.regions` are absent:

~~~text
formats = [CSV, JSON]
regions = ["vn", "sg"]
~~~

If the YAML file supplies:

~~~yaml
app:
  export:
    formats:
      - XML
~~~

`formats` takes the value from YAML and **does not append** `CSV` or `JSON` from the annotation. At that point, `@DefaultValue` is unused because the property already has data from a configuration source.

### Distinguish from List Merging Across Sources

In Spring Boot, configuration lists across multiple sources normally follow a **replace the entire list** rule from the higher-precedence source, rather than appending elements by default. `@DefaultValue({"CSV", "JSON"})` is simply a default set used when the property is absent, not a list-merging rule.

If you need per-element defaults while still allowing customization, design a dedicated configuration contract or explicit logic in the application.

### What About Maps?

`@DefaultValue` is not a general-purpose syntax for describing complex YAML/Map structures inline in an annotation. For configuration with dynamic keys, use YAML/properties files, constructor binding on suitable nested objects, or a deliberate defaults builder. Do not assume passing a JSON string into `@DefaultValue` automatically turns into `Map<String,String>` without a corresponding converter.

## 9. Defaults for Nested Configuration: Argument-Less @DefaultValue

This is the most easily overlooked feature of the annotation. Suppose configuration has a nested object:

~~~yaml
app:
  email:
    enabled: true
~~~

You create a record:

~~~java
@ConfigurationProperties(prefix = "app.email")
public record EmailProperties(
        boolean enabled,
        Smtp smtp) {

    public record Smtp(
            @DefaultValue("localhost") String host,
            @DefaultValue("2525") int port) {
    }
}
~~~

If the YAML file **contains no keys under `app.email.smtp`**, the `smtp` object can be `null` in constructor binding. Defaults on `Smtp.host` and `Smtp.port` **do not automatically force the Binder to create an `Smtp` when the entire nested group is absent**.

If a service calls:

~~~java
properties.smtp().host();
~~~

it can hit a `NullPointerException` when `smtp()` is `null`.

### Solution: Empty @DefaultValue on the Nested Parameter

~~~java
package com.example.configdemo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.email")
public record EmailProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue Smtp smtp) {

    public record Smtp(
            @DefaultValue("localhost") String host,
            @DefaultValue("2525") int port) {
    }
}
~~~

`@DefaultValue` **with no arguments** on `Smtp smtp` tells the Binder that this nested object should be created even when no properties belong to the `smtp` group.

Because the nested record declares defaults for `host` and `port`, the object is created with:

~~~text
EmailProperties(
    enabled = true,
    smtp = Smtp(
        host = "localhost",
        port = 2525
    )
)
~~~

If configuration specifies:

~~~yaml
app:
  email:
    smtp:
      host: mail.example.org
~~~

the result will be `smtp.host=mail.example.org` and `smtp.port=2525`. Nested component defaults are still evaluated individually when their corresponding properties are missing.

### Empty @DefaultValue Is Not an Empty String

Distinguish:

~~~java
@DefaultValue Smtp smtp
~~~

from:

~~~java
@DefaultValue("") String hostname
~~~

The first is an instruction to instantiate a nested object. The second declares an **empty string value** as the default for a `String` parameter. Their meanings are completely different.

If the nested object does not need to exist unconditionally, you can omit the empty `@DefaultValue`, let missing configuration be represented as `null`, and handle it appropriately in business logic. You are not required to instantiate every nested configuration group.

## 10. Nested @DefaultValue and Validation Constraints

Suppose default values must satisfy application rules. Combine Bean Validation with `@ConfigurationProperties`:

~~~java
package com.example.configdemo.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.email")
public record EmailProperties(
        @DefaultValue("true") boolean enabled,
        @Valid @NotNull @DefaultValue Smtp smtp) {

    public record Smtp(
            @NotBlank @DefaultValue("localhost") String host,
            @Min(1) @DefaultValue("2525") int port) {
    }
}
~~~

In a Gradle project, you can include:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

- `@Validated` requests constraint checking when binding the configuration-properties bean.
- `@Valid` cascades validation to nested members.
- `@NotNull` expresses that `smtp` is a required configuration group at the object level, even though a default constructs it.
- `@NotBlank` ensures hostname has content.
- `@Min(1)` ensures port is not less than 1.

**Default does not mean valid.** Using `@DefaultValue("0")` on port with `@Min(1)` lets the binder supply `port = 0`, yet validation will report an error. Design defaults to comply with business constraints.

For other fields such as positive timeouts, valid endpoint schemes, or max retry limits, apply validation as needed. `@NotNull` alone on a `Duration` does not guarantee the duration is greater than 0.

## 11. On a Class Constructor Instead of a Record

`@DefaultValue` is not limited to records. For an immutable class with a single eligible constructor, place the annotation on each parameter:

~~~java
package com.example.configdemo.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.session")
public final class SessionProperties {

    private final int maxSessions;
    private final Duration idleTimeout;

    public SessionProperties(
            @DefaultValue("100") int maxSessions,
            @DefaultValue("30m") Duration idleTimeout) {

        this.maxSessions = maxSessions;
        this.idleTimeout = idleTimeout;
    }

    public int getMaxSessions() {
        return maxSessions;
    }

    public Duration getIdleTimeout() {
        return idleTimeout;
    }
}
~~~

In Spring Boot 3.3, a class with only one parameterized constructor is normally considered for constructor binding when registered via the configuration properties mechanism. No setters need to be written for `final` fields.

Benefits of this style:

- You can control logic inside the constructor.
- You can preserve traditional getter APIs for older Java code.
- You can add invariants or derived calculations if truly necessary.

With a record, Java generates the canonical constructor and accessors automatically, making code more concise. Choose based on project scale, compatibility needs, and architecture.

### When a Class Has Multiple Constructors

If a class has multiple constructors and choosing which one to bind is no longer obvious, Spring Boot supports `@ConstructorBinding` on the appropriate constructor:

~~~java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.DefaultValue;

public class ClientProperties {

    private final String baseUrl;
    private final int retries;

    public ClientProperties() {
        this("http://localhost:8080", 3);
    }

    @ConstructorBinding
    public ClientProperties(
            @DefaultValue("http://localhost:8080") String baseUrl,
            @DefaultValue("3") int retries) {
        this.baseUrl = baseUrl;
        this.retries = retries;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public int getRetries() {
        return retries;
    }
}
~~~

To use this class as configuration properties, add `@ConfigurationProperties(prefix="app.client")` to the class and register it via configuration-properties scanning or enabling. The snippet focuses on constructor selection rather than showing the full application class.

Note that the `@ConstructorBinding` package in Spring Boot 3.x is `org.springframework.boot.context.properties.bind.ConstructorBinding`. Do not confuse it with the older package from previous Spring Boot versions.

## 12. How Does @DefaultValue Differ from Defaults in @Value?

`@Value` uses property placeholders:

~~~java
@Value("${app.session.max-sessions:100}")
private int maxSessions;
~~~

Whereas constructor binding uses:

~~~java
@ConfigurationProperties(prefix = "app.session")
public record SessionProperties(
        @DefaultValue("100") int maxSessions) {
}
~~~

Both can yield the same result when a property is missing and conversion succeeds, yet they operate at **two different architectural layers**:

| Criterion | `@Value("${key:default}")` | `@DefaultValue("default")` |
| --- | --- | --- |
| Where used | Field, constructor parameter, or method parameter injection point | Constructor parameter / record component of configuration properties |
| Mechanism | Property placeholder resolution at the usage site | ConfigurationProperties Binder |
| Scope | A single value or expression | A component in a structured configuration object |
| Type conversion | At the injection point | Binder's conversion service |
| Value source | Environment and corresponding expression mechanisms | Environment via the Binder |
| Default data | Text inside the placeholder | Constant strings from the annotation |
| Expressing nested objects | Not its primary purpose | Can use empty `@DefaultValue` to bind nested objects |
| Placeholders inside defaults | Can participate in placeholder resolution per context | **Does not support placeholder resolution inside `@DefaultValue`** |

### Example Not to Write

~~~java
@DefaultValue("${APP_TIMEOUT:5s}") Duration timeout
~~~

In Spring Boot 3.3, **`@DefaultValue` does not support property placeholder resolution**; the API documentation specifies that values are constants. Do not expect the annotation above to read `APP_TIMEOUT` from the Environment or pick `5s` when the variable is missing.

### Right Way to Allow Environment Overrides

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @DefaultValue("5s") Duration timeout) {
}
~~~

Then operators can set:

~~~bash
export APP_CLIENT_TIMEOUT="8s"
java -jar config-demo.jar
~~~

In this case, the Binder finds `app.client.timeout` via the environment variable and uses `8s`, while `5s` is only used when the property is absent.

This keeps configuration sources independent of the annotation and follows Spring Boot's standard precedence order.

## 13. Defaults in YAML or in Java?

The same fallback value can be supplied in multiple places, with different operational implications.

### 13.1. Putting Defaults in @DefaultValue

~~~java
@ConfigurationProperties(prefix = "app.task")
public record TaskProperties(
        @DefaultValue("3") int retries) {
}
~~~

Suitable when `3` is a default of the **Java contract**, independent of deployment environment. Even if no file declares the key, the Binder can create the object with a clear value.

### 13.2. Putting Defaults in application.yml

~~~yaml
app:
  task:
    retries: 3
~~~

Suitable when defaults should be visible and adjustable via deployment configuration. `application-prod.yml` or higher-precedence sources can override it via Spring Boot's precedence rules.

### 13.3. Using a Java Constructor to Set Defaults Manually

A record can contain constructor logic:

~~~java
public record LocalSettings(String region) {

    public LocalSettings {
        if (region == null || region.isBlank()) {
            region = "vn";
        }
    }
}
~~~

However, this is **Java logic** that runs whenever the record is instantiated, including when you call `new LocalSettings(null)` in unit tests. By contrast, `@DefaultValue` is applied by the Binder only when a property is missing, and does not run when Java constructs the object manually.

If the requirement is "set a default only when operators do not supply the property," `@DefaultValue` expresses that intent more closely. If the requirement is "every created object must normalize invalid/blank data," constructor logic can be a deliberate choice.

### Avoid Conflicting Overlapping Defaults

Example:

~~~yaml
app:
  task:
    retries: 5
~~~

~~~java
@DefaultValue("3") int retries
~~~

There is no runtime conflict at binding time: because YAML supplies the property, the effective value is `5`. Yet for human readers, two different numbers in two places can be misleading. Document clearly which values are **code defaults** and which are **operational values**.

## 14. Primitive Types, Reference Types, and Missing Values

If constructor binding receives no property and has no `@DefaultValue`, the component's value depends on its type:

| Java Type | When Property Is Missing and No @DefaultValue |
| --- | --- |
| `int` | Typically receives the primitive default `0` |
| `boolean` | Typically receives the primitive default `false` |
| `String` | Can be `null` |
| `Duration` | Can be `null` |
| Nested object | Can be `null` if no child properties exist |
| Collection | Can be `null` when no data is bound |

Example:

~~~java
@ConfigurationProperties(prefix = "app.job")
public record JobProperties(
        int attempts,
        boolean enabled,
        Duration delay) {
}
~~~

When no keys exist under `app.job`, relying on `0`/`false`/`null` may fail to reflect business requirements. Some missing properties should **fail**, while others should have defaults.

Use annotations to define the contract properly:

~~~java
@ConfigurationProperties(prefix = "app.job")
public record JobProperties(
        @DefaultValue("1") int attempts,
        @DefaultValue("true") boolean enabled,
        @DefaultValue("1s") Duration delay) {
}
~~~

Do not use `@DefaultValue` to hide a required property such as a secret or a production endpoint. For those fields, omit the default and use validation so startup fails when configuration is incomplete.

## 15. Impact of Profiles and Other Configuration Sources

`@DefaultValue` only takes effect after the Binder checks data across effective property sources. It **does not override** values from `application-prod.yml`, environment variables, or CLI arguments.

Example:

~~~java
@ConfigurationProperties(prefix = "app.batch")
public record BatchProperties(
        @DefaultValue("100") int chunkSize,
        @DefaultValue("5s") Duration timeout) {
}
~~~

`application.yml`:

~~~yaml
app:
  batch:
    chunk-size: 250
~~~

`application-prod.yml`:

~~~yaml
app:
  batch:
    timeout: 2s
~~~

Default run:

~~~text
chunkSize = 250 (application.yml)
timeout   = 5s  (@DefaultValue)
~~~

Run with the prod profile:

~~~bash
java -jar config-demo.jar --spring.profiles.active=prod
~~~

Result:

~~~text
chunkSize = 250 (application.yml)
timeout   = 2s  (application-prod.yml)
~~~

If you add:

~~~bash
java -jar config-demo.jar --spring.profiles.active=prod --app.batch.chunk-size=500
~~~

`chunkSize` becomes `500`. That is the CLI value, not the annotation value.

**In summary:** PropertySource precedence determines what value a property has; `@DefaultValue` only supplies data when the Binder finds no corresponding property. Do not treat it as a way to alter precedence order.

## 16. Testing @DefaultValue Without Depending on Many Files

Spring Boot Test provides `ApplicationContextRunner` to spin up lightweight contexts, convenient for testing binding and defaults.

Assuming `ReportProperties` from Section 3 exists, create a test:

~~~java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.configdemo.config.ReportProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

class ReportPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BindingConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ReportProperties.class)
    static class BindingConfig {
    }

    @Test
    void usesDefaultsWhenPropertiesAreMissing() {
        runner.run(context -> {
            ReportProperties properties =
                    context.getBean(ReportProperties.class);

            assertThat(properties.enabled()).isTrue();
            assertThat(properties.maxRows()).isEqualTo(500);
            assertThat(properties.timeout().toSeconds()).isEqualTo(10);
            assertThat(properties.format()).isEqualTo("summary");
        });
    }

    @Test
    void suppliedValuesOverrideDefaults() {
        runner.withPropertyValues(
                "app.report.enabled=false",
                "app.report.max-rows=200",
                "app.report.timeout=4s",
                "app.report.format=detail")
                .run(context -> {
                    ReportProperties properties =
                            context.getBean(ReportProperties.class);

                    assertThat(properties.enabled()).isFalse();
                    assertThat(properties.maxRows()).isEqualTo(200);
                    assertThat(properties.timeout().toSeconds())
                            .isEqualTo(4);
                    assertThat(properties.format()).isEqualTo("detail");
                });
    }
}
~~~

The test uses `spring-boot-starter-test`, JUnit Jupiter, and AssertJ. Two cases prove:

1. When no properties are supplied, the Binder uses the `@DefaultValue` annotations.
2. When properties are present in the test Environment, the Binder uses those values instead of defaults.

This tests `@ConfigurationProperties` binding, not values assigned during manual Java constructor calls.

### Verifying @DefaultValue Does Not Affect Manual Java Constructors

~~~java
ReportProperties manual =
        new ReportProperties(false, 0, null, null);
~~~

The result is that those exact arguments are **passed directly into the constructor**, rather than becoming `true`/`500`/`10s`/`summary`. `@DefaultValue` does not execute in the JVM like a default assignment statement; it requires the Spring Boot Binder.

### Testing Nested Defaults

With `EmailProperties` from Section 9, tests can verify:

~~~java
assertThat(properties.smtp()).isNotNull();
assertThat(properties.smtp().host()).isEqualTo("localhost");
assertThat(properties.smtp().port()).isEqualTo(2525);
~~~

If you want to verify error diagnostics, you can inspect `context.getStartupFailure()` in `ApplicationContextRunner` when intentionally passing an invalid property. Exact exception messages may vary across versions.

## 17. Common Mistakes

### Mistake 1 — Importing the Wrong Annotation

The `@DefaultValue` for Spring Boot configuration properties has the fully qualified name:

~~~java
org.springframework.boot.context.properties.bind.DefaultValue
~~~

Check that your IDE imported the right package. Another library's annotation with a similar name will not be recognized by the Binder.

### Mistake 2 — Placing @DefaultValue on a @Component Field

~~~java
@Component
class TaskService {
    @DefaultValue("3")
    private int retries;
}
~~~

This is not a valid use of the annotation in these examples (it is defined for constructor parameters and record components). Use `@ConfigurationProperties` for configuration groups or `@Value` at appropriate injection points.

### Mistake 3 — Forgetting to Register Configuration Properties

~~~java
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(
        @DefaultValue("500") int maxRows) {
}
~~~

Without `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(ReportProperties.class)`, Spring may not create the configuration bean for injection. Bean registration is a separate prerequisite and is not replaced by `@DefaultValue`.

### Mistake 4 — Using Placeholders Inside @DefaultValue

~~~java
@DefaultValue("${APP_TIMEOUT:5s}") Duration timeout
~~~

The `DefaultValue` documentation states that **property placeholder resolution is not supported**. Declare `@DefaultValue("5s")` and let the environment override it via a real property such as `APP_CLIENT_TIMEOUT`.

### Mistake 5 — Expecting the Default When a Property Has an Empty String

~~~properties
app.report.format=
~~~

Here the property is present with an empty value; `@DefaultValue("summary")` is not automatically selected because a value is present. To forbid empty strings, use Bean Validation such as `@NotBlank`.

### Mistake 6 — Nested Object Remains Null

~~~java
public record EmailProperties(
        Smtp smtp) {
    public record Smtp(@DefaultValue("localhost") String host) {}
}
~~~

If there are no `app.email.smtp.*` properties, `smtp` can be null. Add an empty `@DefaultValue` before `Smtp smtp` if you want the nested object always created.

### Mistake 7 — Default Cannot Be Converted to the Target Type

~~~java
@DefaultValue("five") int retries
~~~

When the Binder has to use this default, conversion will fail. For `Duration`, write values with explicit units like `"5s"` or `"250ms"`.

### Mistake 8 — Confusing Defaults with Validation

~~~java
@Min(1)
@DefaultValue("0")
int retries
~~~

The annotation supplies the integer `0`, yet it violates the constraint. Choose a valid default or omit the default to require operators to supply the configuration.

### Mistake 9 — Putting Defaults on Required Secrets

~~~java
@DefaultValue("password")
String password
~~~

This is a dangerous design for production environments. If a password is required, do not put a fake or insecure value just to let the application start. Use proper secret sources and validation to detect missing configuration.

### Mistake 10 — Assuming the Annotation Modifies Environment

Defaults from `@DefaultValue` belong to data bound onto the object. Do not assume `environment.getProperty("app.report.max-rows")` will return `"500"` just because the record has `@DefaultValue("500")`. When no source defines the property, `Environment` can return null while `ReportProperties.maxRows()` returns 500.

### Mistake 11 — Treating Collection Defaults as List Appending

~~~java
@DefaultValue({"CSV", "JSON"}) List<String> formats
~~~

When configuration sets `app.export.formats=[XML]`, the list does not become `[CSV, JSON, XML]` just because the annotation has two elements. Defaults apply only when no matching property exists.

### Mistake 12 — Confusing with Default Profiles

The Binder's `@DefaultValue` is unrelated to `spring.profiles.default` or `ConfigurableEnvironment.setDefaultProfiles(...)`. One populates missing property values during object creation; the other manages profiles used when no active profiles are set.

## 18. Guide to Designing a Configuration Group with Sensible Defaults

Suppose a file-processing service needs:

- A default worker count.
- A file-size limit.
- A processing timeout.
- A list of input formats.
- A group of retry settings.
- A required output directory.

You can design:

~~~java
package com.example.configdemo.config;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.processor")
public record ProcessorProperties(
        @Min(1) @DefaultValue("2") int workers,
        @NotNull @DefaultValue("20MB") DataSize maxFileSize,
        @NotNull @DefaultValue("30s") Duration timeout,
        @DefaultValue({"CSV", "JSON"}) List<String> acceptedFormats,
        @Valid @NotNull @DefaultValue Retry retry,
        @NotNull Path outputDir) {

    public record Retry(
            @Min(1) @DefaultValue("3") int attempts,
            @NotNull @DefaultValue("200ms") Duration backoff) {
    }
}
~~~

In this case, `outputDir` has no default because the system requires an actual deployment path. The YAML file can supply:

~~~yaml
app:
  processor:
    output-dir: /var/app/output
    workers: 4
~~~

The remaining fields take defaults from the annotations. When running under different profiles or environment variables, operators can override any field with its corresponding property.

Benefits:

- Services inject **one typed object**.
- Defaults are declared right beside their data types.
- The nested group (`retry`) still receives values even when YAML omits the `retry` section.
- Business constraints like `workers >= 1` are enforced.
- `outputDir` remains mandatory and is not masked by a fake default.

A consuming bean:

~~~java
package com.example.configdemo.service;

import com.example.configdemo.config.ProcessorProperties;
import org.springframework.stereotype.Service;

@Service
public class FileProcessor {

    private final ProcessorProperties properties;

    public FileProcessor(ProcessorProperties properties) {
        this.properties = properties;
    }

    public int workers() {
        return properties.workers();
    }

    public java.time.Duration retryBackoff() {
        return properties.retry().backoff();
    }
}
~~~

No need to inject individual property strings separately; everything is accessed through a typed Java structure.

## 19. Practice Exercises

### Exercise 1 — Predict Default Values

Given:

~~~java
@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("30s") Duration ttl,
        @DefaultValue("100") int maxEntries) {
}
~~~

`application.yml` only contains:

~~~yaml
app:
  cache:
    max-entries: 250
~~~

What are the values of `enabled`, `ttl`, and `maxEntries`?

**Answer:** `true`, `Duration.ofSeconds(30)`, and `250`. The `max-entries` property is present, so it overrides the default of 100.

### Exercise 2 — Supplying Values via Command-Line Argument

Keep `CacheProperties` above and run:

~~~bash
java -jar config-demo.jar --app.cache.ttl=45s
~~~

Assuming no higher-precedence source overrides it, what is `ttl`?

**Answer:** `Duration.ofSeconds(45)`, because the CLI value is present so `@DefaultValue("30s")` is not used.

### Exercise 3 — Creating a Default Nested Object

Given:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        Smtp smtp) {

    public record Smtp(
            @DefaultValue("localhost") String host,
            @DefaultValue("1025") int port) {
    }
}
~~~

When `app.mail.smtp.*` is absent, update the record so `properties.smtp().host()` is still accessible.

**Answer:** add an empty `@DefaultValue` before `Smtp smtp`:

~~~java
public record MailProperties(
        @DefaultValue Smtp smtp) {
    // ...
}
~~~

### Exercise 4 — Distinguish Empty String and Missing Property

Given:

~~~java
@DefaultValue("summary") String format
~~~

Compare two runs:

~~~text
Run A: app.report.format is absent
Run B: app.report.format=
~~~

**Answer:** In Run A, the Binder can use the default `summary`. In Run B, the property is present but empty; you cannot rely on the annotation to automatically replace it with `summary`. If non-blank values are required, add validation.

### Exercise 5 — Fix the Broken Annotation

~~~java
@DefaultValue("${APP_TIMEOUT:5s}") Duration timeout
~~~

Fix this so the default is 5 seconds while still allowing overrides via `APP_CLIENT_TIMEOUT`.

**One solution:** declare `@ConfigurationProperties(prefix="app.client")` and component `@DefaultValue("5s") Duration timeout`. When an override is needed, set `APP_CLIENT_TIMEOUT=10s`.

### Exercise 6 — Declaring Collection Defaults

Create a record with `List<String> regions` defaulting to `vn` and `sg`. Verify that when YAML supplies `regions: [th]`, the effective list does not automatically append all three elements.

**One solution:**

~~~java
@ConfigurationProperties(prefix = "app.region")
public record RegionProperties(
        @DefaultValue({"vn", "sg"}) List<String> regions) {
}
~~~

### Exercise 7 — Checking Validation

Create `ProcessorProperties` with `@Min(1) @DefaultValue("0") int workers`. Run without `app.processor.workers`. Explain why binding can produce an integer value while validation reports an error.

**Answer:** A default is a bound value, not a guarantee of validity; `0` violates the `@Min(1)` constraint.

### Exercise 8 — Distinguishing Java Instantiation from the Binder

Given:

~~~java
@ConfigurationProperties(prefix = "app.job")
public record JobProperties(
        @DefaultValue("3") int attempts) {
}
~~~

Compare:

~~~java
JobProperties direct = new JobProperties(0);
~~~

with a bean bound by Spring Boot when the property is missing.

**Answer:** The manually constructed object holds `attempts=0`; the bean created by the Binder when the property is missing can use `attempts=3`. The annotation is not Java code executed on every constructor call.

## 20. Summary

`@DefaultValue` is a mechanism of the **Spring Boot ConfigurationProperties Binder** for constructor binding and Java records. The annotation contains constant strings; the Binder uses them when no corresponding property is found, then converts them to target types through the conversion service. If a property already has a value, the source value takes precedence; **even an empty property does not automatically trigger the default**.

The `@DefaultValue("...")` form is useful for scalars, enums, `Duration`, `DataSize`, collections, and other types with suitable converters. The **argument-less `@DefaultValue`** form instructs the Binder to instantiate a nested object even when no child properties exist. The annotation does not support `${...}` placeholder resolution inside its value, does not affect objects instantiated with `new`, and does not replace validation for required configuration.

Used alongside `@ConfigurationProperties`, `@ConfigurationPropertiesScan`, and Bean Validation, `@DefaultValue` helps define a structured, reusable configuration contract that adapts cleanly across environments without scattering default values throughout services.

## References

- [Spring Boot 3.3 — Externalized Configuration: Constructor Binding and @DefaultValue](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding)
- [Spring Boot 3.3 — DefaultValue Annotation API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/DefaultValue.html)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 — ConfigurationProperties Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
