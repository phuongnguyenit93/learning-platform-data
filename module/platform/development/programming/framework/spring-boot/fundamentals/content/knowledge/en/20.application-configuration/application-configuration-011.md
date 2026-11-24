# Converting Duration, DataSize, Collections, and Nested Configuration

In Spring Boot applications, configuration is commonly written in `application.yml`, `application.properties`, environment variables, or command-line arguments. Java code should not have to split strings like `"5s"`, `"32MB"`, or parse individual elements of a configuration list manually. Spring Boot provides **type-safe configuration binding** to convert values from those configuration sources into strongly typed Java objects.

With `@ConfigurationProperties`, you can define a group of properties under a prefix and let Spring Boot convert:

- `Duration`: durations such as `500ms`, `5s`, `2m`, or ISO-8601 format such as `PT30S`.
- `DataSize`: sizes such as `512KB`, `32MB`, or `1GB`.
- Collections: `List<String>`, `Set<String>`, `List<Duration>`, `Map<String, DataSize>`, and other typed structures.
- Nested configuration: objects, records, lists of objects, and maps with object values.
- Defaults and validation so the application catches missing or invalid configuration at startup.

This lesson targets **Spring Boot 3.3, Java 21**, focusing on conversion rules, configuration organization, subtle differences between collections and maps, testing, and common mistakes.

## 1. From configuration strings to Java objects

Suppose an application has configuration for a data transport client:

~~~yaml
app:
  transport:
    connect-timeout: 5s
    max-in-memory: 4MB
    regions:
      - apac
      - emea
    quotas:
      images: 32MB
      documents: 8MB
    retry:
      max-attempts: 4
      backoff: 750ms
~~~

Values from YAML are loaded into `Environment` as configuration properties. When a class is registered for binding with prefix `app.transport`, Spring Boot uses its binder and conversion service to construct the corresponding Java object.

~~~mermaid
flowchart TD
    A["application.yml / properties"] --> E["Environment / PropertySources"]
    B["Environment variables"] --> E
    C["Command-line arguments"] --> E
    D["Additional config sources"] --> E
    E --> F["ConfigurationProperties Binder"]
    F --> G["Relaxed name matching"]
    G --> H["Convert String → Duration / DataSize"]
    H --> I["Bind List / Map / nested objects"]
    I --> J["Validate configuration"]
    J --> K["TransportProperties bean"]
    K --> L["Inject into Service / Client"]
~~~

There are three distinct responsibilities:

1. **Source loading and precedence**: `Environment` determines the effective value of each property based on property-source precedence.
2. **Binding and conversion**: the Binder matches property names, creates objects, and converts data into declared Java types.
3. **Validation and consumption**: constraints are checked, and services receive the configuration bean as a dependency.

