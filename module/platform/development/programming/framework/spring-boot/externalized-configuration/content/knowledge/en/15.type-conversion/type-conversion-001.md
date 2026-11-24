# The Role of ConversionService in Configuration Binding

## 1. Why Does Configuration Binding Need Type Conversion?

In Spring Boot Externalized Configuration, configuration values can be supplied from many sources: `application.yml`, `application.properties`, environment variables, Java system properties, command-line arguments, and additional Config Data sources. Many of these sources represent values as text, whereas Java code needs to work with **specific data types**.

For example:

```yaml
delivery:
  endpoint: "https://delivery.example.invalid"
  timeout: 3s
  max-attempts: 5
  enabled: true
  max-payload: 2MB
```

The application wants to consume the configuration as:

```java
URI endpoint;
Duration timeout;
int maxAttempts;
boolean enabled;
DataSize maxPayload;
```

Turning `"3s"` into `Duration.ofSeconds(3)`, `"5"` into an integer, or `"2MB"` into a `DataSize` object is not a plain string assignment.

This is why **Spring's type conversion system**, particularly the `ConversionService` interface and the converters registered with it, plays a critical role in the `@ConfigurationProperties` **binding** process.

Key idea of this lesson:

> The binder decides which property corresponds to which Java member; the type conversion system helps produce a properly typed Java value for that member.

The two responsibilities are related, but they are not synonymous.

## 2. From Configuration Source to Java Object: The Entire Flow

Suppose `application.yml` declares:

```yaml
client:
  connect-timeout: 5s
  retry-count: 4
  enabled: false
```

And the configuration class:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        Duration connectTimeout,
        int retryCount,
        boolean enabled) {
}
```

You can visualize the process as:

```text
application.yml / environment / CLI arguments / Config Data
                       |
                       v
             Spring Environment
                       |
                       v
           ConfigurationProperties Binder
                       |
           1. Identify the "client" prefix
           2. Find matching properties
           3. Map names to Java members
                       |
                       v
                 Type conversion
                (ConversionService)
                       |
             "5s"   -> Duration
             "4"    -> int
             "false"-> boolean
                       |
                       v
          ClientProperties object
                       |
                       v
        Spring service receives the bean via DI
```

In this example, Spring Boot handles selecting the source with the appropriate precedence, resolving property names, converting values, and instantiating the bean.

**`ConversionService` does not decide which YAML file is loaded, which profile is active, or which source has higher precedence.** It participates at the stage where a located value needs to be converted to the appropriate target type.

If the `client.retry-count` key does not exist or is misspelled, merely adding a `String → Integer` converter cannot make the binder look up a different key name. That is a name lookup/binding and configuration control issue, not a type conversion issue.

## 3. What Is ConversionService?

In the Spring Framework, `ConversionService` is an interface that provides the ability to **convert a value from a source type to a target type**. Familiar methods include:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);
```

Conceptual example:

```java
String raw = "42";
Integer number = conversionService.convert(raw, Integer.class);
```

If the service has a suitable converter, the result is the integer `42`.

However, `ConversionService` is not an "any-type-to-any-type" converter. It needs a **registered converter** or a corresponding conversion mechanism. If no matching conversion path exists, the conversion can fail.

Related interfaces:

| Component | Role |
| --- | --- |
| `ConversionService` | Provides the API to check and perform conversions |
| `Converter<S, T>` | Implements conversion from a source type `S` to a target type `T` |
| `ConverterFactory<S, R>` | Provides converters for a family of target types under `R` |
| `GenericConverter` | Handles more general conversions with type descriptor information |
| `ConditionalGenericConverter` | Can decide whether a type pair is supported in a specific context |
| `ApplicationConversionService` | A `ConversionService` prepared by Spring Boot with many conversions useful for configuration |

At the Spring Framework layer, `DefaultConversionService` is an implementation containing common converters. Spring Boot adds a more convenient set of conversions for Boot applications, including duration and data size types commonly seen in configuration.

## 4. Spring Boot's ApplicationConversionService

Spring Boot provides `org.springframework.boot.convert.ApplicationConversionService`, a `ConversionService` with many standard conversions tailored for applications.

It builds on the Spring Framework conversion infrastructure and adds interpretations that make sense in Boot configuration. For example, a timeout value is often written as:

```properties
client.connect-timeout=5s
```

In Java, this value fits:

```java
java.time.Duration
```

Similarly:

```properties
upload.max-size=10MB
```

can bind to:

```java
org.springframework.util.unit.DataSize
```

To observe the available conversions, you can practice with a standalone Java example outside an application context:

```java
import java.time.Duration;

import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.core.convert.ConversionService;
import org.springframework.util.unit.DataSize;

public class ConversionDemo {

    public static void main(String[] args) {
        ConversionService conversions =
                new ApplicationConversionService();

        Integer count = conversions.convert("12", Integer.class);
        Boolean enabled = conversions.convert("true", Boolean.class);
        Duration timeout = conversions.convert("5s", Duration.class);
        DataSize payload = conversions.convert("4MB", DataSize.class);

        System.out.println("count = " + count);
        System.out.println("enabled = " + enabled);
        System.out.println("timeout = " + timeout);
        System.out.println("payload bytes = " + payload.toBytes());
    }
}
```

