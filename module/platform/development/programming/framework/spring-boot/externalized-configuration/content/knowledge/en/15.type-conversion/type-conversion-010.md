# Diagnosing Invalid Formats, Wrong Units, and Out-of-Range Values in Spring Boot 3.3

## 1. Problem: Property Exists Yet Fails to Bind, or Binds Cleanly and Runs Wrong

Spring Boot lets you declare configuration in `application.properties`, `application.yaml`, environment variables, Java system properties, and command-line arguments. When mapping those values to `@ConfigurationProperties` beans, the `Binder` must **read property names**, **choose the effective source**, **convert types**, and **check constraints** if validation is enabled.

Not all configuration failures look alike. Three categories must be distinguished:

1. **Invalid format or wrong input type:** for example, `app.max-retries=three` for `int`, `app.enabled=perhaps` for `boolean`, or `app.timeout=soon` for `Duration`.
2. **Wrong unit:** the value binds cleanly yet carries the wrong meaning—for instance, `app.timeout=10` interpreted as **10 milliseconds** when the operator wanted 10 seconds, or `app.buffer-size=10` interpreted as **10 bytes** when 10 MB was intended.
3. **Out of valid range:** the value may not fit in the Java type (`int` overflow, `Duration`/`DataSize` beyond conversion limits), or it fits the Java type yet **violates application policy** (`retry-count=-1`, `worker-count=0` when at least one worker is required, `timeout=-5s` when negative durations are disallowed).

**Key takeaway:** *parseable* does not mean *right unit*; *bound successfully* does not mean *valid for business rules*. Diagnostics must answer three questions independently: **where did the effective value come from, what type and unit was it interpreted as, and does it fall within the allowed range?**

Brief example:

```properties
app.max-retries=0
app.timeout=10
app.buffer-size=10
app.enabled=false
```

If the Java model declares `int`, `Duration`, `DataSize`, and `boolean`, all four values can bind cleanly:

- `maxRetries = 0`: valid by type; whether disabling retries is allowed depends on business rules.
- `timeout = Duration.ofMillis(10)`: **not 10 seconds** unless `@DurationUnit` specifies otherwise.
- `bufferSize = DataSize.ofBytes(10)`: **not 10 MB** unless `@DataSizeUnit` specifies otherwise.
- `enabled = false`: an explicitly set value, not an absent property.

The question "why is the application misbehaving?" sometimes produces no exception at all, because a unit mistake can still be completely valid syntactically.

## 2. Diagnostic Flow from Text to Runtime

High-level model:

```text
application.yaml / .properties / CLI / -D / OS environment
                |
                v
     Spring Environment + PropertySource order
                |
                v
     Canonical / relaxed-binding property name
                |
                v
     Effective value (often text)
                |
                v
     ConversionService / Binder:
       String -> int, boolean, enum, Duration,
                 Period, DataSize, URI, ...
                |
      +---------+-----------+
      |                     |
      v                     v
 Conversion fails       Conversion succeeds
      |                     |
      v                     v
 Bind/conversion error     @Validated / Bean Validation
                            |
                 +----------+---------+
                 |                    |
                 v                    v
           Constraint error     Valid configuration bean
                                      |
                                      v
                           Business logic consumes value
```

Error classes may show up as `BindException`, `ConversionFailedException`, `IllegalArgumentException`, `NumberFormatException`, constraint validation errors, or `ConfigurationPropertiesBindException` at startup. **The exact exception name varies with the binding path, target type, and cause chain.** Never grep for a single exception class name and draw sweeping conclusions.

### Common Symptom Pattern

When a configuration bean fails to bind, Spring Boot may display a failure analysis like:

```text
APPLICATION FAILED TO START

Description:
Failed to bind properties under 'app.max-retries' to int:

    Property: app.max-retries
    Value: "not-a-number"
    Origin: class path resource [application.properties] - ...
    Reason: failed to convert java.lang.String to int

Action:
Update your application's configuration
```

This is an **illustrative message layout**, not byte-for-byte output across all versions. The useful fields to extract from logs are:

| Field | What Information to Extract? |
| --- | --- |
| `Property` | Final property name being bound |
| `Value` | Input value causing the error; may be masked/sanitized |
| `Origin` | File/line/column source when the source supplies origin info |
| `Reason` | Specific conversion or constraint failure |
| `Target type` | Actual Java type and binding target site |
| `Caused by` | Root cause when wrapper exceptions have multiple layers |

Not every source (especially env vars or custom `PropertySource`s) tracks line/column origins; missing `Origin` **does not prove the property did not exist**.

## 3. Complete Reference Configuration Example

Suppose a service has the configuration:

```properties
# src/main/resources/application.properties
app.max-retries=3
app.worker-count=4
app.request-timeout=5s
app.idle-timeout=30s
app.cache-size=16MB
app.retention=30d
app.enabled=true
app.region=ap-southeast-1
```

JavaBean using `@ConfigurationProperties`:

```java
package com.example.demo.config;

import java.time.Duration;
import java.time.Period;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.boot.convert.DurationUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;
import org.springframework.validation.annotation.Validated;

import java.time.temporal.ChronoUnit;

@Validated
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    @Min(0)
    @Max(10)
    private int maxRetries = 3;

    @Min(1)
    @Max(64)
    private int workerCount = 4;

    @NotNull
    private Duration requestTimeout = Duration.ofSeconds(5);

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration idleTimeout = Duration.ofSeconds(30);

    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize cacheSize = DataSize.ofMegabytes(16);

    private Period retention = Period.ofDays(30);

    private boolean enabled = true;

    @NotBlank
    private String region = "local";

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int value) { maxRetries = value; }

    public int getWorkerCount() { return workerCount; }
    public void setWorkerCount(int value) { workerCount = value; }

    public Duration getRequestTimeout() { return requestTimeout; }
    public void setRequestTimeout(Duration value) {
        requestTimeout = value;
    }

    public Duration getIdleTimeout() { return idleTimeout; }
    public void setIdleTimeout(Duration value) { idleTimeout = value; }

    public DataSize getCacheSize() { return cacheSize; }
    public void setCacheSize(DataSize value) { cacheSize = value; }

    public Period getRetention() { return retention; }
    public void setRetention(Period value) { retention = value; }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean value) { enabled = value; }

    public String getRegion() { return region; }
    public void setRegion(String value) { region = value; }
}
```