Having properties in YAML does not automatically create a `@ConfigurationProperties` bean. The configuration class must be registered using an appropriate mechanism such as `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

## 2. Why use @ConfigurationProperties?

You can read a value via `Environment.getProperty(...)` or `@Value`. However, when multiple properties belong to the same component, a centralized configuration class keeps code much cleaner.

For example, a service accepting many loose values becomes hard to read:

~~~java
@Service
public class TransportClient {
    private final Duration connectTimeout;
    private final DataSize maxInMemory;

    public TransportClient(
            Duration connectTimeout,
            DataSize maxInMemory) {
        this.connectTimeout = connectTimeout;
        this.maxInMemory = maxInMemory;
    }
}
~~~

Those parameters do not show the configuration source, property names, or default semantics. Passing them through multiple `@Bean` methods increases parameter bloat further.

A cleaner solution groups the values into:

~~~java
@ConfigurationProperties(prefix = "app.transport")
public record TransportProperties(
        Duration connectTimeout,
        DataSize maxInMemory
) {
}
~~~

Once the bean is registered and bound, the consumer only needs:

~~~java
@Service
public class TransportClient {
    private final TransportProperties properties;

    public TransportClient(TransportProperties properties) {
        this.properties = properties;
    }
}
~~~

Here, `TransportProperties` is a strongly typed configuration model. Unlike a free-form configuration map, the Java compiler, IDE, and validation can verify how fields are used.

## 3. Duration: representing time spans

`Duration` belongs to the Java Time API:

~~~java
import java.time.Duration;
~~~

It represents an amount of time, such as a connection timeout, retry delay, cache TTL, or operation timeout.

Plain Java examples:

~~~java
Duration shortWait = Duration.ofMillis(500);
Duration connectTimeout = Duration.ofSeconds(5);
Duration retryDelay = Duration.ofMinutes(2);
Duration oneHour = Duration.ofHours(1);
~~~

In Spring Boot configuration, you do not need to call those factory methods manually. The Binder converts text values into `Duration`.

### 3.1. Ways to write Duration

| Configuration value | Meaning | Equivalent Java value |
| --- | --- | --- |
| `500ms` | 500 milliseconds | `Duration.ofMillis(500)` |
| `5s` | 5 seconds | `Duration.ofSeconds(5)` |
| `2m` | 2 minutes | `Duration.ofMinutes(2)` |
| `1h` | 1 hour | `Duration.ofHours(1)` |
| `1d` | 1 day (24 hours) | `Duration.ofDays(1)` |
| `PT30S` | ISO-8601: 30 seconds | `Duration.ofSeconds(30)` |
| `PT1H30M` | ISO-8601: 1 hour 30 minutes | `Duration.ofMinutes(90)` |
| `10` | Defaults to 10 milliseconds | `Duration.ofMillis(10)` |

Spring Boot supports simple unit-suffixed formats and ISO-8601 format. In the short format, common suffixes are `ns`, `us`, `ms`, `s`, `m`, `h`, and `d`. `m` means **minutes**, while `ms` means milliseconds.

A bare number without a suffix can be misleading. If configuration says:

~~~properties
app.transport.connect-timeout=5
~~~

and the target is `Duration`, the default unit is **milliseconds**, not five seconds. Write `5s` or `5000ms` to express intent clearly.

### 3.2. @ConfigurationProperties example with Duration

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.transport")
public record TransportProperties(
        Duration connectTimeout,
        Duration readTimeout
) {
}
~~~

Configuration:

~~~yaml
app:
  transport:
    connect-timeout: 5s
    read-timeout: PT30S
~~~

Once bound successfully:

~~~java
properties.connectTimeout().equals(Duration.ofSeconds(5));   // true
properties.readTimeout().equals(Duration.ofSeconds(30));      // true
~~~

This compares `Duration` values rather than the original strings. Both `30s` and `PT30S` produce equal `Duration` objects.

### 3.3. @DurationUnit for unitless values

If existing configuration must use bare integers whose business meaning is seconds, use `@DurationUnit`:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "app.legacy-client")
public record LegacyClientProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration timeout
) {
}
~~~

With:

~~~properties
app.legacy-client.timeout=10
~~~

the value binds as `Duration.ofSeconds(10)` instead of `Duration.ofMillis(10)`.

If the property explicitly states `10ms`, the explicit suffix still indicates milliseconds. The annotation sets the default unit for values lacking a suffix.

Use `@DurationUnit` when supporting legacy numeric formats or an intentional contract. For new configuration, `10s` is usually easier to read.

### 3.4. Binding Duration for a timeout does not enforce it automatically

Binding only creates the value. You still must pass that value to the API performing connections, retries, or caching.

~~~java
public final class RetryPolicy {
    private final Duration delay;

    public RetryPolicy(Duration delay) {
        this.delay = delay;
    }

    public Duration delay() {
        return delay;
    }
}
~~~

If the application binds `delay=250ms` yet never passes `delay` when configuring the client, nothing automatically applies a timeout just because a field has type `Duration`.

### 3.5. Duration and Period are two different concepts

`Duration` represents elapsed time measured in seconds/nanoseconds. `Period` represents calendar-based amounts of time in days, months, and years.

For example:

~~~java
Duration timeout = Duration.ofHours(24);
Period retention = Period.ofMonths(1);
~~~

A calendar month does not always correspond to a fixed number of seconds. For timeouts, delays, technical deadlines, and intervals in time APIs, `Duration` is usually appropriate. For calendar rules like "retain data for one month," consider `Period`.

## 4. DataSize: representing data sizes

`DataSize` is a Spring type:

~~~java
import org.springframework.util.unit.DataSize;
~~~

It represents a byte count, commonly used for buffer sizes, upload limits, cache capacities, or maximum payload sizes.

Java can construct values by unit:

~~~java
DataSize oneKilobyte = DataSize.ofKilobytes(1);
DataSize fourMegabytes = DataSize.ofMegabytes(4);
DataSize oneGigabyte = DataSize.ofGigabytes(1);
~~~

Spring Boot supports binding from unit-suffixed strings.

### 4.1. DataSize values

| Value | Meaning in DataSize | Byte count |
| --- | --- | ---: |
| `512B` | 512 bytes | 512 |
| `1KB` | 1 kilobyte (1024 bytes) | 1,024 |
| `256KB` | 256 × 1024 bytes | 262,144 |
| `4MB` | 4 × 1024² bytes | 4,194,304 |
| `1GB` | 1 × 1024³ bytes | 1,073,741,824 |
| `10` | Defaults to 10 bytes | 10 |

A common point of confusion: `KB`, `MB`, and `GB` in `DataSize` use powers of **1024**, not 1000. This is the convention of Spring's `DataSize` type, even though commercial storage labeling may differ.

Common suffixes include `B`, `KB`, `MB`, `GB`, and `TB`. `MB` stands for megabytes, completely distinct from the `m` suffix meaning minutes in `Duration`.

### 4.2. DataSize example in application.yml

~~~java
import org.springframework.util.unit.DataSize;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        DataSize maxFileSize,
        DataSize memoryThreshold
) {
}
~~~

~~~yaml
app:
  upload:
    max-file-size: 20MB
    memory-threshold: 256KB
~~~

When bound:

~~~java
long maxBytes = properties.maxFileSize().toBytes();
long memoryBytes = properties.memoryThreshold().toBytes();
~~~

In Java, `DataSize` exposes APIs like `toBytes()` to obtain the byte count. If an infrastructure API requires `long` or `int`, convert at the boundary of use and check that API's valid limits.

### 4.3. @DataSizeUnit changes the default unit

If legacy configuration uses an integer meant to represent megabytes by default:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(
        @DataSizeUnit(DataUnit.MEGABYTES)
        DataSize maxSize
) {
}
~~~

With:

~~~properties
app.cache.max-size=64
~~~

the value is interpreted as **64 MB**, rather than 64 bytes. If the config writes `64KB` explicitly, that suffix still determines the unit.

Do not overuse implicit units. A clearer form for operators is:

~~~properties
app.cache.max-size=64MB
~~~

### 4.4. DataSize does not enforce size limits on its own

Creating a class with a `DataSize maxFileSize` field only causes Spring to bind the number. It does not automatically block uploads or cap memory in an arbitrary library. A service or corresponding auto-configuration must read that field and pass it to the enforcing API.

For example, Spring Boot has its own multipart configuration properties; custom properties under `app.upload` do not automatically replace standard properties such as `spring.servlet.multipart.max-file-size`. Know which component owns each property and who consumes it.

## 5. Converting simple values into collections

Systems often need multiple values of the same type, such as allowed regions, retry backoff steps, or enabled feature names.

Configuration class:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        List<String> regions,
        Set<String> enabledChannels,
        List<Duration> retryDelays
) {
}
~~~

YAML:

~~~yaml
app:
  delivery:
    regions:
      - apac
      - emea
    enabled-channels:
      - email
      - sms
    retry-delays:
      - 100ms
      - 500ms
      - 2s
~~~

The Binder can convert each element of `retry-delays` into a `Duration` and build a `List<Duration>`. With `Set<String>`, duplicate entries are not retained as in a list.

### 5.1. Do List and Set differ?

| Type | Use when | Notes |
| --- | --- | --- |
| `List<T>` | Element order is meaningful | Allows duplicate elements |
| `Set<T>` | Unique set of values matters | Do not rely on order as a business contract |
| `Map<K,V>` | Lookup by name or key is needed | Unique keys; values can be complex types |
| `List<RecordType>` | Multiple structured configs are needed | Each element binds into an object |

If retry delays execute sequentially, `List<Duration>` fits better than `Set<Duration>` because order matters. If you only check whether a channel is enabled, `Set<String>` expresses that requirement more accurately.

### 5.2. Collections from .properties files

List elements can be written with indices:

~~~properties
app.delivery.regions[0]=apac
app.delivery.regions[1]=emea

app.delivery.retry-delays[0]=100ms
app.delivery.retry-delays[1]=500ms
app.delivery.retry-delays[2]=2s
~~~

For simple lists, comma-separated values can also be bound:

~~~properties
app.delivery.regions=apac,emea
~~~

Indexed form is clearer when elements have multiple fields or when exact positions matter. With indexed lists, use contiguous indices starting at 0 to avoid sparse gaps and confusing binding errors.

### 5.3. Should collections always be non-null?

If a collection property is omitted, the result depends on binding style and class defaults. Do not assume every `List` or `Map` is always an empty collection.

With immutable records, you can normalize inputs in a compact constructor:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        List<String> regions,
        List<Duration> retryDelays
) {
    public DeliveryProperties {
        regions = regions == null ? List.of() : List.copyOf(regions);
        retryDelays = retryDelays == null
                ? List.of()
                : List.copyOf(retryDelays);
    }
}
~~~

This frees consumers from repeated null checks. `List.copyOf` also creates an unmodifiable copy, fitting an immutable configuration object.

If a collection is required to have at least one item, use validation such as `@NotEmpty` rather than silently turning it into an empty list.

## 6. Map: configuration with keys and values

When each category has its own limit, `Map<String, DataSize>` fits well:

~~~java
@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        Map<String, DataSize> quotas
) {
}
~~~

YAML:

~~~yaml
app:
  upload:
    quotas:
      avatars: 512KB
      images: 32MB
      videos: 1GB
~~~

After binding, a service can look up:

~~~java
DataSize imageQuota = properties.quotas().get("images");
long bytes = imageQuota.toBytes();
~~~

Map values are converted to `DataSize`. If any key has an invalid value like `many-megabytes`, configuration can fail during binding.

### 6.1. Map<String, Duration> and other value types

Spring Boot can also bind:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
        Map<String, Duration> delayByChannel,
        Map<String, Integer> maxAttemptsByChannel
) {
}
~~~

~~~yaml
app:
  retry:
    delay-by-channel:
      email: 2s
      sms: 500ms
    max-attempts-by-channel:
      email: 3
      sms: 5
~~~

There is no need to iterate through `Environment` to parse each key manually. The Binder converts each value to the corresponding target type.

### 6.2. Keys with special characters: bracket notation

Property keys containing dots, slashes, or special characters can be interpreted by the binder as nested property paths. To preserve a key verbatim, use `[key]` notation.

In YAML, wrap bracketed keys in quotes:

~~~yaml
app:
  upload:
    quotas:
      "[/internal/images]": 4MB
      "[tenant.eu]": 8MB
~~~

The resulting map can contain the literal keys `/internal/images` and `tenant.eu`.

In `application.properties`:

~~~properties
app.upload.quotas.[/internal/images]=4MB
app.upload.quotas.[tenant.eu]=8MB
~~~

Brackets are especially important when values are nested objects or when keys contain characters stripped by relaxed binding rules. Do not assume all characters in a key are preserved without brackets.

### 6.3. Using an Enum as key or value

When the set of categories is fixed, you can use an enum:

~~~java
public enum Channel {
    EMAIL,
    SMS,
    PUSH
}

@ConfigurationProperties(prefix = "app.channel")
public record ChannelProperties(
        Map<Channel, Duration> delays
) {
}
~~~

~~~yaml
app:
  channel:
    delays:
      EMAIL: 1s
      SMS: 500ms
      PUSH: 2s
~~~

The Binder can convert keys to the matching enum constants. For enums, standardize value formatting and add binding tests to catch config mismatches if a constant is renamed.

## 7. Nested configuration (nested properties)

A client may have a retry policy, authentication, an endpoint list, and size limits. Putting all properties on one level with very long names makes configuration hard to read.

A more natural form:

~~~yaml
app:
  transport:
    connect-timeout: 3s
    max-in-memory: 2MB
    retry:
      max-attempts: 4
      backoff: 250ms
    endpoints:
      - name: primary
        url: https://primary.example.test
        timeout: 1s
      - name: backup
        url: https://backup.example.test
        timeout: PT2S
~~~

In Java, you can model this with nested records.

### 7.1. Nested records with constructor binding

~~~java
package com.example.config;

import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.transport")
public record TransportProperties(
        Duration connectTimeout,
        DataSize maxInMemory,
        Retry retry,
        List<Endpoint> endpoints
) {
    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {}

    public record Endpoint(
            String name,
            String url,
            Duration timeout
    ) {}
}
~~~

YAML paths map to components:

| Property path | Location in object |
| --- | --- |
| `app.transport.connect-timeout` | `TransportProperties.connectTimeout()` |
| `app.transport.max-in-memory` | `TransportProperties.maxInMemory()` |
| `app.transport.retry.max-attempts` | `TransportProperties.retry().maxAttempts()` |
| `app.transport.retry.backoff` | `TransportProperties.retry().backoff()` |
| `app.transport.endpoints[0].name` | `TransportProperties.endpoints().get(0).name()` |
| `app.transport.endpoints[1].timeout` | `TransportProperties.endpoints().get(1).timeout()` |

In Spring Boot 3.x, a record with a single constructor uses constructor binding when registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`; `@ConstructorBinding` is not needed in this simple case.

