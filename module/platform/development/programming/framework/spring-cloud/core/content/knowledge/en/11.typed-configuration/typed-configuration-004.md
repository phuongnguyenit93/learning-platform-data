# Converting `Duration`, `DataSize`, and Custom Data Types

Application configuration frequently contains values with units: timeouts in milliseconds, cleanup intervals in seconds, cache memory limits in megabytes, or upload limits in bytes. If all of these are read as strings and parsed manually in multiple places, the application easily suffers from unit mismatches, inconsistent conversions, and errors that only appear at request time.

Spring Boot supports binding configuration to meaningful types such as **`java.time.Duration`** and **`org.springframework.util.unit.DataSize`**. For custom business types, an application can register a converter to transform configuration strings into value objects. Once bound, values can be validated, shared, and tested right during startup.

This lesson belongs to the **Typed Configuration** chapter of the **SPRING_CLOUD_CORE** module. It focuses on unit conversion, typed configuration in Spring Boot, custom converters, validation, and how these values participate in configuring Spring Cloud components such as HTTP clients, discovery, and service registries.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why configuration should bind to typed objects rather than keeping all values as `String`.
2. Convert timeouts and time intervals to `Duration`.
3. Convert storage/size limits to `DataSize`.
4. Use `@DurationUnit` and `@DataSizeUnit` to define default units for bare numeric values without suffixes.
5. Create custom data types and register `Converter<String, T>` for `@ConfigurationProperties`.
6. Distinguish converters intended for configuration binding from the general application `ConversionService`.
7. Combine conversion, default values, and validation to catch misconfiguration at startup.
8. Test successful binding, boundary values, and conversion failures.

## 2. Why Is Typed Configuration Needed?

Suppose a service calls Inventory Service and enforces a response size limit:

~~~yaml
clients:
  inventory:
    read-timeout: "700"
    max-response-size: "8"
~~~

If both values are read as strings, application code has to decide on its own whether `"700"` means milliseconds or seconds, and whether `"8"` means bytes, kilobytes, or megabytes. Two teams can pick different units without the compiler catching it.

Typed configuration expresses intent much more clearly:

~~~yaml
clients:
  inventory:
    read-timeout: 700ms
    max-response-size: 8MB
~~~

After binding:

- `readTimeout` has type `Duration`.
- `maxResponseSize` has type `DataSize`.
- Business code can call `toMillis()`, `toSeconds()`, or `toBytes()`.
- Format errors can be caught when Spring initializes the configuration bean.
- Consuming classes no longer parse strings repeatedly across the codebase.

| Configuration Value | Appropriate Type | Usage Example |
| --- | --- | --- |
| Connection timeout | `Duration` | HTTP client, database pool |
| Refresh or cleanup interval | `Duration` | Scheduler, cache eviction |
| TTL | `Duration` | Cache, token expiry |
| Upload limit | `DataSize` | Multipart, file validation |
| Cache capacity | `DataSize` | Buffer, cache capacity |
| Region code, tenant, endpoint type | Custom value object | Discovery metadata, routing policy |

Data types alone do not guarantee business validity. For example, a `Duration` can be zero or negative; a `DataSize` can fall outside operational limits. Type conversion and validation are complementary steps.

## 3. Converting `Duration`

Java's `Duration` represents a span of time, not a calendar timestamp. Spring Boot includes converters supporting familiar unit suffixes as well as ISO-8601 strings.

### 3.1. Common Value Formats

Example:

~~~yaml
clients:
  inventory:
    connect-timeout: 250ms
    read-timeout: 2s
    retry-delay: 1m
    long-poll-timeout: PT30S
~~~

Common representations:

| Value | Meaning |
| --- | --- |
| `250ms` | 250 milliseconds |
| `2s` | 2 seconds |
| `1m` | 1 minute |
| `5h` | 5 hours |
| `PT30S` | 30 seconds in ISO-8601 |
| `PT1H15M` | 1 hour 15 minutes in ISO-8601 |