The example above shows **type conversion independent** of having an `application.yml` file. A `ConversionService` can be called directly to perform conversions, while the binder is the component that uses that capability during configuration binding.

Do not conclude that every newly constructed `ConversionService` in code has the same converters as the service used by the application's binder. That depends on how you create and configure the conversion object.

## 5. Complete Example with @ConfigurationProperties

### 5.1. Input Configuration

File `src/main/resources/application.yml`:

```yaml
upload:
  endpoint: "https://upload.example.invalid"
  timeout: 7s
  max-file-size: 16MB
  max-connections: 20
  enabled: true
```

### 5.2. Configuration Record with Real Data Types

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "upload")
public record UploadProperties(
        URI endpoint,
        Duration timeout,
        DataSize maxFileSize,
        int maxConnections,
        boolean enabled) {
}
```

When binding, Spring Boot needs to handle the corresponding values:

| Key | Input Form | Target |
| --- | --- | --- |
| `upload.endpoint` | String URL | `URI` |
| `upload.timeout` | `7s` | `Duration` |
| `upload.max-file-size` | `16MB` | `DataSize` |
| `upload.max-connections` | `20` | `int` |
| `upload.enabled` | `true` | `boolean` |

There is no need to manually call `Integer.parseInt`, `Duration.parse`, or strip the `MB` suffix in business classes.

### 5.3. Registering the Configuration Record

Application class:

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

`@ConfigurationPropertiesScan` helps Spring Boot find and register configuration classes annotated with `@ConfigurationProperties` in the appropriate packages.

You can use `@EnableConfigurationProperties(UploadProperties.class)` if you want explicit registration instead of scanning.

### 5.4. Using the Converted Data

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class UploadConfigPrinter implements ApplicationRunner {

    private final UploadProperties properties;

    public UploadConfigPrinter(UploadProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("URI: " + properties.endpoint());
        System.out.println("Timeout ms: "
                + properties.timeout().toMillis());
        System.out.println("Max bytes: "
                + properties.maxFileSize().toBytes());
        System.out.println("Connections: "
                + properties.maxConnections());
        System.out.println("Enabled: "
                + properties.enabled());
    }
}
```

With the sample data, the program can print:

```text
URI: https://upload.example.invalid
Timeout ms: 7000
Max bytes: 16777216
Connections: 20
Enabled: true
```

Here `DataSize` uses binary-based units for the `MB` suffix according to Spring Boot's conversion, so `16MB` corresponds to `16 × 1024 × 1024` bytes in the example.

The initial values can come from YAML, Properties files, environment variables, or another source; business beans still read a typed Java object.

## 6. Duration: Configuration Strings and Time Units

`Duration` is a very common type: timeouts, check intervals, retry delays, TTLs.

Spring Boot supports convenient notations:

```properties
client.read-timeout=500ms
client.retry-delay=2s
client.cache-ttl=15m
client.session-ttl=1h
```

These values can bind to different `Duration` members.

For example:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public record ClientTimingProperties(
        Duration readTimeout,
        Duration retryDelay,
        Duration cacheTtl,
        Duration sessionTtl) {
}
```

Common units you may encounter:

| Suffix | Meaning |
| --- | --- |
| `ns` | Nanosecond |
| `us` | Microsecond |
| `ms` | Millisecond |
| `s` | Second |
| `m` | Minute |
| `h` | Hour |
| `d` | Day |

Spring Boot can also interpret strings in ISO-8601 duration format, for example:

```properties
client.read-timeout=PT3S
```

The string `PT3S` represents three seconds in Java's duration syntax.

**Do not confuse** the convenient `3s` syntax with the syntax of `Duration.parse("3s")` itself. Java's `Duration.parse` targets ISO-8601 format, whereas Spring Boot's converter adds support for configuration-friendly formats.

### 6.1. Numbers Without a Unit

Suppose the configuration is:

```properties
client.read-timeout=2000
```

For `Duration`, Spring Boot interprets an integer without a unit as **milliseconds** by default, unless another annotation or conversion mechanism specifies a unit. Thus, the expected result is two seconds.

However, this style of configuration is easy to misread. Readers might wonder whether `2000` means seconds, milliseconds, or microseconds.

**Recommendation:** write the unit explicitly at the source, such as `2000ms` or `2s`.

### 6.2. Changing the Default Unit with @DurationUnit

You can specify the unit for values without a suffix:

```java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "client")
public record ClientTimingProperties(
        @DurationUnit(ChronoUnit.SECONDS) Duration readTimeout) {
}
```

With:

```properties
client.read-timeout=5
```

the value is interpreted as five seconds according to the annotation.

If the source explicitly specifies `500ms`, the unit-bearing form is used to represent the corresponding value. The annotation mainly determines how numbers **without a unit** are interpreted.

In new projects, writing the unit in YAML is usually the more readable choice; `@DurationUnit` is useful when compatibility with an existing input convention is needed.

## 7. DataSize: Converting Capacity Configuration into Objects

Settings for upload limits, buffers, or data sizes should use `DataSize` instead of keeping raw strings.

For example:

```yaml
storage:
  max-file-size: 50MB
  chunk-size: 512KB
```

Record:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "storage")
public record StorageProperties(
        DataSize maxFileSize,
        DataSize chunkSize) {
}
```

After binding, you can use:

```java
long maxBytes = properties.maxFileSize().toBytes();
long chunkBytes = properties.chunkSize().toBytes();
```

Commonly supported suffixes include `B`, `KB`, `MB`, `GB`, `TB`. The resulting value is an object describing the size, helping avoid accidental multiplication/division mistakes in code.

When a value has no suffix, Boot typically uses **bytes** as the default unit for `DataSize`.

To change the default for values without a suffix, you can use `@DataSizeUnit`:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "storage")
public record StorageProperties(
        @DataSizeUnit(DataUnit.MEGABYTES) DataSize maxFileSize) {
}
```

When using:

```properties
storage.max-file-size=8
```

the value is interpreted in megabytes in this example.

**Right mindset:** configuration and domain models receive a meaningful type, while `ConversionService` handles converting the input format; business code should not repeat unit-suffix parsing.

## 8. Numbers, Booleans, Enums, and URIs

Beyond specialized types, the binder also relies on type conversion for many basic data types.

### 8.1. Integers and Floating-Point Numbers

```yaml
queue:
  batch-size: 128
  backoff-multiplier: 1.5
```

Record:

```java
@ConfigurationProperties(prefix = "queue")
public record QueueProperties(
        int batchSize,
        double backoffMultiplier) {
}
```

If the value is `batch-size: many`, converting it to `int` fails under standard rules. This is a conversion error, not a missing property name error.

### 8.2. Boolean

```yaml
feature:
  enabled: true
```

Java:

```java
@ConfigurationProperties(prefix = "feature")
public record FeatureProperties(boolean enabled) {
}
```

Use `boolean` when the feature truly always has an on/off state. If you need to distinguish "not configured" from `false`, consider `Boolean` along with validation or an explicit default value.

### 8.3. Enum

Suppose an application supports these modes:

```java
public enum DeliveryMode {
    IMMEDIATE,
    SCHEDULED,
    DISABLED
}
```

Configuration:

```yaml
delivery:
  mode: scheduled
```

Record:

```java
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(DeliveryMode mode) {
}
```

Spring Boot provides converters that support mapping familiar configuration styles to enums, including convenient handling of name casing in many situations.

If the mode name is completely invalid, such as `mode: teleport`, there is no matching `TELEPORT` enum constant; binding can fail rather than guessing a close match.

For business-critical choices, enums let the compiler and validation clarify the valid set of options.

### 8.4. URI

```yaml
delivery:
  endpoint: "https://delivery.example.invalid"
```

Record:

```java
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(java.net.URI endpoint) {
}
```

Choose `URI` instead of `String` to express the proper meaning. However, **having the `URI` type does not mean the endpoint has been validated for business rules**: the application may still need to require an HTTPS scheme, an allowlisted host, or a non-null endpoint. That is the job of separate validation/checks.

## 9. Type Conversion for List, Set, and Map

When a property is a list or a map, the binder is also responsible for binding the structure, indices, and keys.

For example:

```yaml
worker:
  retry-delays:
    - 1s
    - 3s
    - 10s
  shard-ids:
    - 1
    - 2
    - 7
  labels:
    team: "orders"
    tier: "backend"
```

Record:

```java
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        List<Duration> retryDelays,
        List<Integer> shardIds,
        Map<String, String> labels) {
}
```

After binding:

```java
Duration firstDelay = properties.retryDelays().get(0);
Integer firstShard = properties.shardIds().get(0);
String team = properties.labels().get("team");
```

Spring Boot can convert each list element to `Duration` or `Integer`. Still, **`ConversionService` is not the entire structural binding mechanism**: the binder coordinates recognizing configuration branches and indices with type conversion of the elements.

For maps, key names can be dynamic data, while map value types can still require conversion.

If an element has a wrong-type value, such as `retry-delays: [1s, invalid-duration]`, binding can fail because one element cannot be converted.

### 9.1. Note on Mutable Collections

A record containing `List<Duration>` does not automatically guarantee deep immutability of the underlying list. If you want to restrict modification after construction, you can make a defensive copy:

```java
public record WorkerProperties(List<Duration> retryDelays) {

    public WorkerProperties {
        retryDelays = retryDelays == null
                ? List.of()
                : List.copyOf(retryDelays);
    }
}
```

This is a Java object design decision, not a new converter.

## 10. Limitations: Converters Cannot Fix Every Kind of Configuration Error

When configuration fails to bind, you need to identify which stage the error belongs to.

| Issue | Example | Related Mechanism |
| --- | --- | --- |
| Wrong key name | `retry-coutn` instead of `retry-count` | Key lookup/relaxed binding, strict unknown field |
| Source not loaded | Profile file not activated | Config Data, profiles |
| Another source overrides | CLI overrides YAML | `PropertySource` precedence |
| Wrong value type | `max-attempts=many` for `int` | `ConversionService`/binding |
| Constraint violation | `max-attempts=-4` | Validation or constructor check |
| Ambiguous unit | `timeout=3` | Conversion rules/unit annotation |
| Target type lacks converter | Custom string to value object | Custom `Converter` |
| Bean not registered | Annotated but not scanned/enabled | Configuration bean registration |

**`ConversionService` handles representation and type issues**, not business validity of every requirement. For example, the string `"-10"` can be converted to `int -10` completely validly at the type level, even though the application does not allow a negative retry count.

If a value has the right type but violates a rule, add Bean Validation or constructor checks.

## 11. How to Add a Converter<S,T> for a Custom Type

Sometimes an application uses a domain type that has no default converter.

Suppose configuration wants to accept region codes following the convention `VN-SG`, `VN-HN`, or similar. In YAML, operators prefer writing them simply:

```yaml
routing:
  region: "vn-sg"
  timeout: 2s