Nested configuration can go multiple levels deep. However, if one class accumulates too many branches, consider splitting property groups by subsystem responsibility.

### 7.2. Lists of nested objects

`List<Endpoint>` lets you declare multiple endpoints, each with a name, URL, and timeout.

~~~java
for (TransportProperties.Endpoint endpoint : properties.endpoints()) {
    System.out.println(
            endpoint.name() + " -> " + endpoint.url()
                    + ", timeout=" + endpoint.timeout()
    );
}
~~~

When list items are objects, YAML lists are usually much easier to read than a long run of indexed properties. In `.properties`, the equivalent paths are:

~~~properties
app.transport.endpoints[0].name=primary
app.transport.endpoints[0].url=https://primary.example.test
app.transport.endpoints[0].timeout=1s

app.transport.endpoints[1].name=backup
app.transport.endpoints[1].url=https://backup.example.test
app.transport.endpoints[1].timeout=2s
~~~

Define an appropriate `Endpoint` class/record and add validation if endpoint names or URLs are required.

### 7.3. Maps whose values are nested objects

Sometimes you need lookup by a fixed key rather than list position:

~~~java
@ConfigurationProperties(prefix = "app.routes")
public record RouteProperties(
        Map<String, Route> targets
) {
    public record Route(
            String baseUrl,
            Duration timeout,
            DataSize maxPayload
    ) {}
}
~~~

