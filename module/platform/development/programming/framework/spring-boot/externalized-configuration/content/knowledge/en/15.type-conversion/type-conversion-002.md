# Converting Strings to Numbers, Booleans, Enums, and Standard Types in Spring Boot

Spring Boot lets you provide configuration from `application.properties`, `application.yml`, environment variables, Java system properties, command-line arguments, and many other sources. These values are usually represented as text, while Java code needs explicit data types such as `int`, `boolean`, `BigDecimal`, `Duration`, `URI`, or enums.

When using `@ConfigurationProperties`, the Spring Boot **Configuration Binder** not only looks up properties by name but also converts source values into their corresponding Java types. As a result, a service can receive a typed configuration object instead of manually calling `Integer.parseInt(...)`, `Boolean.parseBoolean(...)`, or scattering conversion logic around.

For example:

~~~properties
app.client.max-connections=12
app.client.enabled=true
app.client.mode=ACTIVE
app.client.connect-timeout=3s
app.client.endpoint=https://api.example.org
~~~

This can bind to a record containing `int maxConnections`, `boolean enabled`, `ClientMode mode`, `Duration connectTimeout`, and `URI endpoint`.

This lesson uses Spring Boot 3.3.x and Java 21; it explains common conversion groups, how to declare them in YAML/properties/environment variables, conversion errors, validation, and testing.

## 1. Distinguishing Property Names, Type Conversion, and Validation

When reading a property, there are typically three distinct concerns:

1. **Property lookup:** selecting the effective value of `app.client.max-connections` across `PropertySource`s.
2. **Type conversion:** turning the text `"12"` into a Java `int` value.
3. **Validation:** verifying that `12` satisfies business rules, such as greater than 0 and less than 1000.

For example:

~~~properties
app.client.max-connections=abc
~~~

If Java requires `int`, the value cannot be converted into a normal integer. This is a **conversion/binding** error.

~~~properties
app.client.max-connections=-3
~~~

`-3` converts to `int`, but it may violate a `@Min(1)` business constraint. This is a **validation** error, not a numeric syntax error.

Another issue:

~~~yaml
app:
  client:
    max-connetions: 12
~~~

The name `max-connetions` is misspelled compared to `max-connections`. The binder may not find the property; for a primitive `int`, the resulting value may stay `0` without an error. This case is not the same as failing to convert `"abc"` to a number.

Diagram:

~~~text
Properties / YAML / Environment / CLI
                 |
                 v
     Environment + PropertySource
                 |
                 v
       @ConfigurationProperties Binder
                 |
                 +-- name lookup (relaxed binding)
                 +-- select effective value
                 +-- convert to Java type
                 +-- construct object/nested object
                 +-- validation if enabled
                 |
                 v
              Service
~~~

The binder has common built-in converters, but it does not automatically understand every format or every application-defined business type.

## 2. Building a Multi-Type Example in One Record

Create the enum:

~~~java
package com.example.configdemo.config;

public enum ClientMode {
    ACTIVE,
    PASSIVE,
    MAINTENANCE
}
~~~

Create `ClientProperties.java`:

~~~java
package com.example.configdemo.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        int maxConnections,
        boolean enabled,
        ClientMode mode,
        Duration connectTimeout,
        URI endpoint) {
}
~~~

File `src/main/resources/application.yml`:

~~~yaml
app:
  client:
    max-connections: 12
    enabled: true
    mode: ACTIVE
    connect-timeout: 3s
    endpoint: https://api.example.org
~~~

Register the configuration class in the application:

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

With the `com.example.configdemo.config` package under the application package, `@ConfigurationPropertiesScan` locates the record. You can also substitute `@EnableConfigurationProperties(ClientProperties.class)` when explicit registration is desired.

Create a bean that reads the configuration:

~~~java
package com.example.configdemo;

import com.example.configdemo.config.ClientProperties;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClientSettingsPrinter {

    @Bean
    ApplicationRunner showSettings(ClientProperties properties) {
        return args -> {
            System.out.println("connections=" + properties.maxConnections());
            System.out.println("enabled=" + properties.enabled());
            System.out.println("mode=" + properties.mode());
            System.out.println("timeout=" + properties.connectTimeout());
            System.out.println("endpoint=" + properties.endpoint());
        };
    }
}
~~~