For simple formats, Spring Boot supports common time unit suffixes such as `ns`, `us`, `ms`, `s`, `m`, `h`, and `d`. ISO-8601 is helpful for complex durations or when standard cross-system formatting is needed.

Prefer explicit suffixes like `700ms` or `15s` over bare numbers. This makes intent readable and avoids relying on default units.

### 3.2. Numeric Values Without Suffixes

If a `Duration` property receives a bare number without a unit, Spring Boot interprets it as **milliseconds** by default.

Example:

~~~yaml
clients:
  inventory:
    read-timeout: 700
~~~

This value equals `700ms`, not `700s`.

You can change the default unit for a property using `@DurationUnit`:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.convert.DurationUnit;

public class PollingProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration interval = Duration.ofSeconds(30);

    public Duration getInterval() {
        return interval;
    }

    public void setInterval(Duration interval) {
        this.interval = interval;
    }
}
~~~

With this annotation, the bare number `15` binds to 15 seconds. If the config writes `15ms`, the explicit suffix still specifies milliseconds.

**Recommendation:** write unit suffixes in config files so readers do not have to hunt down annotations to know the unit. `@DurationUnit` is useful for backward compatibility with legacy bare-number configs or when defining an explicit default unit for the binding API.

### 3.3. Converting and Using Duration in Java

After binding, use the `Duration` API:

~~~java
Duration timeout = Duration.ofMillis(700);

long millis = timeout.toMillis();
long seconds = timeout.toSeconds();
boolean expired = timeout.isZero() || timeout.isNegative();
~~~

Commonly used methods:

- `Duration.ofMillis(value)`, `ofSeconds(value)`, `ofMinutes(value)`.
- `toMillis()`, `toSeconds()`, `toNanos()`.
- `plus(...)`, `minus(...)`, `multipliedBy(...)`.
- `isZero()`, `isNegative()`, `compareTo(...)`.

Be cautious when converting very large `Duration` values to milliseconds or nanoseconds: the conversion can exceed `long` range and throw `ArithmeticException`. Do not assume every syntactically valid value is safe for a target API with numeric limits.

## 4. Converting `DataSize`

Spring's `DataSize` represents a data capacity as a typed numeric value. It is useful for buffers, file uploads, caches, payloads, and resource limits.

### 4.1. Size Suffixes

Example:

~~~yaml
storage:
  max-file-size: 64MB
  buffer-size: 256KB
  cache-size: 2GB
~~~

Common units:

| Value | Meaning |
| --- | --- |
| `512B` | 512 bytes |
| `256KB` | 256 kilobytes |
| `64MB` | 64 megabytes |
| `2GB` | 2 gigabytes |
| `1TB` | 1 terabyte |

Spring `DataSize` and `DataUnit` use base-1024 multiples for kilo, mega, giga, and tera units. Thus `1MB` in this representation is `1,048,576` bytes. When exchanging values with systems using decimal SI conventions, agree explicitly on units to avoid discrepancies.

### 4.2. Numeric Values Without Suffixes

A bare number for `DataSize` defaults to **bytes**:

~~~yaml
storage:
  max-file-size: 1048576
~~~

This value is 1,048,576 bytes, corresponding to 1 MiB in base-1024 multiples—not 1 megabyte for the number 1.

You can change the default unit using `@DataSizeUnit`:

~~~java
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

public class StorageProperties {

    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize maxFileSize = DataSize.ofMegabytes(64);

    public DataSize getMaxFileSize() {
        return maxFileSize;
    }

    public void setMaxFileSize(DataSize maxFileSize) {
        this.maxFileSize = maxFileSize;
    }
}
~~~

With this field, the bare number `128` is interpreted as 128 megabytes. If `128KB` is written, the explicit suffix still takes effect.

### 4.3. Using DataSize

Example:

~~~java
DataSize limit = DataSize.ofMegabytes(64);

long bytes = limit.toBytes();
long kilobytes = limit.toKilobytes();
long megabytes = limit.toMegabytes();
~~~

Useful APIs:

- `DataSize.ofBytes(value)`.
- `DataSize.ofKilobytes(value)`.
- `DataSize.ofMegabytes(value)`.
- `DataSize.ofGigabytes(value)`.
- `toBytes()`, `toKilobytes()`, `toMegabytes()`.
- `compareTo(...)`, `plus(...)`, `minus(...)`.

When passing `DataSize` to an API accepting only `int`, check `Integer.MAX_VALUE` bounds before casting. Never blindly downcast from `long` to `int` as it can overflow.

## 5. Combining Duration and DataSize in ConfigurationProperties

A configuration group often contains multiple unit-bearing values. Using `@ConfigurationProperties` binds them into a single object.

### 5.1. application.yml File

~~~yaml
clients:
  inventory:
    base-url: https://inventory.internal.example
    connect-timeout: 250ms
    read-timeout: 2s
    max-response-size: 8MB
    polling-interval: 15
~~~

In this example:

- `connect-timeout` is 250 milliseconds.
- `read-timeout` is 2 seconds.
- `max-response-size` is 8 megabytes.
- `polling-interval` is 15 seconds if the Java property is annotated with `@DurationUnit(ChronoUnit.SECONDS)`.

### 5.2. Defining the Configuration Class

~~~java
import java.net.URI;
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "clients.inventory")
public class InventoryClientProperties {

    private URI baseUrl;

    private Duration connectTimeout = Duration.ofMillis(250);

    private Duration readTimeout = Duration.ofSeconds(2);

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration pollingInterval = Duration.ofSeconds(15);

    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize maxResponseSize = DataSize.ofMegabytes(8);

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }

    public Duration getPollingInterval() {
        return pollingInterval;
    }

    public void setPollingInterval(Duration pollingInterval) {
        this.pollingInterval = pollingInterval;
    }

    public DataSize getMaxResponseSize() {
        return maxResponseSize;
    }

    public void setMaxResponseSize(DataSize maxResponseSize) {
        this.maxResponseSize = maxResponseSize;
    }
}
~~~

Register the configuration class via scan:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Or register explicitly:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryConfiguration {
}
~~~

Choose a registration approach fitting your application structure. Do not both scan and explicitly declare the same class in multiple places if that creates duplicate registrations.

### 5.3. Default Values and Configured Values

Field initializers act as the object's defaults. If a property is absent, the binder keeps the initialized value. If the property is present, the binder converts the configured value and assigns it to the field.

Alternatives include:

- Using `@DefaultValue` in constructor binding/records to declare defaults at the parameter level.
- Using default values in configuration files.
- Using defaults on Java class fields or constructors.

Avoid scattering the same default across too many layers, which makes it hard for maintainers to tell which value takes effect. For critical values, test both omitted keys and overridden cases.

## 6. Custom Data Types and Converters

`Duration` and `DataSize` already have built-in converters. However, applications often define custom types representing domain concepts, such as:

- `RegionCode`: deployment region code.
- `TenantId`: tenant identifier.
- `ServiceAlias`: logical name of a downstream service.
- `RetryWindow`: structured retry policy.
- `StorageTier`: storage tier with custom rules.

If a configuration file holds a string for a custom type, register a `Converter<String, T>` so Spring Boot binding converts the string into the object.

### 6.1. Defining a Value Object

Example `RegionCode` normalizing region codes like `vn-hcm`:

~~~java
import java.util.Locale;

public record RegionCode(String value) {

    public RegionCode {
        if (value == null) {
            throw new IllegalArgumentException("Region code is required");
        }

        String normalized = value.trim().toLowerCase(Locale.ROOT);

        if (!normalized.matches("[a-z]{2}-[a-z0-9-]{2,20}")) {
            throw new IllegalArgumentException(
                    "Region code must match language-region format"
            );
        }

        value = normalized;
    }
}
~~~

A value object is responsible for enforcing its own invariants. Invalid codes must not produce a seemingly valid `RegionCode`.

### 6.2. Registering a Converter for Configuration Binding

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
class RegionCodeConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static Converter<String, RegionCode> regionCodeConverter() {
        return source -> new RegionCode(source);
    }
}
~~~