~~~yaml
app:
  routes:
    targets:
      orders:
        base-url: https://orders.example.test
        timeout: 3s
        max-payload: 1MB
      payments:
        base-url: https://payments.example.test
        timeout: 5s
        max-payload: 512KB
~~~

This creates `Map<String, Route>` with keys `orders` and `payments`. Choose `List<Route>` when order matters; choose `Map<String, Route>` when route names are lookup identifiers.

## 8. Complete immutable configuration with records and defaults

You can combine `Duration`, `DataSize`, collections, nested records, and validation in one realistic configuration.

### 8.1. TransportProperties class

~~~java
package com.example.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.transport")
@Validated
public record TransportProperties(
        @NotNull
        @DefaultValue("3s")
        Duration connectTimeout,

        @NotNull
        @DefaultValue("2MB")
        DataSize maxInMemory,

        List<String> regions,
        Map<String, DataSize> quotas,

        @Valid
        @DefaultValue
        Retry retry,

        List<@Valid Endpoint> endpoints
) {
    public TransportProperties {
        regions = regions == null ? List.of() : List.copyOf(regions);
        quotas = quotas == null ? Map.of() : Map.copyOf(quotas);
        endpoints = endpoints == null ? List.of() : List.copyOf(endpoints);
    }

    public record Retry(
            @Min(1)
            @DefaultValue("3")
            int maxAttempts,

            @NotNull
            @DefaultValue("500ms")
            Duration backoff
    ) {}

    public record Endpoint(
            @NotBlank
            String name,

            @NotBlank
            String url,

            @NotNull
            @DefaultValue("1s")
            Duration timeout
    ) {}
}
~~~

Design explanation:

- `@ConfigurationProperties(prefix = "app.transport")` identifies the property group.
- `@Validated` requests validation when the configuration binds.
- `@NotNull` ensures required fields are not null after defaults are applied.
- `@DefaultValue("3s")` supplies a default for constructor binding when the property is absent.
- `@DefaultValue` with no arguments on `Retry` instructs the binder to create the nested object using its components' defaults, even if no `retry` key is present in the configuration source.
- `@Min(1)` ensures the retry count is at least one.
- `@Valid` cascades validation into nested objects.
- `List<@Valid Endpoint>` validates individual endpoint items.
- The compact constructor normalizes lists and maps into immutable collections, avoiding nulls when collections are unconfigured.

To provide a Bean Validation provider in a Boot 3.3 project, you usually need:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

For a project that already brings in the validation starter transitively, there is no need to duplicate it just for this example. Never assume Jakarta Validation annotations execute without a validation provider present.

### 8.2. YAML for the combined configuration

~~~yaml
app:
  transport:
    connect-timeout: 5s
    max-in-memory: 4MB
    regions:
      - apac
      - emea
    quotas:
      images: 32MB
      documents: 8MB
    retry:
      max-attempts: 4
      backoff: 750ms
    endpoints:
      - name: primary
        url: https://primary.example.test
        timeout: 1s
      - name: backup
        url: https://backup.example.test
        timeout: PT2S
~~~

After binding:

~~~java
properties.connectTimeout();         // Duration.ofSeconds(5)
properties.maxInMemory();            // DataSize.ofMegabytes(4)
properties.regions();                // [apac, emea]
properties.quotas().get("images");   // DataSize.ofMegabytes(32)
properties.retry().maxAttempts();    // 4
properties.retry().backoff();        // Duration.ofMillis(750)
properties.endpoints().get(1).name();// "backup"
~~~