Output:

~~~text
connections=12
enabled=true
mode=ACTIVE
timeout=PT3S
endpoint=https://api.example.org
~~~

`PT3S` is the ISO-8601 representation of `Duration.ofSeconds(3)`. The output assumes no higher-precedence source overrides the keys in YAML.

## 3. Integers: int, long, short, and BigInteger

Some Java integer types:

| Type | Typical Value Range |
| --- | --- |
| `byte` | -128 to 127 |
| `short` | -32,768 to 32,767 |
| `int` | -2,147,483,648 to 2,147,483,647 |
| `long` | Approximately ±9.22 × 10^18 |
| `BigInteger` | Arbitrary-precision integers within resource limits |

Configuration example:

~~~properties
app.limits.retry-count=4
app.limits.worker-count=16
app.limits.total-records=9000000000
app.limits.external-id=123456789012345678901234567890
~~~

Record:

~~~java
package com.example.configdemo.config;

import java.math.BigInteger;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.limits")
public record LimitProperties(
        int retryCount,
        short workerCount,
        long totalRecords,
        BigInteger externalId) {
}
~~~

The binder converts numeric strings into their respective types. For instance, `9000000000` does not fit in `int` but fits in `long`.

### Out-of-Range Values

~~~properties
app.limits.worker-count=40000
~~~

`40000` exceeds the range of `short`. If the target type is `short`, conversion can fail. You should not replace every field with `long` just to dodge errors; choose the type based on real scale and place validation on the business range.

### Non-Numeric Values

~~~properties
app.limits.retry-count=four
~~~

The string `four` is not standard integer syntax. During binding, an error may occur with a root cause such as `NumberFormatException` or `ConversionFailedException`, wrapped by bind/configuration-properties exceptions.

Write numbers consistently:

~~~properties
app.limits.total-records=1000000
~~~

Do not write locale-formatted thousands separators like `1.000.000` when a property expects an integer.

### Strings with Leading Zeros

Postal codes, account numbers, customer codes, or item SKUs like `00123` are not numeric quantities. Use `String` and write:

~~~yaml
app:
  customer:
    code: "00123"
~~~

Do not bind to `int` and expect leading zeros to be preserved.

## 4. Decimals: float, double, and BigDecimal

Example:

~~~properties
app.price.discount-rate=0.125
app.price.base-amount=199.95
app.price.max-ratio=1.5
~~~

Record:

~~~java
package com.example.configdemo.config;

import java.math.BigDecimal;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.price")
public record PriceProperties(
        double discountRate,
        BigDecimal baseAmount,
        float maxRatio) {
}
~~~

`float` and `double` are binary floating-point types that cannot represent every decimal fraction exactly. For currency amounts, taxes, or calculations requiring base-10 precision, `BigDecimal` is generally more appropriate.

Example:

~~~java
BigDecimal tax = properties.baseAmount()
        .multiply(new BigDecimal("0.10"));
~~~

Do not default to `new BigDecimal(0.1)` if the goal is the exact decimal value `0.1`; the `double` literal may already carry representation error.

Use a decimal point in numeric configuration:

~~~properties
app.price.discount-rate=0.125
~~~

A locale-formatted string like `0,125` should not be assumed valid across all configuration converters. If real data sources require a different locale, the application should design an explicit converter/formatter.

## 5. Converting Strings to boolean

Common example:

~~~properties
app.feature.enabled=true
app.feature.audit=false
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.feature")
public record FeatureProperties(
        boolean enabled,
        boolean audit) {
}
~~~

`true` and `false` are the preferred spellings. They are unambiguous and portable across config files, environment variables, and CI/CD pipelines.

Spring Framework includes a String-to-Boolean converter that supports other familiar representations such as `on/off`, `yes/no`, or `1/0` in appropriate contexts. However, avoid relying on unnecessary variations in operational configuration. In particular, a value like `maybe` is not a valid boolean.

### Why Not Call Boolean.parseBoolean Manually?

Example:

~~~java
boolean enabled = Boolean.parseBoolean(
        environment.getProperty("app.feature.enabled"));
~~~

This Java method handles unrecognized values differently from Spring's converter. When input syntax is wrong, manual parsing can hide the error as `false` instead of detecting misconfiguration.