Registering the class:

```java
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
```

Validation dependency if the project lacks a provider:

```xml
<!-- pom.xml: when using Spring Boot dependency management -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

This example separates three concerns:

- **Java type** determines the convertible data representation.
- **Unit annotations** determine how numeric values **without a suffix** are interpreted.
- **Validation constraints** determine the application's valid domain range, e.g., retries from 0 to 10.

`@NotNull` on `Duration` catches null values after binding, yet **does not automatically enforce** positivity or an upper threshold. Add custom constraints/validation when business rules require them.

## 4. Invalid Integer Formats: Syntax, Type Range, and Business Range

A Java `int` property accepts integers within the range that `int` can represent.

Valid conversion examples:

```properties
app.max-retries=0
app.worker-count=8
```

Invalid format example:

```properties
app.max-retries=three
```

The binder cannot convert `"three"` to `int` using standard converters, so binding fails due to conversion/number format.

Out-of-type-range example for `int`:

```properties
app.max-retries=9999999999999999999999
```

That number cannot be represented in a 32-bit `int`; this is not merely a `@Max(10)` policy error. Type conversion fails **before** Bean Validation ever checks `@Max`.

Within `int` range yet exceeding business constraint:

```properties
app.max-retries=100
```

`100` parses as `int`, yet violates `@Max(10)` in the sample model. This is a **validation error**, distinct from a conversion error.

Business-valid boundary example:

```properties
app.max-retries=0
```

With `@Min(0)`, `0` is valid and can mean "no retries". Do not use `@Positive` if `0` is an intentional setting.

### Integer Classification Table

| Input `app.max-retries` | Converts to `int`? | Within `[0,10]`? | Assessment |
| --- | --- | --- | --- |
| `0` | Yes | Yes | Valid explicit value |
| `3` | Yes | Yes | Valid |
| `10` | Yes | Yes | Upper boundary value |
| `-1` | Yes | No | Violates `@Min(0)` constraint |
| `11` | Yes | No | Violates `@Max(10)` constraint |
| `three` | No | Not evaluated | Invalid format |
| `99999999999999999999` | No | Not evaluated | Outside `int` representable range |
| `3.5` | No under standard `String -> Integer` conversion | Not evaluated | Use a decimal type if needed |
| Empty string | May yield null/error depending on binding path and target type | Not treated as zero | Not equivalent to `0` |

**Distinguishing two kinds of "out of range":** exceeding the target type's capacity fails before or during conversion, whereas exceeding business bounds is caught only if the application declares validation or equivalent checks.

## 5. Booleans: false Is Valid, Unrecognized Words Can Fail

A property:

```java
private boolean enabled = true;
```

can receive:

```properties
app.enabled=false
```

For `boolean`, `false` overrides the initial `true` value. **This is not an error.**

However:

```properties
app.enabled=perhaps
```

is not a commonly supported boolean value and can cause a conversion error. Whether a converter accepts boolean aliases like `yes/no` or `on/off` depends on the source/converter; for consistent configuration, stick strictly to `true` and `false`.

Four cases to keep distinct:

- **Missing key:** a JavaBean can keep its initializer value; an uninitialized primitive defaults to `false` in Java.
- **`enabled=false`:** an explicit, valid selection.
- **`enabled=`:** an empty `String` at the source; does not automatically mean `false`.
- **`enabled=perhaps`:** not an unambiguous boolean value; can trigger a conversion error.

When you need to distinguish "not configured" from "turned off", use the `Boolean` wrapper with null/validation rules instead of inspecting a primitive `boolean` after binding.

## 6. Duration: Valid Formats, Units, and Subtle Discrepancies

`java.time.Duration` is for **time spans with length**, such as 750 milliseconds, 5 seconds, or 30 minutes. Spring Boot 3.3 supports:

1. Long integers without a suffix: default **milliseconds**, unless `@DurationUnit` is present.
2. ISO-8601 `Duration` strings, e.g., `PT5S`, `PT1M`.
3. Human-readable forms combining number and unit, e.g., `750ms`, `5s`, `2m`.

### 6.1. Supported Duration Suffixes

| Suffix | Meaning | Example |
| --- | --- | --- |
| `ns` | Nanoseconds | `500ns` |
| `us` | Microseconds | `100us` |
| `ms` | Milliseconds | `750ms` |
| `s` | Seconds | `5s` |
| `m` | Minutes | `2m` |
| `h` | Hours | `1h` |
| `d` | Days | `7d` |

The forms:

```properties
app.request-timeout=5s
app.request-timeout=PT5S
app.request-timeout=5000ms
```

are **three alternative ways** to express the same 5-second span for a `Duration` property. Never put all three lines for the same key in one real configuration file.

### 6.2. Wrong Unit Yet Still Parses Cleanly

```properties
app.request-timeout=5
```

On a `Duration` property without `@DurationUnit`, `5` means **5ms**, not 5s. This mistake may raise no exception because the input is **syntactically valid**.

Replace with:

```properties
app.request-timeout=5s
```

or:

```properties
app.request-timeout=5000ms
```

If bare numbers should be interpreted as seconds, declare:

```java
@DurationUnit(ChronoUnit.SECONDS)
private Duration requestTimeout;
```

Then `app.request-timeout=5` means 5 seconds **on this annotated target**. Still, even with `@DurationUnit`, writing `5s` in the file is clearer for operators.

### 6.3. Common Duration Mistakes

| Input | Status | Remediation |
| --- | --- | --- |
| `5s` | Valid duration form | Appropriate if the app needs 5 seconds |
| `5000ms` | Valid, equals 5 seconds | Use when milliseconds should be explicit |
| `PT5S` | ISO-8601 form | Use when sources follow ISO standards |
| `5` | Valid syntax, defaults to 5ms | Add a suffix or `@DurationUnit` |
| `5sec` | Not in the short suffix list documented by Boot 3.3 | Change to `5s` or ISO-8601 |
| `5minutes` | Not a documented compact form | Change to `5m` or `PT5M` |
| `abc` | Malformed | Fix to a parseable value |
| `-5s` | Valid negative `Duration` representation | Add validation if timeouts must be non-negative/positive |
| Huge value | Risk of exceeding Java type limits or downstream ms/int overflow | Enforce bounds at each layer |

**Do not confuse `m` in Duration with `M` or `MB` in DataSize.** `2m` is 2 minutes, not 2 megabytes.

### 6.4. 0ms and Negative Values Carry Special Business Meaning

A `Duration.ZERO` may mean "do not wait", "disable timeout", or "execute immediately", depending on the consuming API. A negative duration is representable in Java, yet a given client/server API may reject it. **The binder does not know whether zero or negative values are valid for your application.**

When you must enforce `requestTimeout > 0` up to 30 seconds, validate explicitly after binding or write a custom Bean Validation constraint. `@Min(1)` is not a general option for `Duration` objects, since `@Min` targets supported numeric types.

## 7. Period: Do Not Confuse Calendar Spans with Duration

`java.time.Period` represents calendar days, months, and years. Spring Boot 3.3 supports:

- Integers: default **days**, unless `@PeriodUnit` is present.
- ISO-8601 strings such as `P3D`, `P1M`, `P1Y3D`.
- Human-readable forms such as `3d`, `2w`, `1m`, `1y3d`.

### Period Units

| Suffix | Meaning |
| --- | --- |
| `y` | Years |
| `m` | Months |
| `w` | Weeks (converted to 7 days) |
| `d` | Days |

Notice the same `m` suffix with **different target types**:

```text
Duration + "1m" -> 1 minute
Period   + "1m" -> 1 month
```

Example:

```properties
app.retention=30d
```

If the target is `Period`, the value represents 30 calendar days. When the target is `Duration`, `30d` is a fixed second-based duration for 30 24-hour days; the two behave differently when computing with calendars or timezones.

### Wrong Unit in Period

```properties
app.retention=30
```

For `Period` without `@PeriodUnit`, `30` means **30 days**. If operators intended 30 months, the value must state `30m`, or the model/annotation must match.

### Do Not Use Period for Technical Timeouts

Request timeouts, socket timeouts, and retry backoffs belong to `Duration`. Retention spans measured in calendar months/years under business policies can use `Period`. Picking the wrong target type can trigger conversion failures or wrong time calculations from the very same number.

## 8. DataSize: Default Unit Is Bytes, Not KB/MB

Spring Boot 3.3 supports `org.springframework.util.unit.DataSize` for expressing data capacities. Supported formats:

- Long integers **without a suffix**: default **bytes**, unless `@DataSizeUnit` is present.
- Number + size suffix: `256B`, `16KB`, `10MB`, `2GB`, etc.

### 8.1. Supported Suffixes

| Suffix | Meaning |
| --- | --- |
| `B` | Bytes |
| `KB` | Kilobytes |
| `MB` | Megabytes |
| `GB` | Gigabytes |
| `TB` | Terabytes |

Example:

```properties
app.cache-size=16MB
app.upload-limit=512KB
app.buffer-size=256B
```

If declared as:

```java
private DataSize cacheSize;
```

then `app.cache-size=16MB` parses into the corresponding `DataSize`.

### 8.2. Silent Unit Error

```properties
app.cache-size=16
```

Without `@DataSizeUnit`, `16` means **16 bytes**, not 16 MB. Write:

```properties
app.cache-size=16MB
```

Or in Java:

```java
@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize cacheSize;
```

With this annotation, bare `16` is interpreted as 16 MB. However, to avoid forcing operators to check Java annotations just by reading a config file, **always writing unit suffixes for `DataSize` is recommended**.

### 8.3. Using Wrong Suffixes

Strings like `16MiB`, `16Megabytes`, or `16M` are not part of the `B/KB/MB/GB/TB` `DataSize` suffix list described in Spring Boot 3.3 documentation. For clear, compatible configuration, use `16MB` or one of the listed units.

Never write `16m` intending 16 MB; `m` means something completely different in `Duration`/`Period`. `DataSize` units must match both the target type and valid syntax.

### 8.4. Exceeding Representation Limits or Real Environment Resources

`DataSize` can represent large sizes at the API level, yet:

- An extremely large string may fail to convert to a numeric/`DataSize` value by exceeding internal limits.
- A successfully converted size may exceed RAM, disk space, or container quotas.
- Narrowing `DataSize.toBytes()` (`long`) to `int` or passing it to a 32-bit integer API risks **downstream overflow**.
- Negative or zero values may be representable yet invalid for a specific buffer, upload limit, or cache size.

Therefore enforce **business bounds** via proper validation and safe checks before narrowing types:

```java
DataSize configured = properties.getCacheSize();
long bytes = configured.toBytes();