These methods are invoked on a `TransportProperties` bean registered and successfully bound by Spring Boot.

### 8.3. What if the entire retry branch is omitted?

Because the `retry` parameter carries `@DefaultValue`, the binder can construct a `Retry` using the defaults of its two inner components instead of leaving `retry` as null.

Without `@DefaultValue` on that nested component and with no `retry` properties present, a nested object under constructor binding can be null. That is why many record-based configuration examples place `@DefaultValue` on nested parameters.

Do not use defaults to hide genuinely mandatory configuration. If a missing endpoint should fail startup, use validation and clear error messages.

## 9. Registering @ConfigurationProperties in Spring Boot 3

A `@ConfigurationProperties` class must be registered with Spring so the binder creates the object and injects it into services.

### 9.1. @ConfigurationPropertiesScan

In an application, place the main class in a root package covering `com.example.config`:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExampleApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` discovers `@ConfigurationProperties` classes in scanned packages. This works well when an application has multiple similar configuration classes.

### 9.2. @EnableConfigurationProperties

When you want to register one or more classes explicitly:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(TransportProperties.class)
public class TransportConfiguration {
}
~~~

This is common in Java configuration or library auto-configuration.

For immutable constructor-bound records, use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. Do not slap `@Component` onto a record expecting Spring to bind its constructor as configuration properties; regular Spring constructor injection and properties constructor binding use different registration mechanisms.

### 9.3. @ConfigurationProperties on a @Bean method

When binding a JavaBean object from an external library, you can put the annotation on a `@Bean` method:

~~~java
@Configuration(proxyBeanMethods = false)
public class VendorConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "vendor.pool")
    VendorPoolSettings vendorPoolSettings() {
        return new VendorPoolSettings();
    }
}
~~~

This assumes `VendorPoolSettings` has suitable getters and setters. This is helpful when you cannot edit the library class source to add annotations.

Difference: here the object is constructed by the factory method and properties are bound onto it afterward. An immutable record without setters should not be used with this factory-method JavaBean binding style without a dedicated design.

## 10. JavaBean binding: an alternative alongside records

Records are convenient for immutable configuration. However, mutable classes with a no-args constructor, getters, and setters remain supported by the binder.

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.http")
public class HttpClientProperties {
    private Duration timeout = Duration.ofSeconds(3);
    private DataSize maxBuffer = DataSize.ofMegabytes(2);
    private final Retry retry = new Retry();

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public DataSize getMaxBuffer() {
        return maxBuffer;
    }

    public void setMaxBuffer(DataSize maxBuffer) {
        this.maxBuffer = maxBuffer;
    }

    public Retry getRetry() {
        return retry;
    }

    public static class Retry {
        private int attempts = 3;

        public int getAttempts() {
            return attempts;
        }

        public void setAttempts(int attempts) {
            this.attempts = attempts;
        }
    }
}
~~~

With JavaBean binding, the binder invokes the corresponding setters. The nested `Retry` object is pre-initialized and exposed via a getter, so the binder can populate its inner properties without needing a separate setter to replace the entire nested instance.

Comparison:

| Criterion | Record / constructor binding | JavaBean / setter binding |
| --- | --- | --- |
| Model | Constructs instance from constructor parameters | Constructs object then updates properties |
| Immutability | Easy to keep immutable state | Typically mutable |
| Default values | `@DefaultValue` or constructor logic | Field initializers |
| Nested objects | Nested records/classes via constructor binding | Nested beans via getters/setters |
| Best suited for | Stable, type-safe application config | Legacy libraries, setter-based classes, or `@Bean` binding |

Both approaches can coexist in one application as long as each class is registered and bound properly.

## 11. Relaxed binding of property names

Spring Boot allows different property naming styles to bind to the same Java property.

Suppose the record component is `connectTimeout`; the canonical name in config is:

~~~yaml
app:
  transport:
    connect-timeout: 5s
~~~

In `application.properties`:

~~~properties
app.transport.connect-timeout=5s
~~~

In certain configuration sources, camelCase names may also be recognized under relaxed binding rules. Spring Boot recommends **lowercase kebab-case** for property names in configuration files.

### 11.1. Environment variables

Environment variable names are usually derived from canonical property names by:

1. Replacing dots `.` with underscores `_`.
2. Removing dashes `-`.
3. Converting to uppercase.

For example:

| Canonical property | Environment variable |
| --- | --- |
| `app.transport.connect-timeout` | `APP_TRANSPORT_CONNECTTIMEOUT` |
| `app.transport.max-in-memory` | `APP_TRANSPORT_MAXINMEMORY` |
| `app.transport.retry.max-attempts` | `APP_TRANSPORT_RETRY_MAXATTEMPTS` |

This is a common pitfall: from `connect-timeout`, the dash is **removed** under this rule. `APP_TRANSPORT_CONNECT_TIMEOUT` is not the official canonical conversion of that same property.

For lists, indices are represented as numbers enclosed by underscores:

~~~text
APP_TRANSPORT_ENDPOINTS_0_NAME
APP_TRANSPORT_ENDPOINTS_0_TIMEOUT
APP_TRANSPORT_ENDPOINTS_1_NAME
~~~

Verify effective environment variable names in your specific deployment setup; platforms may impose naming constraints or normalize keys differently.

### 11.2. Relaxed binding does not forgive invalid data formats

Relaxed binding mainly helps match **property names**. It does not mean an invalid duration or size string will be fixed automatically.

For example:

~~~properties
app.transport.connect-timeout=fast
app.transport.max-in-memory=large
~~~

The Binder cannot convert `fast` to `Duration` or `large` to `DataSize` under standard contracts. Conversion errors must be fixed at the configuration source or handled by an intentionally designed converter.

## 12. Collections and Maps when multiple configuration sources override

Here is a critical distinction in Spring Boot: **lists and maps typically combine across property sources differently**.

### 12.1. Lists are usually replaced as a whole

Suppose `application.yml` has:

~~~yaml
app:
  delivery:
    regions:
      - apac
      - emea
~~~

And a higher-precedence source sets:

~~~yaml
app:
  delivery:
    regions:
      - americas
~~~

When binding `List<String>`, the list from the higher-precedence source is used; it does not concatenate into `[apac, emea, americas]`.

If you want regions combined according to custom rules, implement explicit aggregation in code or structure the configuration differently. Do not count on the binder to merge lists across sources.

### 12.2. Maps can merge keys

Suppose the base source has:

~~~yaml
app:
  upload:
    quotas:
      images: 16MB
      documents: 8MB
~~~

Higher-precedence source:

~~~yaml
app:
  upload:
    quotas:
      images: 32MB
~~~

A map can retain the `documents` key from the base source while the `images` key receives `32MB` from the higher-precedence source.

For maps whose values are complex objects, branch/property merging has additional subtleties; test the actual scenario before treating it as a deployment contract.

### 12.3. Profile-specific configuration

The same source-precedence behavior occurs with profile-specific files or profile-activated YAML documents.

For example, settings in `application-prod.yml` can override lists in `application.yml`. When deploying, check active profiles and higher-precedence property sources to know what the final collection contains.

A common mistake is thinking that adding one element in a profile file appends to the base list. With list binding, it normally replaces the list.

## 13. Validation for Duration, DataSize, collections, and nested objects

Type conversion verifies whether a value can convert to the target type. Yet successful conversion does not guarantee the configuration satisfies business rules.

For example:

- `-5s` may be a valid `Duration` syntactically, yet invalid as a connect timeout.
- `0B` is a representable `DataSize`, yet invalid for a buffer limit required to be positive.
- `max-attempts=0` converts to `int`, yet is invalid if the system requires at least one attempt.
- An endpoint missing `name` or `url` can fail at runtime if not checked early.

### 13.1. Jakarta Bean Validation

Combine `@Validated` with constraint annotations:

~~~java
@ConfigurationProperties(prefix = "app.retry")
@Validated
public record RetryProperties(
        @Min(1) int maxAttempts,
        @NotNull Duration backoff,
        @NotNull DataSize maxPayload
) {
}
~~~

If `max-attempts=0` or a required value is missing, validation can fail startup with a message identifying the offending property.

When a nested type needs validation, add `@Valid` at the appropriate site:

~~~java
@ConfigurationProperties(prefix = "app.worker")
@Validated
public record WorkerProperties(
        @Valid
        @NotNull
        Retry retry
) {
    public record Retry(
            @Min(1) int attempts
    ) {}
}
~~~

`@Valid` enables validating constraints inside the nested object. If the entire branch is omitted without a default, the nested object can be null; hence `@NotNull` on the nested component is a separate requirement.

### 13.2. Checking positive Duration via domain validation

If you need to guarantee a positive timeout, you can enforce the check in a compact constructor:

~~~java
@ConfigurationProperties(prefix = "app.deadline")
public record DeadlineProperties(
        @DefaultValue("5s") Duration timeout
) {
    public DeadlineProperties {
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
    }
}
~~~

This check runs inside the record constructor when the binder instantiates the object. It works well for simple invariants. If you use Bean Validation across the whole application, you can create a custom constraint for consistent messaging and metadata.

Similarly for `DataSize`:

~~~java
if (maxBuffer == null || maxBuffer.toBytes() <= 0) {
    throw new IllegalArgumentException("maxBuffer must be positive");
}
~~~

Do not try to apply `@Min(1)` directly onto `Duration` or `DataSize` if your validator does not support that constraint on those target types. `@Min` is primarily intended for numeric types under Jakarta Validation's contract.

### 13.3. Validating collections

Use `@NotEmpty` if a list or map must contain at least one entry:

~~~java
@ConfigurationProperties(prefix = "app.routes")
@Validated
public record RouteProperties(
        @NotEmpty
        List<@Valid Route> routes
) {
    public record Route(
            @NotBlank String name,
            @NotBlank String url
    ) {}
}
~~~

When configuration omits `routes` or provides an empty list, validation rejects the configuration. This is much clearer than letting the app start and fail later for lack of routes.

## 14. When binding fails, what does Spring Boot report?

Errors fall into different categories:

| Scenario | Example | Cause |
| --- | --- | --- |
| Invalid Duration format | `timeout=soon` | Cannot convert string to `Duration` |
| Invalid DataSize format | `max-buffer=very-large` | Cannot convert string to `DataSize` |
| Number incompatible with type | `max-attempts=abc` | Cannot convert to `int` |
| Missing required property | `base-url` omitted | Binding/validation fails constraint |
| Malformed collection structure | Object list missing index or required field | Source does not match structure expected by binder |
| Missing nested object | No `retry` branch | Nested component may be null without default |
| Convertible value violating business rule | `max-attempts=0` | Validation or invariant failure |

A binding error typically reports the property path, offending value, target type, and configuration origin if available. Read the deeper root cause rather than looking only at the outer bean-creation wrapper exception.

### 14.1. Step-by-step diagnosis

1. Identify which `@ConfigurationProperties` bean failed to create.
2. Read the failing property path, such as `app.transport.connect-timeout`.
3. Check the target Java type: `Duration`, `DataSize`, `List<Endpoint>`, or another type.
4. Check the actual value in the highest-precedence property source.
5. Verify format, units, and list indexing or map key syntax.
6. Check defaults, nested binding, and validation.
7. When still unsure, write a small context test with the exact property values.

For unit errors, fix the configuration to include explicit suffixes. Avoid changing Java fields to `String` just to bypass conversion errors; that pushes failures to runtime and forfeits the benefits of type-safe binding.

### 14.2. Watch out for unbound properties

If YAML contains a typo that does not match any field in the class, that key may be ignored depending on binder settings. `@ConfigurationProperties` offers attributes like `ignoreUnknownFields`, though enabling strict mode indiscriminately can break when a prefix shares keys with another component.

If strict configuration is needed, test key properties, validate required fields, and choose distinct prefixes to avoid colliding with other modules.

## 15. Testing type-safe binding with ApplicationContextRunner

You do not need to launch an entire web server to verify a `@ConfigurationProperties` bean. Spring Boot test support offers `ApplicationContextRunner` to spin up a lightweight context and pass property values.

Assume we use the composite `TransportProperties` class from Section 8.

### 15.1. Testing binding of Duration, DataSize, and nested records

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.unit.DataSize;

class TransportPropertiesBindingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(TransportProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsDurationsDataSizesCollectionsAndNestedProperties() {
        runner.withPropertyValues(
                "app.transport.connect-timeout=5s",
                "app.transport.max-in-memory=4MB",
                "app.transport.regions[0]=apac",
                "app.transport.regions[1]=emea",
                "app.transport.quotas.images=32MB",
                "app.transport.retry.max-attempts=4",
                "app.transport.retry.backoff=750ms",
                "app.transport.endpoints[0].name=primary",
                "app.transport.endpoints[0].url=https://primary.example.test",
                "app.transport.endpoints[0].timeout=1s"
        ).run(context -> {
            assertThat(context).hasSingleBean(TransportProperties.class);

            TransportProperties properties =
                    context.getBean(TransportProperties.class);

            assertThat(properties.connectTimeout())
                    .isEqualTo(Duration.ofSeconds(5));
            assertThat(properties.maxInMemory().toBytes())
                    .isEqualTo(DataSize.ofMegabytes(4).toBytes());
            assertThat(properties.regions())
                    .containsExactly("apac", "emea");
            assertThat(properties.quotas().get("images"))
                    .isEqualTo(DataSize.ofMegabytes(32));
            assertThat(properties.retry().maxAttempts()).isEqualTo(4);
            assertThat(properties.retry().backoff())
                    .isEqualTo(Duration.ofMillis(750));
            assertThat(properties.endpoints().get(0).name())
                    .isEqualTo("primary");
        });
    }
}
~~~

This example uses test dependencies from the Spring Boot test starter and a Bean Validation provider because Section 8's class uses `@Validated`. A full `@SpringBootTest` is unnecessary just to test the binder.

### 15.2. Testing default values

~~~java
@Test
void usesDefaultsWhenOptionalPropertiesAreMissing() {
    runner.run(context -> {
        TransportProperties properties =
                context.getBean(TransportProperties.class);

        assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofSeconds(3));
        assertThat(properties.maxInMemory())
                .isEqualTo(DataSize.ofMegabytes(2));
        assertThat(properties.retry().maxAttempts()).isEqualTo(3);
        assertThat(properties.retry().backoff())
                .isEqualTo(Duration.ofMillis(500));
        assertThat(properties.regions()).isEmpty();
        assertThat(properties.quotas()).isEmpty();
    });
}
~~~

Notably, the nested `Retry` record is still constructed even with zero `retry` properties supplied, thanks to `@DefaultValue` on the nested parameter.

### 15.3. Testing validation errors

~~~java
@Test
void rejectsInvalidRetryCount() {
    runner.withPropertyValues(
            "app.transport.retry.max-attempts=0"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

This test verifies that configuration fails to initialize when invariants are violated. In real applications, you can also inspect failure messages and property paths to ensure diagnostics are clear, while avoiding brittle assertions on entire exception strings that may change across framework versions.

### 15.4. Testing list overrides across property sources

An advanced test can supply a base property source with `regions[0]=apac` and `regions[1]=emea`, and then add a higher-precedence source setting `regions[0]=americas`. Verify the resulting list matches Spring Boot's real behavior.

Do not pass all properties inside a single `withPropertyValues` call and treat it as a multi-source precedence test. Set up distinct property sources when testing override behavior accurately.

## 16. When do you need a custom converter?

Types like `Duration`, `DataSize`, enums, common numeric types, and many collections are converted out of the box by Spring Boot.

If your domain has a specialized configuration type, such as `ShardId` formatted as `shard-12`, you can define a dedicated converter:

~~~java
public record ShardId(int value) {
    public ShardId {
        if (value < 0) {
            throw new IllegalArgumentException("Shard ID must be non-negative");
        }
    }
}
~~~

Converter:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public class ShardIdConverter implements Converter<String, ShardId> {
    @Override
    public ShardId convert(String source) {
        if (!source.startsWith("shard-")) {
            throw new IllegalArgumentException("Expected shard-N");
        }

        int number = Integer.parseInt(source.substring("shard-".length()));
        return new ShardId(number);
    }
}
~~~

Then a property:

~~~properties
app.storage.shard=shard-12
~~~

can bind to a `ShardId` field once the converter is properly registered.

`@ConfigurationPropertiesBinding` marks a converter for configuration-properties binding. These converters may be instantiated very early in the application lifecycle; avoid making them depend on business services or complex bean graphs.

Do not write custom converters for `Duration` or `DataSize` when Spring Boot's standard format already suffices. Prefer built-in converters to minimize code and prevent inconsistencies across modules.

## 17. Common design mistakes

### 17.1. Using bare numbers without units

~~~yaml
app:
  transport:
    connect-timeout: 10
    max-in-memory: 10
~~~

Under default conversion, `10` can mean **10 milliseconds** for `Duration` and **10 bytes** for `DataSize`. That may not match what the author intended.

Write instead:

~~~yaml
app:
  transport:
    connect-timeout: 10s
    max-in-memory: 10MB
~~~

### 17.2. Using String instead of dedicated types

If a class declares:

~~~java
public record UploadProperties(String maxSize) {}
~~~

every consumer must know the syntax, parse numbers and units, handle errors, and convert manually. Using `DataSize` centralizes conversion logic in the binder.

### 17.3. Using Map<String, Object> for all configuration

An untyped map forces services to cast values, check keys manually, and discover errors late. Use records or classes with explicit fields whenever the schema is known.

`Map<String, X>` still makes sense when the set of keys is genuinely dynamic, yet the value type should be concrete rather than defaulting everywhere to `Object`.

### 17.4. Assuming lists merge across all profiles

List branches are usually replaced according to property-source precedence. If a profile supplies only a first item, remaining items from other sources are not appended automatically.

### 17.5. Forgetting to validate nested objects

`@Validated` on the root class does not guarantee constraints inside nested types run automatically. You need `@Valid` on nested beans/collection elements along with an appropriate validation provider.

### 17.6. Using configuration as mutable runtime state

`@ConfigurationProperties` models application configuration. If you need per-request, per-tenant, per-job, or per-user mutable state, use a dedicated context/domain object or storage. Do not call setters on singleton properties beans as an ad-hoc way to store business state.

### 17.7. Confusing configuration values with runtime side effects

A `DataSize maxPayload` field does not automatically block oversized payloads. A `Duration timeout` field does not automatically configure an HTTP client. Consuming beans must read and apply those values via their underlying library APIs.

### 17.8. Binding configured but forgetting to register the properties bean

Annotating a class with `@ConfigurationProperties` is insufficient unless it is scanned or enabled. If injection fails, verify `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, scan packages, and source configuration.