With `@ConfigurationProperties`, the binder attempts to convert to the requested type and can report an error when a boolean string is invalid. That is usually better behavior when strict configuration is required.

### boolean and Boolean Differ When Configuration Is Missing

~~~java
boolean enabled
Boolean enabled
~~~

Primitive `boolean` cannot be `null`; when a property is missing on an instantiated object, it can become `false`. Wrapper `Boolean` can hold `null` to represent absence.

If operators **must explicitly choose on or off**, use:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.audit")
public record AuditProperties(
        @NotNull Boolean enabled) {
}
~~~

When using this snippet, import `org.springframework.validation.annotation.Validated` and `jakarta.validation.constraints.NotNull`, and include a Bean Validation provider. When absence is allowed to default to off, you can use `@DefaultValue("false") boolean`.

## 6. Converting Strings to Enum

Enums restrict a choice to a defined set of values. Example:

~~~java
package com.example.configdemo.config;

public enum ProcessingMode {
    SYNC,
    ASYNC,
    MAINTENANCE
}
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.processing")
public record ProcessingProperties(
        ProcessingMode mode) {
}
~~~

Configuration:

~~~yaml
app:
  processing:
    mode: ASYNC
~~~

The binder turns `ASYNC` into `ProcessingMode.ASYNC`. Services can rely on the enum rather than manual string comparisons:

~~~java
switch (settings.mode()) {
    case SYNC -> processNow();
    case ASYNC -> queueForLater();
    case MAINTENANCE -> pauseProcessing();
}
~~~

The three methods above represent business logic defined by the application itself.

With the value:

~~~properties
app.processing.mode=UNKNOWN
~~~

if the enum has no `UNKNOWN` constant, the binder cannot produce a matching enum value and can report a conversion error. The Java string `"UNKNOWN"` is still a valid `String`, but a nonexistent enum value is an invalid choice configuration.

Spring Boot supports convenient enum conversion for configuration, though the clearest practice is to **write the exact enum constant name** such as `SYNC`, `ASYNC`, and `MAINTENANCE`. Relaxed binding of **property names** does not mean arbitrary display labels automatically become valid enum constants.

### Default Enum Value

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.processing")
public record ProcessingProperties(
        @DefaultValue("SYNC") ProcessingMode mode) {
}
~~~

When `app.processing.mode` is absent, the binder can select `SYNC`. If an operator supplies `MAINTENANCE`, the provided property overrides the default.

## 7. Standard Java Types That Can Bind from Strings

Beyond numbers, booleans, and enums, many standard types are supported via Spring and Spring Boot converters.

| Target Type | Configuration Example | Meaning |
| --- | --- | --- |
| `String` | `warehouse-service` | Names and identifiers |
| `URI` | `https://api.example.org/v1` | Resource address |
| `URL` | `https://example.org` | URL object |
| `Path` | `/var/app/data` | Filesystem path |
| `File` | `/var/app/result.csv` | File object |
| `InetAddress` | `127.0.0.1` | IP address/hostname |
| `Charset` | `UTF-8` | Character encoding |
| `Locale` | `en_US` | Language/region |
| `UUID` | `123e4567-e89b-12d3-a456-426614174000` | Unique identifier |
| `Duration` | `3s` | Time duration |
| `Period` | `2w` | Calendar-based period |
| `DataSize` | `10MB` | Data capacity |

Some types depend on an appropriate converter or context-specific interpretation; `Duration`, `Period`, and `DataSize` have dedicated Spring Boot support in Configuration Properties.

### URI Example

~~~java
import java.net.URI;

@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(URI endpoint) {
}
~~~

With:

~~~yaml
app:
  remote:
    endpoint: https://api.example.org
~~~

The binder can construct a `URI` object. However, a syntactically valid `URI` **does not guarantee** that the server exists, DNS works, TLS is trusted, or the path is accessible.

If the application requires HTTPS, check explicitly:

~~~java
if (!"https".equalsIgnoreCase(properties.endpoint().getScheme())) {
    throw new IllegalArgumentException("HTTPS endpoint is required");
}
~~~

This is business validation, not a built-in step of converting a `String` to a `URI`.

### Path Example

~~~java
import java.nio.file.Path;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(Path outputDir) {
}
~~~

~~~yaml
app:
  storage:
    output-dir: /var/app/output