`@ConfigurationPropertiesBinding` marks a converter dedicated to `@ConfigurationProperties` binding. Declaring the `@Bean` method as `static` prevents premature instantiation of the configuration class while the binding infrastructure is being initialized.

The converter takes a string and constructs `RegionCode`. If the constructor throws `IllegalArgumentException`, binding fails and the application refuses to start with an invalid region code.

Avoid adding `@Component` or registering a global converter indiscriminately when the goal is only configuration binding. `@ConfigurationPropertiesBinding` scopes the converter's purpose and avoids altering conversion behavior elsewhere in the application.

### 6.3. Using Custom Types in Configuration

Declare the property:

~~~yaml
clients:
  inventory:
    region: VN-HCM
~~~

Add the field to `InventoryClientProperties`:

~~~java
private RegionCode region;

public RegionCode getRegion() {
    return region;
}

public void setRegion(RegionCode region) {
    this.region = region;
}
~~~

After binding, `VN-HCM` becomes `RegionCode("vn-hcm")`. Services can inject `InventoryClientProperties` and call `region()` or `getRegion()` without repeating trimming, lowercasing, and validation logic.

### 6.4. When to Use Converter, ConverterFactory, or GenericConverter?

| API | When Suitable |
| --- | --- |
| `Converter<S, T>` | A single clear source-to-target pair, e.g., `String` to `RegionCode` |
| `ConverterFactory<S, R>` | One source type converting to a family of target types, e.g., custom enum hierarchies |
| `GenericConverter` | Supporting multiple type pairs or complex conversion conditions |
| `Formatter<T>` | Parsing/formatting tied to text display, typically in web/data binding |

For a value object read from YAML, `Converter<String, T>` is usually the simplest and easiest option to test.

## 7. Distinguishing ConfigurationProperties Converters from the General ConversionService

Spring provides `ConversionService` for type conversion. Spring Boot applies appropriate converters during configuration binding. However, a converter registered with the `@ConfigurationPropertiesBinding` qualifier is specifically intended for configuration properties binding.

This prevents a converter added solely for YAML reading from inadvertently affecting:

- Request parameters in Spring MVC.
- Form binding.
- Data binding for other beans.
- Conversions in components using the shared `ConversionService`.

If the application genuinely needs a conversion across broader layers, design and register a `ConversionService` scoped appropriately. Do not assume configuration converters will automatically appear everywhere `conversionService.convert(...)` is called.

### 7.1. Do Not Build a Custom ConversionService for Every Property

Spring Boot already provides conversions for common types. For `Duration`, `DataSize`, `URI`, numbers, and booleans, writing custom converters is usually unnecessary.

Only add converters when the target type carries domain semantics or a custom format. If you build your own conversion service, ensure standard converters needed for binding remain present; replacing the default service improperly can break built-in conversions.

## 8. Validation After Conversion

Successful conversion does not imply business validity. For example:

- `Duration.ofMillis(-1)` is still a type-valid `Duration`.
- `Duration.ZERO` may be invalid for a timeout or polling interval.
- `DataSize.ofBytes(0)` may violate upload limit expectations.
- A `DataSize` larger than what the application permits can cause memory or resource pressure.

### 8.1. Using Jakarta Bean Validation

Enable validation on `@ConfigurationProperties` classes:

~~~java
import jakarta.validation.constraints.NotNull;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "clients.inventory")
@Validated
public class InventoryClientProperties {

    @NotNull
    private URI baseUrl;

    @NotNull
    private Duration readTimeout = Duration.ofSeconds(2);

    @NotNull
    private DataSize maxResponseSize = DataSize.ofMegabytes(8);

    @NotNull
    private RegionCode region;

    // getters/setters
}
~~~

To use Jakarta Bean Validation in Spring Boot, a compatible validation implementation must be present, typically via `spring-boot-starter-validation`. Adding annotations without a provider does not guarantee validation runs.

Constraints such as `@NotNull`, `@NotBlank`, `@Min`, and `@Max` work on supported types. Do not attach integer constraints directly onto `Duration` or `DataSize` expecting unit-aware comparisons. For rules like "timeout must be greater than 0" or "file size must not exceed 100MB", use a custom constraint/validator or check inside constructors/factories by design.