## 18. Practice exercises

### Exercise 1 — Duration in different formats

Create a `@ConfigurationProperties` class with three `Duration` fields: `connectTimeout`, `retryDelay`, and `cacheTtl`. Bind `5s`, `250ms`, and `PT10M` respectively. Write tests checking them against `Duration.ofSeconds`, `Duration.ofMillis`, and `Duration.ofMinutes`.

### Exercise 2 — @DurationUnit and @DataSizeUnit

Create two properties of type `Duration` and `DataSize`, annotated with `@DurationUnit(ChronoUnit.SECONDS)` and `@DataSizeUnit(DataUnit.MEGABYTES)`. Pass unitless numbers, then compare against values with explicit suffixes.

### Exercise 3 — Ordered collections

Create `List<Duration> retryDelays` configured via YAML with `100ms`, `500ms`, and `2s`. Write simulated retry logic executing in order and explain why `Set<Duration>` is unsuitable.

### Exercise 4 — Map of sizes by file category

Bind `Map<String, DataSize> quotas` with keys `images`, `documents`, and `videos`. Write a method taking a file type and returning the corresponding byte limit. Include a missing-key case to practice fallback handling.

### Exercise 5 — Nested records

Create `ClientProperties` containing nested `Retry` and `List<Endpoint>`. Write YAML with two endpoints having different timeouts. Verify both elements bind in order and nested retry values populate cleanly.