~~~

`Path` only represents a path location. Converting to `Path` does not create the directory, verify read/write permissions, or prove the file exists. If needed, the application uses `Files.exists(...)`, `Files.createDirectories(...)`, or suitable checks before processing data.

Relative paths generally depend on the working directory of the Java process.

## 8. Duration: Time Strings and Units

Spring Boot has dedicated support for `java.time.Duration` in three forms:

1. A plain integer without a unit, defaulting to **milliseconds** unless `@DurationUnit` is declared.
2. ISO-8601 syntax such as `PT30S`.
3. A numeric string with a suffix such as `500ms`, `3s`, or `2m`.

Example:

~~~yaml
app:
  timeout:
    connect: 500ms
    read: 3s
    idle: 2m
    absolute: PT30S
~~~

Record:

~~~java
package com.example.configdemo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.timeout")
public record TimeoutProperties(
        Duration connect,
        Duration read,
        Duration idle,
        Duration absolute) {
}
~~~

Result:

~~~text
connect  = 500 milliseconds
read     = 3 seconds
idle     = 2 minutes
absolute = 30 seconds
~~~

Suffix table:

| Suffix | Unit |
| --- | --- |
| `ns` | Nanoseconds |
| `us` | Microseconds |
| `ms` | Milliseconds |
| `s` | Seconds |
| `m` | Minutes |
| `h` | Hours |
| `d` | Days |

### Unitless Number Pitfall

~~~properties
app.timeout.read=30
~~~

With `Duration read`, this value typically corresponds to **30 milliseconds**, not 30 seconds. This is a common mistake when migrating from `long readTimeoutSeconds` to `Duration readTimeout` while keeping `30` in the file.

### @DurationUnit

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "app.timeout")
public record TimeoutProperties(
        @DurationUnit(ChronoUnit.SECONDS) Duration read) {
}
~~~

With this annotation, `app.timeout.read=30` is interpreted in seconds. Even so, `30s` in YAML is usually easier to understand and less error-prone because the unit sits right next to the value.

## 9. DataSize: Capacity with Units

Spring Framework provides `org.springframework.util.unit.DataSize`. Spring Boot supports values such as:

~~~properties
app.upload.max-size=20MB
app.upload.memory-buffer=512KB
app.upload.chunk-size=1024B
~~~

Record:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        DataSize maxSize,
        DataSize memoryBuffer,
        DataSize chunkSize) {
}
~~~

To work with the byte count, use:

~~~java
long bytes = properties.maxSize().toBytes();
~~~

Supported units include `B`, `KB`, `MB`, `GB`, `TB`. If a `DataSize` property contains only a number without a suffix, the default unit is **bytes** unless `@DataSizeUnit` is present.

Example:

~~~properties
app.upload.max-size=10
~~~

Do not interpret this as 10 MB; by default it is 10 bytes.

### @DataSizeUnit

~~~java
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        @DataSizeUnit(DataUnit.MEGABYTES) DataSize maxSize) {
}
~~~

Then the string `10` can be interpreted as 10 megabytes. To minimize confusion in operations, configuring `10MB` is still usually clearer.

`DataSize` does not replace business limit checks. For instance, a max upload of 0 bytes may be invalid while still being a properly typed `DataSize` value.

## 10. Period: Calendar-Based Intervals

`Duration` measures in seconds/nanoseconds; `Period` measures in years, months, and days and fits calendar rules.

Example:

~~~properties
app.retention.short=2w
app.retention.archive=1y3d
app.retention.monthly=P1M
~~~

Record:

~~~java
import java.time.Period;

@ConfigurationProperties(prefix = "app.retention")
public record RetentionProperties(
        Period shortPeriod,
        Period archive,
        Period monthly) {
}
~~~

If the property name differs from the component name, keep them consistent under relaxed binding—for example `short-period` with `shortPeriod`. In the exercise above, you can change the key `app.retention.short` to `app.retention.short-period` if the record declares `shortPeriod`; what matters is that the paths match.

Suffixes `y` (years), `m` (months), `w` (weeks), `d` (days) are used in `Period`'s short format. `2w` equals 14 days in `Period`.

**Watch out:** the `m` suffix in `Period` means **months**, whereas `m` in `Duration` means **minutes**. The target Java type determines the interpretation. Do not convert a `Period` into a fixed number of seconds if month/year semantics must be preserved, since calendar lengths vary.