```

In Java, we want a `RegionCode` **value object** to avoid passing arbitrary strings throughout the system.

### 11.1. Creating the Value Object

```java
package com.example.configdemo;

public record RegionCode(String value) {

    public RegionCode {
        if (value == null || !value.matches("[A-Z]{2}-[A-Z]{2}")) {
            throw new IllegalArgumentException(
                    "Region code must follow the XX-YY format");
        }
    }
}
```

The object enforces a construction rule: the code must contain two letters, a hyphen, and two letters. To support real-world region codes, you can define a more appropriate contract.

### 11.2. Creating Converter<String,RegionCode>

```java
package com.example.configdemo;

import java.util.Locale;

import org.springframework.core.convert.converter.Converter;

public final class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

Responsibilities of the converter:

1. Receive a `String` from the source.
2. Normalize leading/trailing whitespace.
3. Convert letters to uppercase using a stable locale.
4. Construct `RegionCode`, letting the value object validate itself.

**Do not silently replace an invalid region code with a default code** inside the converter. If the input is `unknown`, let `RegionCode` construction fail with helpful information to avoid silent misrouting.

### 11.3. Registering a Custom Converter for ConfigurationProperties

Spring Boot supports the `@ConfigurationPropertiesBinding` annotation to identify converters intended for `@ConfigurationProperties` binding.

You can write:

```java
package com.example.configdemo;

import java.util.Locale;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public final class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

This is the **Spring-bean-registered** version of the converter. When the class is within component-scan scope, Spring Boot can use the annotated converter for `@ConfigurationProperties`.

This approach prevents specialized configuration conversions from being confused with other application converters, such as converters for Spring MVC HTTP parameter binding.

If you prefer `@Bean` registration, you can also create the converter in a `@Configuration` class and annotate the bean with `@ConfigurationPropertiesBinding`. For converters created very early during startup, it is generally best to keep converter dependencies minimal.

### 11.4. Using It in a Configuration Record

```java
package com.example.configdemo;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        RegionCode region,
        Duration timeout) {
}
```

Once `RoutingProperties` is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, the binder can use the converter you wrote to create the `region` component:

```text
routing.region = "vn-sg"
           |
           v
StringToRegionCodeConverter
           |
           v
new RegionCode("VN-SG")
           |
           v
RoutingProperties.region()
```

Business classes simply use:

```java
RegionCode region = properties.region();
String canonicalCode = region.value();
```

They no longer have to call `trim()` and `toUpperCase()` repeatedly in many places.

## 12. Avoiding Confusion Between @ConfigurationPropertiesBinding and Component Scanning

The two annotations:

```java
@Component
@ConfigurationPropertiesBinding
```

have different responsibilities.

- `@Component` makes the class a Spring bean candidate when component scanning is configured and scans the appropriate package.
- `@ConfigurationPropertiesBinding` marks the converter as intended for the configuration binding mechanism.

If you merely instantiate an object with:

```java
new StringToRegionCodeConverter()
```

in normal application code without registering it in the conversion system used by the binder, that converter **does not automatically become a `ConfigurationProperties` converter**.

Similarly, if the converter class is not discovered by component scanning, having the annotation in source code alone does not prove the converter is present in the `ApplicationContext`.

Another explicit way to register it:

```java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class RoutingConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static Converter<String, RegionCode> regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
```

Note that this example is an **alternative registration approach** to `@Component` in the previous section. In a single application, there is no need to register two identical converter beans simultaneously without a reason.

Using `static @Bean` where appropriate helps register the bean without instantiating the `@Configuration` class containing the factory method too early.

## 13. Testing a Converter in Isolation

A converter should have small, clear logic so it is easy to test.

JUnit 5 example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class StringToRegionCodeConverterTest {

    private final StringToRegionCodeConverter converter =
            new StringToRegionCodeConverter();

    @Test
    void normalizesValidRegionCode() {
        RegionCode result = converter.convert(" vn-sg ");

        assertEquals("VN-SG", result.value());
    }

    @Test
    void rejectsInvalidRegionCode() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("invalid"));
    }
}
```

This unit test verifies **the string-to-value-object conversion logic**, not whether Spring Boot actually discovers the converter.

That is why you must distinguish two testing layers:

1. **Converter unit tests**: verify the conversion logic and invalid-input errors.
2. **Binding tests**: verify the converter is registered and the binder actually uses it with `@ConfigurationProperties`.

A correct converter that is not registered still does not solve the application's need.

## 14. Testing Binding with ApplicationContextRunner

Spring Boot Test provides `ApplicationContextRunner` to launch a lightweight `ApplicationContext` with test properties.

Suppose we have:

```java
public record RegionCode(String value) {
    public RegionCode {
        if (value == null || !value.matches("[A-Z]{2}-[A-Z]{2}")) {
            throw new IllegalArgumentException("Invalid region");
        }
    }
}
```

And:

```java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(RegionCode region) {
}
```

Write a test that explicitly registers the converter and configuration bean:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

class RoutingPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void convertsRegionCodeDuringBinding() {
        runner.withPropertyValues("routing.region=vn-sg")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    RoutingProperties properties =
                            context.getBean(RoutingProperties.class);

                    assertThat(properties.region().value())
                            .isEqualTo("VN-SG");
                });
    }

    @Test
    void failsWhenRegionCodeIsInvalid() {
        runner.withPropertyValues("routing.region=broken")
                .run(context -> assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(RoutingProperties.class)
    static class TestConfiguration {

        @Bean
        @ConfigurationPropertiesBinding
        static Converter<String, RegionCode> regionCodeConverter() {
            return value -> new RegionCode(
                    value.trim().toUpperCase(Locale.ROOT));
        }
    }
}
```

Expected results:

- With `routing.region=vn-sg`, the context creates the bean and the value is `VN-SG`.
- With `routing.region=broken`, the converter/value object reports invalid data, causing configuration bean binding to fail.
- No web server needs to start in order to test type conversion.

This is a way to catch configuration issues early without running the entire application and observing errors in a deployment environment.

## 15. How Do Converter, ConverterFactory, and GenericConverter Differ?

For most custom configuration needs in a project, `Converter<String, T>` is sufficient. However, Spring provides extension interfaces for other scenarios.

### 15.1. Converter<S,T>

Suitable when the type pair is known clearly.

```java
public class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String value) {
        return new RegionCode(value.toUpperCase(Locale.ROOT));
    }
}
```

A converter with a narrow responsibility is usually easy to test and maintain.

### 15.2. ConverterFactory<S,R>

Used when one converter factory serves **multiple related target types** rather than a single class. Conceptual example: a factory supporting conversion from strings to different enum types.

You do not need to build a `ConverterFactory` just to convert `"vn-sg"` to `RegionCode`. Picking a more complex interface does not automatically make the conversion more accurate.

### 15.3. GenericConverter

Useful when a conversion needs generic type information or cannot be expressed as a simple `Converter<S,T>` pair.

For example, collection conversion infrastructure may need to inspect the target element type, not just the `List` type itself.

### 15.4. ConditionalGenericConverter

Can decide whether conversion is supported in a particular context based on source/target type metadata.

For typical Externalized Configuration needs, only use these advanced interfaces when there is a genuine requirement such as multiple target types, generic types, or metadata-dependent support conditions.

## 16. Should You Create a Bean Named conversionService?

Spring Boot allows customizing how conversion is used in an application. One option is providing a `ConversionService` registered under the special bean name `conversionService` according to Boot's supported mechanism.

However, this is a broader decision than adding a converter for a specific configuration group.

**Important point:** configuration binding runs **very early** when the `ApplicationContext` initializes. If a custom `conversionService` bean depends on many other application beans, there is a risk of initializing those beans prematurely.

For example, an incautious approach:

```java
@Bean(name = "conversionService")
ConversionService conversionService(MyBusinessService service) {
    // Do not force the configuration conversion system
    // to depend on a late-initialized business service.
}
```

Configuration converters should be **lightweight, independent, and have minimal dependencies**, especially when needed during early startup.

In many applications, you do not need to replace the entire `ConversionService`. Prefer registering a dedicated converter with `@ConfigurationPropertiesBinding` when you only need to support a specific domain type for `@ConfigurationProperties`.

If you must create a general-purpose `ConversionService`, understand clearly which default converters must be retained, how it integrates with Spring Boot, and the blast radius of the new bean. Do not replace the standard service with an empty one and accidentally lose useful conversions such as `Duration` or `DataSize`.

## 17. Distinguishing ConfigurationProperties Conversion from Conversion at Other Layers

A Spring Boot application can have many situations requiring data conversion:

1. Binding configuration from `Environment` into `@ConfigurationProperties`.
2. Converting URL or form parameters when handling Spring MVC requests.
3. Converting data in an application using Spring Data.
4. Converting expression values or property placeholders at injection points.
5. Converting data invoked directly by business code through a specific `ConversionService`.

Do not assume that a converter registered in the **Spring MVC formatting registry** will automatically be used as a converter by the configuration-properties binder.

Likewise, a converter annotated with `@ConfigurationPropertiesBinding` is declared for **configuration binding**, and does not necessarily become the rule for every type of HTTP request input.

If a conversion rule needs to be shared across multiple layers, intentionally design appropriate registrations at those layers instead of relying on implicit behavior.

## 18. Do @Value and @ConfigurationProperties Handle Type Conversion the Same Way?

Both can supply typed values to Java, but their usage is not identical.

**`@Value` for a single value:**

```java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PollingService {

    private final Duration interval;

    public PollingService(
            @Value("${polling.interval:3s}") Duration interval) {
        this.interval = interval;
    }
}
```

**`@ConfigurationProperties` for a group of values:**

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "polling")
public record PollingProperties(
        Duration interval,
        int batchSize,
        boolean enabled) {
}
```

Both mechanisms can use Spring's type conversion infrastructure, but **do not assume every converter annotated with `@ConfigurationPropertiesBinding` automatically behaves identically in `@Value`**. `@Value` injection points are processed by Spring's placeholder/dependency-injection mechanism, whereas `@ConfigurationProperties` uses the binder with many specialized features.