### Exercise 6 — Fail-fast validation

Add `@Validated`, `@Min(1)`, and `@NotBlank` to the configuration. Intentionally pass `max-attempts=0` and an endpoint missing its name. Confirm the test context fails before any service processes requests.

### Exercise 7 — Precedence between lists and maps

Create two property sources with different precedence. The base source contains two list elements and two map entries; the higher-precedence source declares a single list element and overrides one map key. Verify the difference between list replacement and map merging.

### Exercise 8 — Configuration from environment variables

Bind `app.transport.connect-timeout`, `app.transport.retry.max-attempts`, and `app.transport.endpoints[0].name` via environment variable names following relaxed binding rules. Record the exact variable names and verify values after startup.

## 19. References

- [Spring Boot 3.3 — Externalized Configuration and Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 — Conversion of Durations, Periods and Data Sizes](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion)
- [Spring Framework — DataSize API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/util/unit/DataSize.html)

## 20. Key takeaways

Spring Boot can convert property values directly into `Duration`, `DataSize`, collections, and nested objects via `@ConfigurationProperties`. `Duration` lets you configure timeouts/delays with values like `5s` or `PT30S`, while `DataSize` lets you configure sizes with `512KB` or `32MB`. Unitless numbers default to milliseconds for `Duration` and bytes for `DataSize`; `@DurationUnit` and `@DataSizeUnit` let you customize default units when needed.

Collections model multiple values of the same kind; `List` fits when order matters, `Set` fits unique sets of values, and `Map` fits key-based lookups. Lists are typically replaced by higher-precedence property sources, whereas maps can merge keys across sources. Nested records/classes model groups like retry policies, endpoints, and quotas without manual parsing.

In Spring Boot 3.x, single-constructor records support constructor binding, `@DefaultValue` supplies defaults, and `@Validated` with Jakarta Validation catches invalid configuration at startup. Register beans via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, test with `ApplicationContextRunner`, and remember: binding yields typed data; consuming components remain responsible for applying timeouts or size limits at runtime.