## 11. Nested Parameters and Conversion in a Large Object

An application may have configuration such as:

~~~yaml
app:
  pipeline:
    mode: ASYNC
    enabled: true
    worker-count: 8
    output-path: /var/app/result
    retry:
      max-attempts: 4
      delay: 250ms
~~~

Record:

~~~java
package com.example.configdemo.config;

import java.nio.file.Path;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.pipeline")
public record PipelineProperties(
        ProcessingMode mode,
        boolean enabled,
        int workerCount,
        Path outputPath,
        Retry retry) {

    public record Retry(
            int maxAttempts,
            Duration delay) {
    }
}
~~~

The binder binds and converts:

~~~text
ASYNC             → ProcessingMode.ASYNC
true              → boolean true
8                 → int 8
/var/app/result   → Path
4                 → int 4
250ms             → Duration.ofMillis(250)
~~~

`Retry` is a nested object. If all of `app.pipeline.retry` is absent, the nested object can be `null` under constructor binding. That is a **missing configuration structure** issue rather than a per-field conversion error.

If the `retry` group must exist, use `@NotNull`/`@Valid` when validation is enabled. If it may be omitted while still wanting a default object, Spring Boot supports an argument-less `@DefaultValue` on the nested component combined with valid defaults on its child components.

## 12. Default Values and Target Types

For constructor binding and records, Spring Boot supports:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.scheduler")
public record SchedulerProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("4") int workers,
        @DefaultValue("3s") Duration interval,
        @DefaultValue("ASYNC") ProcessingMode mode) {
}
~~~

When a property is not found, the binder takes the `@DefaultValue` string and converts it to the proper Java type.

If YAML supplies:

~~~yaml
app:
  scheduler:
    workers: 10
~~~

the result can be:

~~~text
enabled  = true
workers  = 10
interval = PT3S
mode     = ASYNC
~~~

Limitations to remember:

- `@DefaultValue` only applies when the binder **does not find** the corresponding property.
- A property that exists but is empty or malformed is not automatically replaced with the default.
- The string in the annotation must be a constant; property placeholders like `${APP_INTERVAL:3s}` are not supported inside `@DefaultValue`.
- A default may convert successfully yet still be invalid from a business standpoint, such as a negative worker count.

For required fields, do not set fake defaults just so the application always starts; use wrapper types together with appropriate validation.

## 13. Conversion Errors Differ from Validation

Consider:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.pool")
public record PoolProperties(
        @NotNull @Min(1) @Max(64) Integer size) {
}
~~~

Imports:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.validation.annotation.Validated;
~~~

With `spring-boot-starter-validation` or a compatible provider present.

Scenarios:

| Input | Conversion | Validation |
| --- | --- | --- |
| `size=8` | Becomes `Integer 8` | Valid |
| `size=0` | Becomes `Integer 0` | Violates `@Min(1)` |
| `size=100` | Becomes `Integer 100` | Violates `@Max(64)` |
| `size=abc` | Cannot convert to a normal `Integer` | Never reaches numeric validation |
| Missing `size` | Can be `null` | Violates `@NotNull` |

With primitive `int`, a missing value can show up as `0`, making it impossible to distinguish "property omitted" from "user explicitly wrote `0`" from the bound object alone. `Integer` + `@NotNull` clearly expresses the contract that the property must be supplied.

In real applications, a bind failure may appear as `ConfigurationPropertiesBindException`, `BindException`, or another wrapping exception depending on version. Read the root cause to see whether the issue is in the property name, input string, target type, or constraint.

### Booleans and Business Rules

`@NotNull Boolean auditEnabled` requires deployers to choose `true` or `false`. `false` is still a valid choice; do not attach a "must be true" check if the business contract only requires an explicit decision.

### URIs and Validation

A URI with the `http` scheme can still convert into a valid `URI`. If the application mandates HTTPS, a separate rule is required. Do not treat successful conversion as proof of connectivity or security.

## 14. Common Mistakes When Converting Strings

### Out-of-Range Number Error

~~~properties
app.client.max-connections=99999999999999999999
~~~

If using `int`, the number is too large. Choose a wider type when appropriate and validate the business range.