if (bytes <= 0 || bytes > 100L * 1024 * 1024) {
    throw new IllegalArgumentException(
            "app.cache-size must be > 0 and <= 100MB");
}

int safeBytes = Math.toIntExact(bytes);
```

`Math.toIntExact` throws an exception if the `long` falls outside `int` range instead of silently truncating via `(int)`. Add real resource checks as needed; validators cannot replace capacity planning.

## 9. Unit Comparison Table: The Same Number Can Mean Completely Different Things

Suppose the configuration contains only the text `"10"`:

| Java Target | Description | Meaning Without a Unit-Changing Annotation |
| --- | --- | --- |
| `int` | Integer value | 10 |
| `long` | Long integer value | 10 |
| `Duration` | Time span | 10 **ms** |
| `Period` | Calendar period | 10 **days** |
| `DataSize` | Data size | 10 **bytes** |
| `String` | Text | String `"10"` |

To make intent unmistakable in the file:

```properties
app.retry-count=10
app.request-timeout=10s
app.retention=10d
app.buffer-size=10MB
```

**Do not guess units from property names alone**, such as `timeout` or `size`. Check the actual target type and `@DurationUnit`/`@PeriodUnit`/`@DataSizeUnit` annotations in Java code.

## 10. Out of Valid Range: Conversion Differs from Validation

A value such as:

```properties
app.worker-count=0
```

converts cleanly to `int 0`. Yet in the `AppProperties` example, `workerCount` carries `@Min(1)`, making this a **policy violation**, not a parser failure.

Similarly:

```properties
app.worker-count=128
```

parses cleanly, yet exceeds `@Max(64)`.

Common constraint categories:

| Type / Need | Suitable Constraint | Notes |
| --- | --- | --- |
| Integer ≥ 0 | `@Min(0)` | Allows 0 |
| Integer ≥ 1 | `@Min(1)` or `@Positive` | Rejects 0 and negatives |
| Integer capped at threshold | `@Max(n)` | Never runs if conversion already failed |
| Decimal in range | `@DecimalMin`, `@DecimalMax` | Watch inclusive/exclusive bounds |
| Required non-empty string | `@NotBlank` | Distinct from `@NotNull` |
| Pattern-matched string | `@Pattern` | Match regex to data contract |
| Nested object | `@Valid` | Enables validating child properties |
| Known enum | Enum Java target | Conversion checks valid constant names |
| `Duration`/`DataSize` in custom range | Custom constraint/validator | Do not assume `@Min` works on all objects |

### 10.1. Decimal Example

```java
import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;