### 8.2. Checking Business Conditions

Example of an explicit check method:

~~~java
public void validateOperationalLimits() {
    if (readTimeout == null || readTimeout.isZero()
            || readTimeout.isNegative()) {
        throw new IllegalArgumentException(
                "read-timeout must be greater than zero"
        );
    }

    if (maxResponseSize == null || maxResponseSize.toBytes() <= 0) {
        throw new IllegalArgumentException(
                "max-response-size must be greater than zero"
        );
    }
}
~~~

In real applications, perform checks via Bean Validation or a centralized validation mechanism so errors are reported consistently. The snippet above simply illustrates the invariant.

## 9. Integrating Duration and DataSize with Spring Cloud Clients

A typed configuration group enables constructing clients with explicit timeouts and resource bounds.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryClientConfiguration {

    @Bean
    InventoryGateway inventoryGateway(InventoryClientProperties properties) {
        return new InventoryGateway(
                properties.getBaseUrl(),
                properties.getConnectTimeout(),
                properties.getReadTimeout(),
                properties.getMaxResponseSize(),
                properties.getRegion()
        );
    }
}
~~~

`InventoryGateway` is an example application class. Its constructor can accept these types:

~~~java
public InventoryGateway(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout,
        DataSize maxResponseSize,
        RegionCode region
) {
    // Initialize transport and service call policies.
}
~~~

Here, the types inform several decisions:

- `connectTimeout` bounds connection establishment time.
- `readTimeout` bounds response wait time as supported by the HTTP client.
- `maxResponseSize` limits payload or buffer sizes per the transport API.
- `region` can guide endpoint selection, metadata, or routing policies.

Note that binding a `Duration` does not automatically apply a timeout to an HTTP client. Your configuration bean must pass the value to the transport API in use. Similarly, `DataSize` does not automatically cap response bodies; configure the HTTP client or check payload sizes through the appropriate API.

### 9.1. Timeouts May Need Multiple Levels

A client may have:

- Connection timeout.
- Response/read timeout.
- Pool connection-acquisition timeout.
- Overall deadline for a business operation.
- Per-attempt timeout during retries.

Do not collapse all of these into a single `timeout` property if they have distinct meanings. `Duration` only represents a time span; enforcement depends on the transport, client, and orchestration layer.

### 9.2. Capacity Limits Also Need Clear Scope

`max-response-size` may bound an in-memory response body, which is not necessarily the same as a file upload limit, message broker payload limit, or cache capacity. Name properties according to their scope, for example:

~~~yaml
clients:
  inventory:
    max-response-size: 8MB

uploads:
  max-file-size: 32MB

cache:
  max-memory: 256MB
~~~

Each component binds to its corresponding property and applies it through its own API.

## 10. Testing Conversion and Binding

Configuration tests should cover suffixed values, bare numbers with unit annotations, custom converters, and invalid cases.

### 10.1. Testing Duration and DataSize

Example using `ApplicationContextRunner`:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.util.unit.DataSize;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            InventoryConfiguration.class,
                            RegionCodeConversionConfiguration.class
                    );

    @Test
    void bindsUnitsAndCustomType() {
        runner.withPropertyValues(
                "clients.inventory.base-url=https://inventory.example",
                "clients.inventory.connect-timeout=250ms",
                "clients.inventory.read-timeout=2s",
                "clients.inventory.polling-interval=15",
                "clients.inventory.max-response-size=8MB",
                "clients.inventory.region=VN-HCM"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            InventoryClientProperties properties =
                    context.getBean(InventoryClientProperties.class);

            assertThat(properties.getConnectTimeout())
                    .isEqualTo(Duration.ofMillis(250));

            assertThat(properties.getReadTimeout())
                    .isEqualTo(Duration.ofSeconds(2));

            assertThat(properties.getPollingInterval())
                    .isEqualTo(Duration.ofSeconds(15));

            assertThat(properties.getMaxResponseSize())
                    .isEqualTo(DataSize.ofMegabytes(8));

            assertThat(properties.getRegion())
                    .isEqualTo(new RegionCode("vn-hcm"));
        });
    }
}
~~~