### Invalid Boolean Error

~~~properties
app.client.enabled=maybe
~~~

An arbitrary value that is not a recognized boolean can cause the binder to report an error. Change it to `true` or `false`.

### Nonexistent Enum Error

~~~properties
app.client.mode=SILENT
~~~

If the enum only has `ACTIVE`, `PASSIVE`, and `MAINTENANCE`, `SILENT` will not convert to a matching enum constant.

### Time Unit Error

~~~properties
app.timeout.read=30
~~~

If the field is `Duration`, the default is usually 30 milliseconds. To express 30 seconds, write `30s` or use `@DurationUnit(ChronoUnit.SECONDS)`.

### Data Size Unit Error

~~~properties
app.upload.max-size=10
~~~

For `DataSize`, a unitless value defaults to bytes. If you want 10 megabytes, write `10MB`.

### YAML Dropping Leading Zeros Error

~~~yaml
app:
  customer:
    code: 00123
~~~

If this is a customer code, write `code: "00123"` and bind to `String`. Do not use integer types for identifier data.

### Misspelled Property Name Error

~~~yaml
app:
  client:
    max-connetions: 12
~~~

The key `max-connetions` does not match `max-connections`. No conversion can fix an arbitrary typo in a property name. Property names, profiles, and configuration sources must be checked separately.

### Empty Property Error

~~~properties
app.client.max-connections=
~~~

An empty string is not necessarily treated the same as a missing property. The outcome depends on the target type and converter; it may become `null` or cause an error. If the property is required, use validation and write a test for this case.

## 15. Relaxed Binding Differs from Value Conversion

The following names can map to the same Java component `maxConnections` in appropriate sources:

~~~text
app.client.max-connections
app.client.maxConnections
APP_CLIENT_MAXCONNECTIONS
~~~

This is **relaxed binding of names**, not converting `"12"` to `int`.

Common rule for converting a canonical property name to an environment variable:

1. Replace dots `.` with underscores `_`.
2. Remove hyphens `-`.
3. Convert to uppercase.

Examples:

~~~text
app.client.max-connections → APP_CLIENT_MAXCONNECTIONS
app.client.connect-timeout → APP_CLIENT_CONNECTTIMEOUT
~~~

Run:

~~~bash
export APP_CLIENT_MAXCONNECTIONS=24
java -jar config-demo.jar --app.client.enabled=false
~~~

The binder can take `24` from the environment variable and `false` from CLI, then convert them to `int` and `boolean`. `@ConfigurationProperties` itself does not change `PropertySource` precedence.

### Watch Out for Map Key Names

When binding a `Map<String,String>` from environment variables, Spring Boot normalizes variable names to lowercase before processing map keys. For example, `MY_PROPS_VALUES_KEY=VALUE` typically produces key `key` with value `VALUE`. This is a `Map` key naming rule, **not** lowercasing of the value.

If business key names must preserve uppercase letters, choose a suitable source such as YAML with bracket notation or separately parsed JSON data.

## 16. @Value and Environment Also Have Type Conversion