@DecimalMin("0.0")
@DecimalMax("1.0")
private BigDecimal sampleRate = new BigDecimal("0.5");
```

Values:

```properties
app.sample-rate=0.0
app.sample-rate=1.0
```

are valid at both boundaries under this example constraint. `app.sample-rate=1.25` parses into `BigDecimal` yet **fails validation**. `app.sample-rate=abc` fails immediately during type conversion.

Do not use `double` for decimal values requiring exactness; `BigDecimal` is appropriate when exact base-10 representation is required.

### 10.2. Missing, Empty, and Zero Are Three Different Cases

Suppose a JavaBean has:

```java
@Min(1)
private int workerCount = 4;
```

- **Missing `app.worker-count`:** can keep the default value 4.
- **`app.worker-count=0`:** carries value `0`, converts cleanly yet violates `@Min(1)`.
- **`app.worker-count=`:** empty string; check how conversion handles primitive vs. nullable types rather than assuming `0` or missing.
- **`app.worker-count=abc`:** invalid numeric format.

If configuration is declared mandatory rather than relying on field initializers, use wrappers/constraints or explicit presence checks in `Environment`; a Java primitive's default does not prove the property was provided.

## 11. `@Validated` and Jakarta Bean Validation in @ConfigurationProperties

Spring Boot 3.3 validates `@ConfigurationProperties` when the bean carries `@Validated` and a compatible Bean Validation provider is on the classpath.

Example class:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public class WorkerProperties {

    @Min(1)
    @Max(64)
    private int threads = 4;

    @NotBlank
    private String region = "local";

    @Valid
    private final Pool pool = new Pool();

    public int getThreads() { return threads; }
    public void setThreads(int threads) { this.threads = threads; }

    public String getRegion() { return region; }
    public void setRegion(String region) { this.region = region; }

    public Pool getPool() { return pool; }

    public static class Pool {

        @Min(1)
        @Max(100)
        private int maxConnections = 20;

        public int getMaxConnections() { return maxConnections; }
        public void setMaxConnections(int value) {
            maxConnections = value;
        }
    }
}
```

Configuration:

```properties
worker.threads=0
worker.pool.max-connections=200
```

Both values are well-formed integers. When validation runs, both are rejected for violating the declared constraints. `@Valid` validates the nested `pool` object even when pre-initialized.

**Do not assume:** without a Bean Validation provider or proper validation setup, constraint annotations will not be enforced automatically. Spring Boot projects typically include `spring-boot-starter-validation`.

### `@NotBlank` vs. `@NotNull`

`@NotNull` does not catch empty strings. For example:

```properties
worker.region=
```

`worker.region` can bind as an empty string. When non-whitespace characters are required, `@NotBlank` is better suited than `@NotNull`.

### Do Not Hide Errors with `ignoreInvalidFields`

`@ConfigurationProperties` has an `ignoreInvalidFields` attribute, yet enabling it just to "boot at any cost" can retain stale/default values and mask broken operational settings. Normally **do not enable it** just to suppress conversion errors; fix the source value or design an explicit, tested fallback.

`ignoreUnknownFields` is a separate setting: it governs keys that do not map to the model, not a general license to accept malformed values.

## 12. Example Custom Validator for Duration/DataSize

Bean Validation does not know automatically that every `Duration` must be positive or every `DataSize` must stay within service limits. Add explicit checks at the validation layer or after binding.

Example getter-level Bean Validation constraint:

```java
import java.time.Duration;
import jakarta.validation.constraints.AssertTrue;

public class TimeoutProperties {

    private Duration requestTimeout = Duration.ofSeconds(5);

    public Duration getRequestTimeout() { return requestTimeout; }
    public void setRequestTimeout(Duration value) {
        requestTimeout = value;
    }

    @AssertTrue(message =
            "request-timeout must be between 1ms and 30s")
    public boolean isRequestTimeoutInRange() {
        return requestTimeout != null
                && requestTimeout.compareTo(Duration.ofMillis(1)) >= 0
                && requestTimeout.compareTo(Duration.ofSeconds(30)) <= 0;
    }
}
```

This illustrates a custom rule via `@AssertTrue`; it only runs when the enclosing object **is validated**. If `TimeoutProperties` is a nested class inside `@ConfigurationProperties`, put `@Valid` on the parent property or apply equivalent validation.

For `DataSize`, you can likewise check `toBytes()`, bounds, and business rules in a custom validator. If error messages need to target the `cacheSize` field directly, a **custom constraint annotation + `ConstraintValidator`** is cleaner than an auxiliary `@AssertTrue` method.