This test assumes `InventoryConfiguration` enables `@EnableConfigurationProperties(InventoryClientProperties.class)` and registers the converter in the test context. It verifies both explicit suffixes and bare numbers interpreted via `@DurationUnit`.

### 10.2. Testing Bare Numbers and Default Units

Write dedicated tests to verify:

| Property | Value | Expected Result |
| --- | --- | --- |
| `read-timeout` of type Duration, no annotation | `700` | 700 milliseconds |
| `polling-interval` with `@DurationUnit(SECONDS)` | `15` | 15 seconds |
| `max-response-size` of type DataSize, no annotation | `1024` | 1024 bytes |
| `max-file-size` with `@DataSizeUnit(MEGABYTES)` | `64` | 64 megabytes per DataUnit |

These tests protect the application when renaming fields, moving configuration classes, or changing binding styles.

### 10.3. Testing Invalid Values

Scenarios worth testing:

- `read-timeout=fast`: not a valid duration.
- `max-response-size=large`: not a valid data size.
- `region=invalid!`: violates `RegionCode` rules.
- `read-timeout=0ms`: converts successfully, but must be rejected by business validation if a zero timeout is invalid.
- `max-response-size=0B`: converts successfully, but fails minimum limits if positive size is required.

Distinguish conversion errors from validation errors. Conversion errors happen when a string cannot be turned into the target type; validation errors happen once an object exists whose value violates a constraint.

## 11. Diagnosing Conversion Errors at Startup

When `@ConfigurationProperties` fails to bind, Spring Boot typically reports a bind error naming the property and target type. Inspect the root cause instead of looking only at the outermost exception.

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `Failed to bind properties` for Duration | Wrong suffix or format | Use `250ms`, `2s`, or ISO-8601 |
| Duration larger/smaller than expected | Bare number uses an unexpected default unit | Add suffix or `@DurationUnit` |
| DataSize larger/smaller than expected | Bare number defaults to bytes | Use suffix or `@DataSizeUnit` |
| `ConverterNotFoundException` | Converter for custom type not registered | Check `@ConfigurationPropertiesBinding` bean |
| Invalid value object | Converter or constructor rejected input | Check format and error message |
| Configuration bean not created | Missing `@ConfigurationProperties` registration or wrong prefix | Check scan/enable and key names |
| Validation does not run | Missing validation provider or `@Validated` | Add validation starter and check bean |
| Values bind properly yet client uses old values | Client created before updated configuration | Check lifecycle, refresh/recreate, and property wiring |

### 11.1. Reading the Exact Property Path

If the error reports:

~~~text
Failed to bind properties under 'clients.inventory.read-timeout'
to java.time.Duration
~~~

Inspect that exact key and target type. Do not blindly edit property names in the file, because the issue might be an unsupported format like `700seconds` or a higher-precedence source overriding it with another string.

### 11.2. Checking the Winning Property Source

A valid value in `application.yml` can still be overridden by environment variables, command-line arguments, or Config Server. Use `Environment` or a properly secured Actuator `env` endpoint to verify the effective value and its source.

### 11.3. Never Swallow Conversion Errors and Fall Back Silently

If a timeout has an invalid format, catching the exception and substituting `Duration.ZERO` or an arbitrary fallback can mask deployment errors. For required settings, fail startup with a message containing the property path. For optional settings, use explicit defaults and document the fallback policy.

## 12. Version and Compatibility Notes

The `Duration`, `DataSize`, `@DurationUnit`, `@DataSizeUnit`, and `@ConfigurationPropertiesBinding` APIs belong to the Spring Boot and Spring Framework ecosystem. When upgrading, verify:

- The Spring Boot release is compatible with your project's Spring Cloud release train.
- Package imports and annotation APIs match your version.
- How converters are registered and when the binder builds its conversion service.
- The Validation API (`jakarta.validation` in modern Boot generations; older projects may use a different namespace).
- How configuration is loaded via Config Data or legacy bootstrap.
- Whether transport clients accept `Duration` directly or only integer values in specific units.