`@Value` can inject a single property:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class TimeoutConsumer {

    private final Duration timeout;

    public TimeoutConsumer(
            @Value("${app.client.connect-timeout:3s}") Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Spring can convert the value for the injection point; however, `@Value` does not have the same full metadata, object structuring, and relaxed binding capabilities as `@ConfigurationProperties`.

`Environment` also supports typed queries:

~~~java
Integer connections = environment.getProperty(
        "app.client.max-connections", Integer.class);

Boolean enabled = environment.getProperty(
        "app.client.enabled", Boolean.class);
~~~

If a property does not exist, `getProperty` can return `null`. For a large group with nested objects and validation, `@ConfigurationProperties` is usually clearer and easier to maintain.

A less suitable pattern when scattered everywhere:

~~~java
int connections = Integer.parseInt(
        environment.getProperty("app.client.max-connections"));
~~~

If the property is missing, manual parsing can fail in business code. It is better to bind and validate configuration early during bootstrap.

## 17. Custom Converters for Application-Specific Business Types

For a custom Java type, Spring Boot cannot guess every conversion rule.

Suppose an application uses three-letter region codes:

~~~java
package com.example.configdemo.config;

public record RegionCode(String value) {
    public RegionCode {
        if (value == null || !value.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "Region must have three uppercase letters");
        }
    }
}
~~~

Converter:

~~~java
package com.example.configdemo.config;

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
~~~

Registering for configuration binding:

~~~java
package com.example.configdemo.config;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RegionConverterConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static StringToRegionCodeConverter regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

Then:

~~~java
@ConfigurationProperties(prefix = "app.shipping")
public record ShippingProperties(RegionCode region) {
}
~~~

~~~properties
app.shipping.region=vnm
~~~

The binder can use the converter to create `RegionCode("VNM")`.

Converters for configuration properties may be invoked by Spring Boot **very early** in the application lifecycle. Avoid depending on uninitialized beans or network calls. Do not create a custom converter merely for an enum or plain `int` that is already supported out of the box.

## 18. Testing Conversions with ApplicationContextRunner

`ApplicationContextRunner` creates a small context and lets you supply properties in tests.

Example:

~~~java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import com.example.configdemo.config.ClientMode;
import com.example.configdemo.config.ClientProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BindingConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class BindingConfiguration {
    }

    @Test
    void bindsTypedValues() {
        runner.withPropertyValues(
                "app.client.max-connections=12",
                "app.client.enabled=true",
                "app.client.mode=ACTIVE",
                "app.client.connect-timeout=3s",
                "app.client.endpoint=https://api.example.org")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    ClientProperties props =
                            context.getBean(ClientProperties.class);

                    assertThat(props.maxConnections()).isEqualTo(12);
                    assertThat(props.enabled()).isTrue();
                    assertThat(props.mode()).isEqualTo(ClientMode.ACTIVE);
                    assertThat(props.connectTimeout())
                            .isEqualTo(Duration.ofSeconds(3));
                    assertThat(props.endpoint()).isEqualTo(
                            URI.create("https://api.example.org"));
                });
    }

    @Test
    void invalidIntegerFails() {
        runner.withPropertyValues(
                "app.client.max-connections=many",
                "app.client.enabled=true",
                "app.client.mode=ACTIVE",
                "app.client.connect-timeout=3s",
                "app.client.endpoint=https://api.example.org")
                .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void unknownEnumFails() {
        runner.withPropertyValues(
                "app.client.max-connections=12",
                "app.client.enabled=true",
                "app.client.mode=UNKNOWN",
                "app.client.connect-timeout=3s",
                "app.client.endpoint=https://api.example.org")
                .run(context -> assertThat(context).hasFailed());
    }
}
~~~

The snippet above assumes the project includes `spring-boot-starter-test`, JUnit Jupiter, and AssertJ. `ClientProperties` is registered via `@EnableConfigurationProperties` in the test context.

Conversion tests and validation tests should be kept as separate groups. For example, `max-connections=-5` still converts to `int`, but will be rejected when `@Min(1)` and Bean Validation are added.

## 19. Runtime Diagnostics

You can create an `ApplicationRunner` to inspect bound values:

~~~java
@Bean
ApplicationRunner inspectSettings(ClientProperties props) {
    return args -> {
        System.out.println("mode=" + props.mode());
        System.out.println("connections=" + props.maxConnections());
        System.out.println("timeoutSeconds="
                + props.connectTimeout().toSeconds());
    };
}
~~~

Place the method in a `@Configuration` or `@SpringBootApplication` class, and import `org.springframework.context.annotation.Bean` and `org.springframework.boot.ApplicationRunner`.

To test overriding:

~~~bash
java -jar config-demo.jar --app.client.max-connections=20
~~~

To trigger an intentional error:

~~~bash
java -jar config-demo.jar --app.client.max-connections=not-a-number
~~~

When inspecting the stack trace, look for the property name, source value, target Java type, and root cause. Do not look only at the outer wrapper exception.

If the application uses Spring Boot Actuator, the `env` and `configprops` endpoints can help inspect configuration when enabled and properly secured. Do not expose secrets through diagnostic logs or endpoints.

## 20. Guidelines for Choosing Data Types