**Separation:** custom validators are application code, not unit converters in the binder. Validators enforce policy errors; converters handle data parsing.

## 13. Find the Effective Value Before Editing Files

The bug may not live in the file you are editing. Spring Boot merges configuration from multiple `PropertySource`s; a command-line argument or environment variable can override a file inside the JAR.

Suppose a file has:

```properties
app.request-timeout=5s
```

While the deployment environment sets:

```bash
APP_REQUESTTIMEOUT=5
```

The binder matches the environment variable and takes the higher-precedence value from the OS environment. The resulting `Duration` becomes **5ms**, even though the JAR file correctly says `5s`.

Or:

```bash
java -jar myapp.jar --app.worker-count=0
```

If `@Min(1)` requires `workerCount ≥ 1`, the failure comes from **CLI**, not `application.yaml`.

Common sources and precedence in Boot 3.3 (not an exhaustive list):

```text
Default properties
       < Config Data (application.*)
       < OS environment
       < Java system properties (-D)
       < Command-line arguments (--...)
```

Special sources such as `SPRING_APPLICATION_JSON`, test properties, Devtools, and Servlet config have their own positions. Check the **application's actual order** rather than treating this summary as an absolute rule.

### Relaxed Binding When Reading Environment Variables

Formula for deriving an env var name from a canonical property:

1. Replace dots `.` with `_`.
2. Remove hyphens `-`.
3. Convert to uppercase.

Examples:

```text
app.max-retries     -> APP_MAXRETRIES
app.worker-count    -> APP_WORKERCOUNT
app.request-timeout -> APP_REQUESTTIMEOUT
app.cache-size      -> APP_CACHESIZE
```

Do not write `APP_REQUEST_TIMEOUT` and assume it always maps to `app.request-timeout`. Underscores represent hierarchy levels; hyphens in canonical properties **are removed**, not replaced by underscores.

## 14. Reading Errors with `Origin` and Tracing Back to the Exact File

A file-backed Config Data source typically tracks origin metadata pinpointing where a property was declared. When startup reports an error like:

```text
Property: app.cache-size
Value: "ten-gigabytes"
Origin: class path resource [application.yaml] - 12:15
Reason: Failed to convert property value ...
```

trace through:

1. **Key:** `app.cache-size` is the property to fix.
2. **Value:** does `ten-gigabytes` follow valid `DataSize` syntax? No.
3. **Origin:** source file and location, if reported. In YAML, check indentation and which document is active.
4. **Target type:** `DataSize`, not `String`.
5. **Default unit:** bytes if suffixless and unannotated.
6. **Higher-precedence source:** origin might point to external Config Data or another source.
7. **If parsing succeeds:** proceed to check validation and policy.

**Security note:** Spring Boot may mask sensitive values in diagnostic tools. Do not enable secret unmasking just to troubleshoot ordinary configuration errors.

### Profiles and Config Data Can Alter the Effective Value

```yaml
# application.yaml
app:
  request-timeout: 5s
```

```yaml
# application-prod.yaml
app:
  request-timeout: 5
```

When `prod` is active, the profile file overrides the timeout to 5ms. Inspecting only the base file makes it hard to see why the timeout is suddenly so short.

Inspect active profiles, `spring.config.import`, `spring.config.additional-location`, profile-specific files, and CLI/environment overrides when tracking down origins.

## 15. 10-Step Diagnostic Sequence

When a configuration value is wrong or prevents startup, follow these steps:

1. **Identify the canonical property** (e.g., `app.request-timeout`), `@ConfigurationProperties` prefix, and target Java property.
2. **Check the target type:** `int`, `Integer`, `Boolean`, `Duration`, `Period`, `DataSize`, enum, `URI`, List/Map, or custom type.
3. **Identify the effective source:** Config Data, profile, OS env, JVM `-D`, CLI, import, or test `PropertySource`.
4. **Inspect the raw value** without logging secrets; distinguish missing, empty string, `0`, `false`, and non-empty strings.
5. **Check syntax** for the data type: integer, boolean, ISO duration, unit suffix, YAML syntax.
6. **Check units:** how is bare `10` interpreted when targeting `Duration`/`Period`/`DataSize` with or without `@*Unit`?
7. **Check type range:** does the value exceed `int`/`long` limits or downstream library limits?
8. **Check Bean Validation:** are `@Min`/`@Max`/`@NotBlank`/`@Valid`/custom constraints enforced?
9. **Verify business impact:** are 0, negative, huge, or tiny values valid for the actual service/resource?
10. **Fix the winning source**, then rerun/retest in the matching environment. Avoid masking conversion errors with `ignoreInvalidFields` by default.

Decision flow:

```text
Is there an effective value?
  ├─ No -> intentional default / required declaration -> validation?
  └─ Yes
      |
      v
  Does it match the target type syntax?
      ├─ No -> fix text/format/quotes/enum/number
      └─ Yes
          |
          v
      Is the unit what was intended?
          ├─ No -> add suffix / fix @*Unit
          └─ Yes
              |
              v
          Does it fit within the target type range?
              ├─ No -> lower value / pick wider type
              └─ Yes
                  |
                  v
              Does it pass business validation?
                  ├─ No -> fix config or constraint
                  └─ Yes -> inspect downstream code and source precedence
```

Do not stop diagnosing just because the binder threw no exception: **wrong units** often pass parsing cleanly.

## 16. Symptom → Cause → Fix Table