Avoid pulling in the latest standalone `spring-boot` or `spring-cloud-commons` versions while bypassing the BOM. Use a compatible Spring Cloud BOM and inspect the dependency tree after changes.

## 13. Conventions for Designing Typed Configuration

For Spring Cloud applications, follow these conventions:

1. Use `Duration` for all properties representing time spans; avoid names like `timeoutMs` when `timeout` with explicit suffixes works.
2. Use `DataSize` for capacities; avoid storing raw byte counts across multiple layers.
3. Write explicit suffixes in YAML/Properties, e.g., `250ms`, `15s`, `8MB`.
4. Use `@DurationUnit` and `@DataSizeUnit` when supporting legacy bare-number configs or establishing a default unit.
5. Use `@ConfigurationProperties` for related configuration groups instead of parsing strings inside individual services.
6. Use custom types for value objects with domain invariants; do not write converters for types Spring Boot already supports.
7. Register converters with `@ConfigurationPropertiesBinding` when they are solely for binding.
8. Validate values after conversion, especially timeouts, retry delays, file sizes, and resource limits.
9. Test suffixes, bare numbers, defaults, external overrides, and invalid inputs.
10. Verify the client actually applies the bound values; having the right type does not guarantee the transport is configured properly.

## 14. Practice Exercises

**Exercise 1 — Duration.** Declare `connect-timeout` as `250ms`, `read-timeout` as `2s`, and `polling-interval` as bare `15` with `@DurationUnit(ChronoUnit.SECONDS)`. Write a test asserting all three values after binding.

**Exercise 2 — DataSize.** Declare `max-file-size` as `32MB` and `cache-size` as bare `256` with `@DataSizeUnit(DataUnit.MEGABYTES)`. Convert both to bytes and explain why bare numbers do not default to megabytes.

**Exercise 3 — Custom Converter.** Create a `RegionCode` or `TenantId` value object, write a `Converter<String, T>`, and register it with `@ConfigurationPropertiesBinding`. Test valid values, whitespace, uppercase input, and invalid formats.

**Exercise 4 — Validation.** Enforce that timeouts must be greater than 0 and response sizes stay within a chosen limit. Separate conversion error tests from validation error tests.

**Exercise 5 — Configuration Sources.** Set `read-timeout` in YAML, an environment variable, and a command-line argument. Identify which value wins and verify the `@ConfigurationProperties` bean receives the expected `Duration`.

**Exercise 6 — Client Integration.** Pass `Duration` into HTTP client settings and `DataSize` into response limits. Write a test or integration test proving the transport enforces those limits—not just that the binder converts them.

## 15. Key Takeaways and References

- `Duration` represents time intervals; bare numbers default to milliseconds.
- `DataSize` represents data capacities; bare numbers default to bytes.
- `@DurationUnit` and `@DataSizeUnit` change the default unit for bare numbers; explicit suffixes still specify units directly.
- Spring Boot provides built-in conversions for common types; do not manually parse `Duration` or `DataSize`.
- For domain-specific types, use `Converter<String, T>` and register via `@ConfigurationPropertiesBinding` when the converter is meant for configuration binding.
- Type conversion does not replace validation. Zero timeouts or negative file sizes may need to be rejected per application rules.
- `@ConfigurationProperties` only binds values; clients and transports must actively apply them.
- When configuration comes from Spring Cloud Config or external sources, check the winning property source and test runtime values.

Official resources for checking against your project's Spring Boot/Spring Cloud version:

1. [Spring Boot Reference – Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
2. [Spring Boot Reference – Duration Conversion](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion)
3. [Spring Boot Reference – DataSize Conversion](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion)
4. [Spring Boot API – `DurationUnit`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/convert/DurationUnit.html)
5. [Spring Boot API – `DataSizeUnit`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/convert/DataSizeUnit.html)
6. [Spring Boot API – `ConfigurationPropertiesBinding`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBinding.html)
7. [Spring Framework Reference – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
8. [Spring Cloud – release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