| Need | Common Appropriate Type | Example |
| --- | --- | --- |
| Retry count | `int`/`Integer` | `retries=3` |
| Very large counts | `long` | `records=9000000000` |
| Currency | `BigDecimal` | `amount=199.95` |
| On/off toggle | `boolean`/`Boolean` | `enabled=true` |
| Fixed set of modes | `enum` | `mode=ASYNC` |
| Resource address | `URI` | `endpoint=https://example.org` |
| File location | `Path` | `dir=/var/app/data` |
| Wait duration | `Duration` | `timeout=3s` |
| Calendar interval | `Period` | `retention=2w` |
| Size limit | `DataSize` | `size=10MB` |
| Code needing leading zeros | `String` | `code="00123"` |
| List | `List<String>` | `regions=[vn,sg]` |
| Dynamic keys | `Map<String,String>` | `labels.team=platform` |

Do not pick primitives just for brevity if the application must know whether a property is present. Do not pick `String` for every field if you want type validation and readable Java logic.

## 21. Practice Exercises

### Exercise 1 — Integers

Given `demo.worker.count=8` and `demo.worker.max-items=120000`. Create `WorkerProperties(int count, long maxItems)` with prefix `demo.worker`. Expected values: `8` and `120000`.

### Exercise 2 — Required Boolean

Configure `demo.feature.enabled=false`. If the user must explicitly choose on or off, use `@NotNull Boolean enabled` and `@Validated`; explain why `false` is valid whereas `null` must be rejected.

### Exercise 3 — Enum

Create enum `LogMode { SIMPLE, VERBOSE }`. Bind `demo.log.mode=VERBOSE` to `LogMode`. Try `demo.log.mode=QUIET` when there is no `QUIET` constant and observe the error.

### Exercise 4 — Duration

With `Duration read`, how many seconds does `demo.timeout.read=2000` mean when there is no `@DurationUnit`? **Answer:** 2 seconds, because the default unit is milliseconds.

### Exercise 5 — DataSize

With `DataSize maxUpload`, set `demo.file.max-upload=10MB`. Use `maxUpload.toBytes()`. Explain why `10MB` is clearer than a bare `10` without a suffix.

### Exercise 6 — Conversion and Validation

Compare `demo.pool.size=abc` with `demo.pool.size=-2` when the field is `int` with `@Min(1)`. The first fails to parse as a number; the second parses as a number but violates the constraint.

### Exercise 7 — Custom Converter

Create `RegionCode` and a converter that normalizes `vnm` to `VNM`, registered with `@ConfigurationPropertiesBinding`. Bind `demo.region=vnm`.

### Exercise 8 — Preserving Identifiers

Store customer code `00123` in YAML and choose the Java type. **Answer:** use `"00123"` in YAML and `String` in Java.

### Exercise 9 — CLI Override

`application.yml` declares `app.client.max-connections: 10`. Run with `--app.client.max-connections=25`. The binder uses `25` assuming no higher-precedence source is present.

### Exercise 10 — URI

Bind `https://api.example.org` to `URI`, then explain why you still need to check scheme, host, connectivity, and permissions according to business requirements.

## 22. Key Takeaways

- `@ConfigurationProperties` lets the binder convert configuration values from sources into Java types without parsing strings in every service.
- Distinguish **property names** (relaxed binding), **value conversion** (conversion), and **validity rules** (validation).
- Use `int`/`long` for integers, `BigDecimal` for decimals needing precision, `boolean` for toggles, and enums for fixed sets of options.
- For missing values, primitives can mask issues as `0`/`false`; wrapper types with `@NotNull` help verify presence when required.
- `URI` and `Path` express data clearly but do not automatically verify network reachability or filesystem state.
- Suffixless `Duration` defaults to milliseconds; suffixless `DataSize` defaults to bytes. Use explicit suffixes or `@DurationUnit`/`@DataSizeUnit`.
- `Period` serves calendar units and is not the same as `Duration`.
- `@DefaultValue` applies when a property is missing and its value is converted to the target type; it does not automatically replace malformed values or replace validation.
- For custom business types, you can supply a custom converter via `@ConfigurationPropertiesBinding`.
- Test valid values, missing properties, unconvertible strings, out-of-range numbers, and business constraints.

## References

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Properties Conversion](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion)
- [Spring Boot 3.3 — Converting Durations](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion.durations)
- [Spring Boot 3.3 — Converting Data Sizes](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion.data-sizes)
- [Spring Boot 3.3 — Configuration Properties Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Framework — ConversionService](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/convert/ConversionService.html)