| Symptom | Problem Category | Primary Fix |
| --- | --- | --- |
| Cannot bind `worker-count=abc` | Invalid syntax | Supply a valid integer |
| Cannot bind `worker-count=9999999999999` to `int` | Type range overflow | Use a smaller number or wider target type |
| `worker-count=0` fails `@Min(1)` constraint | Business range violation | Pick `≥ 1` if required by policy |
| Request timeout is 5ms despite intending 5s | Wrong unit | Write `5s` or `5000ms` |
| Buffer set to 16B instead of 16MB | Wrong unit | Write `16MB` |
| `cache-size=16MiB` fails to parse as expected | Suffix outside documented list | Use `16MB` |
| `retention=1m` gives 1 month instead of 1 minute | Wrong type/unit | `Period` uses months; `Duration` uses minutes |
| `enabled=maybe` fails | Invalid boolean format | Use `true` or `false` |
| `enabled=false` succeeds yet feature is off | Valid explicit value | Verify intent rather than forcing `true` |
| `region=` passes `@NotNull` | Wrong constraint | Use `@NotBlank` |
| Negative timeout passes Binder yet fails library | Downstream policy | Validate `Duration` before use |
| Huge `DataSize` causes downstream narrowing bug | Downstream overflow | Validate bounds before `toIntExact` |
| `application.properties` looks right yet runtime fails | Overridden by another source | Check profile, OS env, CLI, and origin |
| Typo key throws no exception | Unknown fields | Use metadata/tests and strict binding where needed |
| `ignoreInvalidFields` enabled and app runs on default | Masked error | Disable ignoring errors; fix source value |
| Nested bean constraint never triggers | Missing cascade validation | Add `@Valid` and Bean Validation provider |
| Config fails only in production | Profile/env differs from local | Reproduce with production profile and overrides |

## 17. Inspecting with Environment and the Bound Bean

Sometimes a property binds to a **type-valid value with the wrong unit**, so the bean still initializes. You can inspect both raw and typed values for **non-sensitive** keys:

~~~java
package com.example.demo.config;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ConfigDiagnostics {

    @Bean
    ApplicationRunner printEffectiveTimeout(
            Environment env, AppProperties props) {
        return args -> {
            String key = "app.request-timeout";

            String raw = env.getProperty(key);
            System.out.println("Raw effective value: "
                    + (raw == null ? "<missing>" : "[" + raw + "]"));

            System.out.println("Typed timeout: "
                    + props.getRequestTimeout());

            System.out.println("Timeout in milliseconds: "
                    + props.getRequestTimeout().toMillis());
        };
    }
}
~~~

For example, if `app.request-timeout=5`:

```text
Raw effective value: [5]
Typed timeout: PT0.005S
Timeout in milliseconds: 5
```

If `app.request-timeout=5s`:

```text
Raw effective value: [5s]
Typed timeout: PT5S
Timeout in milliseconds: 5000
```

This snippet assumes `AppProperties` bound successfully, has no `@DurationUnit` altering `requestTimeout`, and has no other override. It **will not run** if startup fails before creating `ApplicationRunner`, so when binding fails, read startup failure analysis/logs instead.

### Checking Whether a Property Is Present

```java
boolean present = env.containsProperty("app.request-timeout");
String raw = env.getProperty("app.request-timeout");
```

`containsProperty` tells whether `Environment` resolves a non-null value. It does not tell "which raw file defines this key", especially when multiple `PropertySource`s exist or a source represents null.

**Never dump the entire `Environment`** just to chase one bug; it can contain credentials and tokens.

## 18. Actuator, Logging, and Data Sources

When using Spring Boot Actuator, useful diagnostic endpoints include:

- `/actuator/env`: view effective properties or `PropertySource`s, subject to exposure/sanitization config.
- `/actuator/configprops`: inspect `@ConfigurationProperties` beans and bound values, subject to security and masking.

**Never expose these two endpoints publicly.** Enable them only with proper authentication/authorization, restricted exposure, and secret protection.

To increase logging while tracking Config Data/Binding errors, try:

```properties
logging.level.org.springframework.boot.context.config=DEBUG
logging.level.org.springframework.boot.context.properties=DEBUG
```

Depending on version, source type, and when logging initializes, not every conversion step appears at `DEBUG`. You can raise `TRACE` for a specific package in controlled environments, keeping in mind logs may capture sensitive configuration and grow significantly.

`--debug` at launch helps inspect auto-configuration condition reports where appropriate; it **does not fix binding errors**, and condition reports should not be confused with converter error origins or reasons.

## 19. Testing Conversion and Validation Errors with ApplicationContextRunner

Rather than testing only happy paths, test malformed inputs and boundary limits. `ApplicationContextRunner` from `spring-boot-test` spins up a small context with explicit property values.

Test configuration class:

```java
package com.example.demo;

import com.example.demo.config.AppProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AppProperties.class)
class BindingTestConfig {
}
```

Test:

```java
package com.example.demo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AppPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BindingTestConfig.class);

    @Test
    void validUnitsAreBound() {
        runner
            .withPropertyValues(
                "app.request-timeout=5s",
                "app.cache-size=16MB",
                "app.worker-count=4")
            .run(context -> {
                assertThat(context).hasNotFailed();
                var props = context.getBean(
                        com.example.demo.config.AppProperties.class);
                assertThat(props.getRequestTimeout().toMillis())
                        .isEqualTo(5000);
                assertThat(props.getCacheSize().toBytes())
                        .isGreaterThan(0);
                assertThat(props.getWorkerCount())
                        .isEqualTo(4);
            });
    }

    @Test
    void badIntegerFormatFailsStartup() {
        runner
            .withPropertyValues("app.worker-count=not-an-int")
            .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void businessRangeIsValidated() {
        runner
            .withPropertyValues("app.worker-count=0")
            .run(context -> assertThat(context).hasFailed());
    }
}
```

This example requires Spring Boot Test, AssertJ/JUnit, and a Bean Validation provider if validation must run. `hasFailed()` verifies the context failed to start rather than asserting an exact exception class across every patch release.

Add tests for `0`, `-1`, `@Max`, bare numeric `Duration`/`DataSize`, and profile overrides. A test checking only "the bean was created" will miss 5ms instead of 5s; assert **the typed result and unit**.

### Building Tests That Distinguish Parse Errors from Range Errors

A meaningful test matrix:

| Property | Input | Expected Outcome |
| --- | --- | --- |
| `app.worker-count` | `4` | Context starts; binds `4` |
| `app.worker-count` | `0` | Conversion succeeds, `@Min(1)` fails |
| `app.worker-count` | `abc` | Conversion fails |
| `app.worker-count` | Number > 2^31 − 1 | Fails due to `int` type range |
| `app.request-timeout` | `5s` | 5 seconds |
| `app.request-timeout` | `5` | 5 milliseconds if no `@DurationUnit` |
| `app.cache-size` | `16MB` | 16 MB |
| `app.cache-size` | `16` | 16 bytes if no `@DataSizeUnit` |
| `app.enabled` | `false` | Valid `false` |
| `app.region` | Empty string | `@NotBlank` fails |