When you need a typed group of settings—especially nested configuration, lists, defaults, and validation—`@ConfigurationProperties` is usually a better fit.

For a standalone value, `@Value` remains convenient and not every case requires creating a new configuration record.

## 19. Conversion Is Not Validation

A string can convert to a Java type successfully yet **still be invalid from a business perspective**.

For example:

```yaml
job:
  max-attempts: -3
  timeout: -5s
```

The converter can produce:

```java
int maxAttempts = -3;
Duration timeout = Duration.ofSeconds(-5);
```

These are valid values when considered solely at the **data type** level. However, the application might require at least 1 attempt and a positive timeout.

To check constraints:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "job")
public record JobProperties(
        @Min(1) int maxAttempts,
        @NotNull Duration timeout) {

    public JobProperties {
        if (timeout != null && !timeout.isPositive()) {
            throw new IllegalArgumentException(
                    "job.timeout must be a positive duration");
        }
    }
}
```

Note: the snippet above illustrates constructor checks combined with Bean Validation; `@NotNull` alone does not guarantee that a `Duration` is greater than 0.

To use Jakarta Bean Validation with Spring Boot, a project typically needs the `spring-boot-starter-validation` dependency.

The distinction:

| Stage | Question |
| --- | --- |
| Source selection | Where is the value taken from? |
| Name binding | Which field/parameter does the configuration key map to? |
| Type conversion | Can `Duration`, `int`, `URI`, etc. be created? |
| Validation | Does the Java value satisfy required/business rules? |
| Bean creation | Is the object qualified for the application to use? |

Making a converter silently "fix" bad data is not always a good choice. Important configuration errors should surface clearly.

## 20. Defaults Do Not Replace Type Conversion

Spring Boot supports `@DefaultValue` for constructor binding, for example:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "task")
public record TaskProperties(
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("3") int maxAttempts) {
}
```

If the property is absent from the sources inspected by the binder, the string default value is **converted to the target type**.

For example:

```yaml
task:
  max-attempts: 8
```

Then:

```text
timeout     = Duration.ofSeconds(5)
maxAttempts = 8
```

If the source contains:

```yaml
task:
  timeout: nonsense
```

do not expect the `5s` default to automatically replace any unconvertible value. The property is present but malformed; binding can fail. Ignoring conversion errors and falling back to a substitute value should only happen when intentionally designed and explicitly tested.

## 21. ConversionService with Profile-Specific Configuration and Source Precedence

Suppose:

```yaml
# application.yml
client:
  timeout: 5s
```

```yaml
# application-prod.yml
client:
  timeout: 2s
```

And:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(java.time.Duration timeout) {
}
```

When the `prod` profile is active, the profile-specific configuration source can supply `2s` according to Config Data rules.

If you run:

```bash
java -jar app.jar --spring.profiles.active=prod --client.timeout=900ms
```

command-line arguments provide a value with higher precedence than Config Data files in a standard Spring Boot setup, so the binder can receive `900ms`.

**`ConversionService` is used to convert `"900ms"` into `Duration`**, but **it does not decide that CLI wins over YAML**.

A fuller model:

```text
PropertySource priority
      |
      v
"900ms" is the effective value
      |
      v
Binder receives client.timeout
      |
      v
ConversionService converts "900ms" -> Duration
      |
      v
ClientProperties(timeout=PT0.9S)
```

Understanding this boundary helps with troubleshooting: if the type is right but the value is unexpected, you usually need to check **configuration sources** before changing converters.

## 22. Common Exceptions When Conversion Fails

During binding, Spring Boot and Spring Framework can report errors related to type conversion. Depending on the failure path, you may see exception classes such as:

- `ConversionFailedException` in the conversion system;
- `ConverterNotFoundException` when no suitable conversion exists;
- `BindException` from the binder;
- `ConfigurationPropertiesBindException` when configuration bean creation fails.

These names describe different layers of failure; not every scenario throws the exact same exception class or message.

For example:

```properties
client.connect-timeout=abc
```

The bean requires:

```java
Duration connectTimeout
```

However, `abc` is not a valid duration representation for the converter in use. The result can be a binding failure at startup.

When reading logs, look for:

1. **The property name** being bound.
2. **The value** or source causing the error.
3. **The target type** the binder needs to create.
4. **The root cause** in the exception chain.
5. Information about the Config Data source, if provided in the log.

Avoid relying on a fixed log string in tests because it can vary across Spring Boot versions.

## 23. Common Pitfall: Confusing "5s" with Duration.parse

In standard Java:

```java
Duration.parse("PT5S");
```

is a valid parse, whereas:

```java
Duration.parse("5s");
```

does not use the same syntax and can throw an exception.

Spring Boot, on the other hand, supports a convenient duration format:

```properties
client.timeout=5s
```

and binds it to:

```java
Duration timeout
```

This does not mean every Java API accepts the `s` suffix. If you write your own converter, do not unintentionally mix expectations about `Duration.parse` syntax and Spring Boot's friendly syntax.

When standard duration configuration is needed, using `Duration` with the default binder is clearer than having each service parse strings manually.

## 24. Common Pitfall: Converter Created but Not Used by the Binder

Consider a converter:

```java
public class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(source);
    }
}
```

Merely having this Java file in the project does not guarantee Spring has registered it.

Check:

- Is the class registered as a bean?
- Is the converter annotated with `@ConfigurationPropertiesBinding` if used for the binder?
- Is it within component-scan scope?
- Is the `@ConfigurationProperties` bean that needs the converter registered?
- Is the target type name in the configuration class actually `RegionCode`?
- Does the data source actually supply a string value the converter can handle?

Sometimes developers register a converter for Spring MVC and use it successfully with request parameters, only to find `@ConfigurationProperties` does not use that converter. This can happen because the layers use different conversion systems/registries.

**Registering in the right place matters just as much as writing the `convert` method correctly.**

## 25. Common Pitfall: Missing Key or Wrong Prefix

For example, the bean:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(Duration timeout) {
}
```