## 20. Diagnosing Custom Converters

Sometimes an application binds a specialized type—such as `ServerAddress`, `Percentage`, or a custom enum—and needs a `Converter<String,T>`.

Spring Boot 3.3 supports registering a converter dedicated to configuration properties using `@ConfigurationPropertiesBinding`.

Example type:

```java
package com.example.demo.config;

public record Percentage(int value) {
    public Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "percentage must be between 0 and 100");
        }
    }
}
```

Converter:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public class StringToPercentageConverter
        implements Converter<String, Percentage> {

    @Override
    public Percentage convert(String source) {
        String trimmed = source.trim();
        if (!trimmed.matches("\\d+")) {
            throw new IllegalArgumentException(
                    "percentage must be an integer");
        }
        return new Percentage(Integer.parseInt(trimmed));
    }
}
```

Model:

```java
@ConfigurationProperties(prefix = "app")
public class PercentageProperties {
    private Percentage sampleRate;

    public Percentage getSampleRate() { return sampleRate; }
    public void setSampleRate(Percentage sampleRate) {
        this.sampleRate = sampleRate;
    }
}
```

Config:

```properties
app.sample-rate=80
```

If the value is `120`, integer parsing succeeds while `Percentage`'s constructor intentionally rejects it for exceeding the range. That is **domain validation inside the value object**, distinct from failing to parse a number.

**Lifecycle warning:** beans used for configuration property conversion may be requested **very early** at application startup; converters should have simple dependencies and avoid pulling in late-initialized beans. When customizing `ConversionService`, watch the `conversionService` bean name and initialization order.

Do not write custom converters merely to parse ordinary `Duration`/`DataSize` values; Spring Boot already supplies those converters and unit annotations.

## 21. Java Type Smaller Than the Value: int, long, byte, and Narrowing

A value may fit in `long` while overflowing `int`. Example:

```properties
app.max-events=3000000000
```

If the Java target is `int`, this number exceeds 2,147,483,647. Change the target to `long` when the business domain genuinely needs more than 32 bits:

```java
private long maxEvents;
```

**Do not widen types just to mask policy errors.** If the system should allow at most 100,000 events, enforce `@Max(100000)` or custom validation even if the Java type can hold more.

Signed integer ranges:

```text
byte  → -128 to 127
short → -32,768 to 32,767
int   → -2,147,483,648 to 2,147,483,647
long  → signed 64-bit range
```

In Java, narrowing casts perform no automatic range checks:

```java
long raw = 3_000_000_000L;
int unsafe = (int) raw;           // silent data truncation
int checked = Math.toIntExact(raw); // throws ArithmeticException
```

This failure can appear **after the binder successfully binds `long`**, when downstream code narrows it. Diagnostics must follow the value to where it is consumed, not stop once the bean constructs.

## 22. Empty Strings, Placeholder Defaults, and @DefaultValue

A **missing** property differs from a property set to an empty string.

```properties
# app.name is absent
app.region=
```

As `String` via `Environment`:

```text
app.name   -> null (when no source defines it)
app.region -> ""
```

With placeholders:

```java
@Value("${app.name:Guest}")
private String name;
```

When `app.name` is missing, default `Guest` is used. When `app.name=`, the property is present with an empty string, so the placeholder default generally **does not replace** it with `Guest`.

`@DefaultValue` on constructor-bound `@ConfigurationProperties` follows the same rule: the default applies when the binder **does not find the property**; a property present with an empty string does not automatically trigger `@DefaultValue`.

If the target is primitive `int` or `boolean`, an empty string can behave differently during conversion/binding compared to a missing key. Never silently coerce empty strings to `0`/`false` unless the application explicitly designs and documents that rule.

### Why Diagnose Empty Strings Before Parsing?

An operator might set:

```bash
APP_WORKERCOUNT=""
```

thinking leaving it blank lets the app pick up the default `4`. Instead, that is a **present environment variable** with an empty value, unlike leaving the variable unset. If an error occurs only in containers, check whether Compose/Kubernetes/CI manifests are injecting empty variables unintentionally.

For required strings, `@NotBlank` distinguishes meaningful content from empty/whitespace; for typed numbers, supply a valid number or omit the key so valid defaults apply.

## 23. YAML Can Alter How Values Are Parsed

YAML is a data serialization language with its own syntax quirks. Watch out for:

- Wrong indentation shifting the property path—for instance, `app.retry-count` accidentally nested under another object.
- Strings with special characters needing quotes to preserve exact content.
- `true` and `false` parsed as boolean scalars vs. `"true"` and `"false"` as text; the binder can convert compatible forms to the target type.
- `null`/valueless keys differing from empty string `""`.
- Values with unit suffixes like `5s`, `16MB` written clearly; quoting can improve clarity.
- Multi-document YAML files separated by `---` containing different values gated by `spring.config.activate.on-profile`; verify which document is active.

Clear YAML example:

```yaml
app:
  worker-count: 4
  max-retries: 0
  request-timeout: "5s"
  cache-size: "16MB"
  enabled: false
  region: "ap-southeast-1"
```

YAML syntax parsing happens before or while data loads into Config Data; do not confuse a YAML parser error with a binder failure to convert `String -> Duration`.

## 24. Intentional Configuration: Defaults, Units, and Limits

A solid configuration contract has three layers:

**Layer 1 — Names and types:**

```text
app.worker-count     Integer
app.request-timeout  Duration
app.cache-size       DataSize
app.region           String
```

**Layer 2 — Units and default values:**

```text
app.worker-count     default 4
app.request-timeout  default 5s
app.cache-size       default 16MB
app.region           default local
```

**Layer 3 — Valid ranges:**

```text
app.worker-count     1..64
app.request-timeout  > 0ms and <= 30s
app.cache-size       > 0B and <= 100MB
app.region           non-blank string, in allowed region list
```

Represented in code via:

- Field initializers/`@DefaultValue`: intentional defaults.
- `@DurationUnit`/`@DataSizeUnit`: interpretation of bare numbers.
- Bean Validation or custom validators: range limits.
- README/configuration metadata: operator documentation.
- Tests: verifying valid samples, syntax errors, wrong units, and boundary values behave as expected.

If you want to eliminate bare-number ambiguity completely, instruct operators to **always write suffixes** for `Duration`/`DataSize` in config files, even when unit annotations are present.

## 25. Distinguishing Startup Failures from Runtime Failures

| Phase | Example | Cause |
| --- | --- | --- |
| Config Data parse | Malformed YAML indentation or syntax | File cannot be parsed as config data |
| Binding conversion | `app.worker-count=foo` | Cannot convert `String` to `int` |
| Binding conversion | Number too large for `int` | Outside type range |
| Validation | `worker-count=0` with `@Min(1)` | Right type, violates policy |
| Runtime value usage | `Duration=5ms` when intending 5s | Bound cleanly, wrong unit/semantics |
| Runtime value usage | `DataSize=16MB` exceeding memory quota | Valid in model, unsuitable for resources |
| Runtime downstream conversion | `long` cast to `int` | Data loss after binding |

Where the error occurs dictates the fix:

- Parse error: fix file syntax.
- Conversion error: fix value to match target type or valid converter.
- Validation error: fix value to fit allowed bounds or revisit business rules.
- Unit/semantic error: fix suffix, annotation, or Java type.
- Downstream error: add range checks, unit conversions, or capacity constraints at consumption sites.

Do not assume every `IllegalArgumentException` at startup is a configuration error; inspect the stack trace, property name, and origin to pinpoint the root cause.

## 26. Implementation and Operations Checklist

- [ ] Property names in documentation use **lowercase kebab-case**.
- [ ] `@ConfigurationProperties` prefix and Java target types match.
- [ ] Optional properties have explicit defaults.
- [ ] `Duration` properties in files specify `ms/s/m/h/d` clearly where needed.
- [ ] `DataSize` properties specify `B/KB/MB/GB/TB`.
- [ ] `Period` properties use `d/w/m/y` for calendar spans without confusing them with `Duration`.
- [ ] When bare numbers are used, check `@DurationUnit`, `@DataSizeUnit`, and `@PeriodUnit`.
- [ ] Large integers use sufficiently wide types without unchecked narrowing casts.
- [ ] Critical settings have `@Min`/`@Max`/`@NotBlank`/`@Valid` or custom validation.
- [ ] A Jakarta Bean Validation provider is present if constraints must be enforced.
- [ ] Semantics of `0` and negative values are defined for each property.
- [ ] `false` and `0` are not treated as missing properties.
- [ ] Empty strings are not treated as automatic fallbacks.
- [ ] `ignoreInvalidFields` is not enabled merely to hide operational mistakes.
- [ ] `Property`, `Value`, `Origin`, and `Reason` are traced in failure analysis.
- [ ] Profiles, Config Data imports, OS env, `-D`, and CLI are checked for the winning source.
- [ ] Whenever possible, tests assert **post-conversion values** and units rather than merely checking context startup.
- [ ] Actuator `env`/`configprops` and debug logging are secured and never leak secrets.
- [ ] Upper and lower boundaries are tested on both sides.
- [ ] Configuration READMEs are updated whenever Java types, defaults, or units change.

## 27. Quick Reference Cheat Sheet

| If You See... | Ask... | Typical Action |
| --- | --- | --- |
| `Failed to bind... to int` | Is the value an integer within `int` range? | Fix the text or target type |
| `ConversionFailedException` | What are the source and target types? | Inspect root cause |
| `BindValidationException` | Which constraint was violated? | Check `@Min`/`@Max`/... |
| `timeout=10` | What is the default unit? | Write `10s` if intending seconds |
| `cache-size=10` | 10 bytes or 10 MB? | Write `10MB` if intending MB |
| `retention=1m` | Is target `Period` or `Duration`? | Pick the right type/unit |
| `0` | Is `0` a valid option? | Do not reject blindly |
| `false` | Is disabling the feature intentional? | Preserve explicit value |
| `value=""` | Is the key present or missing? | Do not assume fallback applies |
| File looks right yet runtime is wrong | Did a higher source override it? | Check `PropertySource`/Origin |
| Fails only in prod | Do active profiles/env differ from local? | Reproduce with prod sources and profile |
| Startup succeeds yet behavior is wrong | Bound cleanly with wrong intent or downstream bug? | Check typed value, unit, and policy |

## 28. References

- **Spring Boot 3.3 Reference — Externalized Configuration**, sections *Properties Conversion*, *Converting Durations*, *Converting Periods*, *Converting Data Sizes*, *@ConfigurationProperties Validation*, *PropertySource Order*, and *Binding*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 API — `@ConfigurationProperties`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- **Spring Boot 3.3 API — `Binder`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
- **Spring Boot 3.3 API — `@DurationUnit`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/DurationUnit.html
- **Spring Boot 3.3 API — `@DataSizeUnit`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/DataSizeUnit.html
- **Spring Boot 3.3 API — `@PeriodUnit`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/PeriodUnit.html
- **Spring Framework — Environment Abstraction**: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- **Jakarta Bean Validation — Constraints** (`@Min`, `@Max`, `@NotBlank`, `@Valid`, `@AssertTrue`): https://jakarta.ee/specifications/bean-validation/

**Conclusion:** diagnosing Spring Boot 3.3 configuration issues requires separating **invalid formats**, **wrong units**, and **out-of-range values**. Use `Environment`/origin to locate the effective raw value, check **Java target type + unit annotations** to understand the converted value, and use **Bean Validation or domain checks** to reject syntactically valid values that are unsafe for the application. Bare numeric values for `Duration`/`DataSize` are especially prone to silent mistakes; always declare explicit unit suffixes in configuration.