while YAML has:

```yaml
clients:
  timeout: 5s
```

The actual key is `clients.timeout`, whereas the bean looks for `client.timeout`.

Even though `ApplicationConversionService` supports converting `"5s"` to `Duration`, the binder cannot automatically use a converter to turn `client` into `clients`.

This is a **key-matching** error, not a type conversion error.

How to diagnose:

1. Check the bean's `prefix`.
2. Check the canonical name in YAML or Properties.
3. Check that the configuration bean is registered.
4. Check whether the file is loaded under the active profile.
5. Only if the value reaches the binder but is malformed should you focus on conversion.

You can combine `@Validated`, required annotations, and `ignoreUnknownFields = false` to catch more configuration mistakes, though each mechanism has its own scope.

## 26. Common Pitfall: conversionService Bean Has Too-Early Dependencies

In many applications, `@ConfigurationProperties` is used right as Spring Boot creates infrastructure components.

If you create a custom `conversionService` whose constructor depends on business beans that need other configurations, you can create a circular dependency or confusing early initialization.

Example of a design to avoid:

```text
conversionService bean
      -> NotificationService
             -> NotificationProperties
                    -> needs ConversionService to bind
```

Remediation:

- Keep converters **stateless** whenever possible.
- Do not make network or database calls inside a converter just to parse a configuration string.
- Do not make conversion depend on a service whose own creation requires configuration properties.
- Consider `@ConfigurationPropertiesBinding` for narrow-scoped converters.
- If a global custom `ConversionService` is required, design and test initialization order carefully.

Type conversion for configuration should be able to run right as the application starts, without depending on the entire business infrastructure already being ready.

## 27. Common Pitfall: Using a Converter to Mask Misconfiguration

Suppose the configuration value is:

```properties
delivery.mode=immedaite
```

The operator meant `immediate` but made a typo. A dangerous converter might do:

```java
return DeliveryMode.IMMEDIATE;
```

for **any** unrecognized string.

The application still starts, but the person configuring it has no idea a mistake was made. Depending on the goal, this is unsafe behavior because it creates implicit configuration.

A better design:

```java
@Override
public DeliveryMode convert(String value) {
    String normalized = value.trim().toUpperCase(Locale.ROOT);
    try {
        return DeliveryMode.valueOf(normalized);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Invalid delivery.mode: " + value, ex);
    }
}
```

This snippet is only an example of a converter for an application-defined enum. Spring Boot already has standard enum conversion; there is no need to reimplement it unless there is custom syntax.

For invalid input, failing early is generally more reliable than guessing.

## 28. Solution Selection Table

| Need | Appropriate Solution |
| --- | --- |
| Bind `int`, `boolean`, `URI` | Spring Boot default converters |
| Bind `Duration` or `DataSize` | Built-in Boot converters |
| Specify unit for suffixless numbers | `@DurationUnit`, `@DataSizeUnit`, or explicit units |
| Bind enum names | Default enum conversion system |
| Bind custom domain type from string | `Converter<String,T>` + `@ConfigurationPropertiesBinding` |
| Bind multiple related fields | `@ConfigurationProperties` instead of manual parsing |
| Catch negative values or invalid bounds | Bean Validation or constructor checks |
| Catch misspelled key names | Check prefix, metadata, strict binding, and tests |
| Choose value across CLI, env vars, YAML | `PropertySource`/Config Data precedence mechanism |
| Need configuration updated at runtime | Design a separate refresh/rebind mechanism; `ConversionService` does not do this |

The table above emphasizes **choosing the right processing layer**. Many errors appear as "wrong configuration value" while the real root cause belongs to another layer.

## 29. Exercise A: Predict Values After Conversion

Given the file:

```yaml
batch:
  size: 64
  interval: 250ms
  payload-limit: 1MB
  enabled: false
```

And the record:

```java
@ConfigurationProperties(prefix = "batch")
public record BatchProperties(
        int size,
        Duration interval,
        DataSize payloadLimit,
        boolean enabled) {
}
```

Predict the values:

| Java Expression | Result |
| --- | --- |
| `properties.size()` | `64` |
| `properties.interval().toMillis()` | `250` |
| `properties.payloadLimit().toBytes()` | `1048576` |
| `properties.enabled()` | `false` |

Explanation: the binder looks up the corresponding names, while the conversion system produces properly typed values.

## 30. Exercise B: Conversion Error or Key Error?

Given the bean:

```java
@ConfigurationProperties(prefix = "pool")
public record PoolProperties(
        int maxConnections,
        Duration acquireTimeout) {
}
```

Consider three scenarios:

**Case 1**

```yaml
pool:
  max-connections: many
  acquire-timeout: 2s
```

**Case 2**

```yaml
pool:
  max-conections: 8
  acquire-timeout: 2s
```

**Case 3**

```yaml
pools:
  max-connections: 8
  acquire-timeout: 2s
```

Answers:

1. The name `max-connections` is correct, but `many` cannot be converted to `int` → conversion/binding error.
2. `max-conections` is misspelled → the binder may fail to bind `maxConnections`, which cannot be fixed merely by adding a converter.
3. Wrong prefix `pools` instead of `pool` → the binder may not see the entire configuration group; you must fix the source or the configured prefix.

A tool with many converters does not mean it can fix key names.

## 31. Exercise C: Write a Converter for a Custom Value Type

Suppose an application needs a channel code consisting of exactly three letters and wants to accept lowercase configuration.

Value object:

```java
public record ChannelCode(String value) {

    public ChannelCode {
        if (value == null || !value.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid channel code");
        }
    }
}
```

Write the converter:

```java
import java.util.Locale;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public class StringToChannelCodeConverter
        implements Converter<String, ChannelCode> {

    @Override
    public ChannelCode convert(String value) {
        return new ChannelCode(
                value.trim().toUpperCase(Locale.ROOT));
    }
}
```

With `channel.code=web`, the expected result is `ChannelCode("WEB")`. If configured as `channel.code=mobile` (six letters), the constructor rejects the value.

## 32. Exercise D: Why Is a Custom Converter Alone Not Enough?

Suppose you wrote:

```java
class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {
    // ...
}
```

But you neither registered a bean nor added the converter to a registry.

**Question:** will the binder necessarily know about this conversion?

**Answer:** no. A class merely existing in code is not automatically discovered by Spring Boot as a configuration converter. It must be registered via a supported mechanism, such as a `@ConfigurationPropertiesBinding` bean.

## 33. Exercise E: Timeout Without a Unit

File:

```properties
client.timeout=7
```

Record:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(Duration timeout) {
}
```

**Question:** without another unit or annotation, how does Spring Boot typically interpret `7`?

**Answer:** as **7 milliseconds**, following the default unit of `Duration` in standard binding.

If 7 seconds is required, change it to:

```properties
client.timeout=7s
```

or declare the appropriate unit with `@DurationUnit` on the corresponding parameter.

## 34. Exercise F: At Which Layer Is the Failure Checked?

Given:

```yaml
task:
  timeout: -3s
  max-attempts: -2
```

And the record:

```java
@ConfigurationProperties(prefix = "task")
public record TaskProperties(
        Duration timeout,
        int maxAttempts) {
}
```

These values can convert to `Duration` and `int` respectively, but are they valid for a real task?

**Answer:** not necessarily. If the timeout must be positive and max attempts at least one, **validation or constructor checks** are required. Successful type conversion does not guarantee business-valid input.

## 35. Diagnostic Workflow When Binding Fails

When Spring Boot reports a configuration binding error, you can proceed sequentially:

1. **Identify the bean and prefix** being bound. If the prefix is wrong, no converter can help locate the data.
2. **Identify the effective source:** profile file, imported file, environment variable, Java system property, or command-line argument.
3. **Check the canonical key:** is it spelled correctly and understood by relaxed binding as intended?
4. **Inspect the value format:** number, Boolean, time unit, data unit, enum, URI, or a custom domain code?
5. **Inspect the target Java type:** is there a default converter supporting it? If a custom converter is needed, is it registered for the binder?
6. **Check business constraints:** the type converted, but does the value pass validation?
7. **Write a small test:** use `ApplicationContextRunner` with valid and invalid values to lock down the expected behavior.
8. **Avoid logging secrets:** print only non-sensitive illustrative keys or necessary metadata, never full passwords/tokens.

These steps help avoid fixing the wrong layer. For example, if the cause is a key named `client.timeoutt`, adding a `Duration` converter will solve nothing.

## 36. Key Takeaways

- `ConversionService` is Spring's type conversion infrastructure; the `@ConfigurationProperties` binder uses its conversion capabilities to produce properly typed Java values.
- Spring Boot's `ApplicationConversionService` provides many useful default conversions, especially for types frequently seen in configuration such as `Duration` and `DataSize`.
- **The binder is responsible for name and structure binding; `ConversionService` is responsible for converting values to the right types.** The two work together and do not replace each other.
- Writing explicit units like `500ms`, `3s`, `2MB` reduces misunderstandings; `@DurationUnit` and `@DataSizeUnit` help set units for suffixless numbers.
- When a domain type lacks a built-in converter, you can write a `Converter<String,T>` and register it with `@ConfigurationPropertiesBinding`.
- Custom converters must be **properly registered with Spring**, and should have minimal dependencies because binding runs early.
- Spring MVC converters, configuration binder converters, and converters invoked by business code do not necessarily belong to the same registry.
- **Type conversion is not validation**: a negative number can convert to `int` while still violating business requirements.
- **`ConversionService` does not fix misspelled keys, select profiles, decide `PropertySource` precedence, or automatically refresh configuration.**
- Testing converters in isolation alongside binding tests with `ApplicationContextRunner` helps catch both value-parsing bugs and converter-registration errors early.