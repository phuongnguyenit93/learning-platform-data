# Default Units and @DurationUnit When Converting Duration in Spring Boot

## 1. One Small Number Can Make a Timeout Off by a Factor of a Thousand

A Spring Boot application calling an external service has this configuration:

~~~properties
client.request-timeout=30
~~~

You expect this value to mean **30 seconds**, while the Java field has the type:

~~~java
private Duration requestTimeout;
~~~

With standard `@ConfigurationProperties` binding and no explicit unit annotation, Spring Boot interprets the **suffixless** number `30` as **30 milliseconds**, not 30 seconds.

The difference is huge:

~~~text
30 ms = 0.03 seconds
30 s  = 30,000 ms
~~~

An unexpectedly short timeout can cause requests to fail even when the external service is healthy. Conversely, a number intended as milliseconds but interpreted as seconds can leave tasks hanging far too long.

Spring Boot provides the `@DurationUnit` annotation to handle this when binding `java.time.Duration`:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration requestTimeout;
~~~

When placed properly and processed by the binder, `client.request-timeout=30` becomes **30 seconds** instead of **30 milliseconds**.

This lesson focuses on these questions:

1. Why do plain numeric values for `Duration` default to milliseconds?
2. What does `@DurationUnit` change and what does it not change?
3. When a value already has a suffix like `ms`, `s`, `m` or uses ISO-8601, does the annotation still have an effect?
4. How do you place the annotation on JavaBean fields and constructor parameters?
5. How do you distinguish **default unit** from **default value**?
6. How do you migrate from a `long` property to `Duration` without altering the meaning of legacy configuration?
7. How do you verify that `Duration` bound correctly without confusing it with `Period` or `DataSize`?

## 2. What Type Is Duration?

`java.time.Duration` is a Java type representing a time span based on seconds and sub-second nanoseconds (*seconds and nanoseconds*). It commonly appears in:

- Network connection timeouts.
- HTTP response timeouts.
- Delays between retries.
- Cache retention intervals.
- Job execution timeouts.
- Scheduler intervals.
- Deadlines for how long an operation may run.

In Java:

~~~java
import java.time.Duration;

Duration first = Duration.ofMillis(500);
Duration second = Duration.ofSeconds(30);
Duration third = Duration.ofMinutes(2);
~~~

These objects hold concrete time values. `Duration` does not store "30 with an unknown unit"; once created, the object represents an unambiguous length of time.

For example:

~~~java
Duration.ofSeconds(30).toMillis(); // 30000
Duration.ofMillis(30).toMillis();  // 30
~~~

Spring Boot must convert a string or number from `Environment` into a `Duration`. It is at this **input conversion step** that the question "what is the default unit?" arises.

### Do Not Confuse with Points in Time

`Duration` expresses *how long*, not *when*:

- `Duration.ofSeconds(30)`: a 30-second span.
- `Instant.now()`: a point in time.
- `LocalDateTime`: local date and time.
- `Period.ofMonths(1)`: a calendar-based span in years/months/days with different rules.

`@DurationUnit` only supplies unit semantics for converting `Duration`; it does not define timezones, calendars, or schedules.

## 3. Which Duration Formats Does Spring Boot Accept?

In externalized configuration and type-safe configuration properties, Spring Boot supports three common representations.

### 3.1. Numbers Without a Suffix

~~~properties
client.request-timeout=30
~~~

This value does not specify a unit. In standard binding:

- **Without `@DurationUnit`:** `30` is interpreted as **30 ms**.
- **With `@DurationUnit(ChronoUnit.SECONDS)`:** `30` is interpreted as **30 s**.
- **With `@DurationUnit(ChronoUnit.MINUTES)`:** `30` is interpreted as **30 minutes**.

### 3.2. Numbers with a Unit Suffix

~~~properties
client.request-timeout=30s
~~~

The `s` suffix explicitly indicates seconds. The value carries its own unit; there is no need to guess a default unit.

Examples:

~~~properties
client.request-timeout=500ms
client.retry-delay=2s
client.cache-ttl=15m
client.long-timeout=1h
~~~

### 3.3. ISO-8601 Duration Standard

~~~properties
client.request-timeout=PT30S
client.retry-delay=PT2M
client.cache-ttl=PT1H30M
~~~

`PT30S` writes 30 seconds; `PT2M` is 2 minutes; `PT1H30M` is 1 hour 30 minutes. In those values, the unit information is built directly into the ISO-8601 expression.

Three ways to express the same `Duration`:

~~~properties
# Three independent examples — do not put all three for the same key in one file
client.request-timeout=30000
client.request-timeout=30s
client.request-timeout=PT30S
~~~

**Condition:** `30000` equals 30 seconds only when the property's default unit is **milliseconds**.

If the field has `@DurationUnit(ChronoUnit.SECONDS)`, the bare number equivalent to 30 seconds must be `30`, not `30000`.

## 4. Default Unit: No Annotation Means Milliseconds

Spring Boot documentation specifies that when binding a `Duration` from a plain numeric representation, the default unit is **milliseconds** unless overridden with `@DurationUnit`.

Example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        Duration connectTimeout,
        Duration readTimeout) {
}
~~~

Configuration:

~~~yaml
service:
  connect-timeout: 10
  read-timeout: 500
~~~

With standard binding and no other unit annotation:

~~~text
connectTimeout = PT0.01S  = 10 ms
readTimeout    = PT0.5S   = 500 ms
~~~

You can observe:

~~~java
properties.connectTimeout().toMillis(); // 10
properties.readTimeout().toMillis();    // 500
~~~

**Why do learners often get confused?** Because the value `10` under the key `connect-timeout` does not state whether it is seconds or milliseconds. Field names, property names, or code comments do not tell the binder what business unit you intended.

The converter needs a rule. The default Spring Boot uses for bare numbers is **ms**.

### Example Table Without @DurationUnit

| Configuration String | Resulting Duration | Equivalent |
| --- | --- | --- |
| `1` | 1 ms | `PT0.001S` |
| `20` | 20 ms | `PT0.02S` |
| `500` | 500 ms | `PT0.5S` |
| `1000` | 1,000 ms | `PT1S` |
| `30000` | 30,000 ms | `PT30S` |
| `60000` | 60,000 ms | `PT1M` |

A bare number is not "assumed to be seconds" merely because the field is named `timeout`, `delay`, or `duration`.

## 5. How Does @DurationUnit Change the Default Unit?

Annotation:

~~~java
import org.springframework.boot.convert.DurationUnit;
~~~

Takes a `java.time.temporal.ChronoUnit`:

~~~java
import java.time.temporal.ChronoUnit;
~~~

Example:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration requestTimeout;
~~~

Meaning: **if the input for this property does not state a unit**, the binder uses **seconds** to convert it to `Duration`.

Example:

~~~properties
client.request-timeout=30
~~~

with the field above binds to:

~~~java
Duration.ofSeconds(30)
~~~

Try changing it to:

~~~java
@DurationUnit(ChronoUnit.MINUTES)
private Duration requestTimeout;
~~~

When the source is still `30`, the value is now:

~~~java
Duration.ofMinutes(30)
~~~

**Do not apply one blanket unit annotation just because you want every timeout to have the same "number".** Choose units according to each property's configuration contract. Connection timeouts may fit seconds; polling delays may fit milliseconds; TTLs may fit minutes or hours.

### What Does Not Change?

`@DurationUnit` does **not**:

- Set a default value when the key is completely absent.
- Enable or create a configuration bean on its own.
- Change prefix names or member names during relaxed binding.
- Turn numbers everywhere in Java into seconds.
- Change the meaning of a value with an explicit suffix such as `500ms`, `2m`, or `PT30S`.
- Enable validation to ensure the duration is always positive.
- Replace `Thread.sleep`, timeout APIs, or scheduler logic.

It only supplies **the unit used when converting a `Duration` value that does not specify an explicit unit** via the corresponding binding mechanism.

## 6. JavaBean Binding Example with @DurationUnit

This is the easiest style of example to inspect.

### 6.1. Configuration Class

~~~java
package com.example.demo.config;

import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration connectTimeout = Duration.ofSeconds(5);

    private Duration readTimeout = Duration.ofMillis(500);

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
}
~~~

### 6.2. Registering the Configuration Bean

~~~java
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
~~~

`ClientProperties` must be within scan scope or explicitly registered via `@EnableConfigurationProperties(ClientProperties.class)`.

### 6.3. Configuration Source

~~~yaml
app:
  client:
    connect-timeout: 15
    read-timeout: 250
~~~

Output:

~~~text
connectTimeout = 15 seconds       (@DurationUnit(SECONDS))
readTimeout    = 250 milliseconds (no @DurationUnit)
~~~

Both are bare numbers, yet **each field has its own unit rule**.

### 6.4. Reading in a Service

~~~java
package com.example.demo.service;

import com.example.demo.config.ClientProperties;
import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class ClientSettingsService {

    private final ClientProperties properties;

    public ClientSettingsService(ClientProperties properties) {
        this.properties = properties;
    }

    public Duration connectTimeout() {
        return properties.getConnectTimeout();
    }

    public Duration readTimeout() {
        return properties.getReadTimeout();
    }
}
~~~

The service receives a bean already configured by the binder. There is no need to append `s` to the source string or multiply `15` manually into seconds.

## 7. When a Value Already Has a Suffix: Explicit Unit Wins

Keep the class:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration connectTimeout;
~~~

And vary the configuration source value:

| Source Value | Resulting Duration | Reason |
| --- | --- | --- |
| `15` | 15 seconds | No suffix, uses `SECONDS` from the annotation. |
| `15s` | 15 seconds | `s` suffix explicitly specifies seconds. |
| `15000ms` | 15 seconds | `ms` suffix explicitly specifies milliseconds. |
| `250ms` | 250 milliseconds | `ms` suffix is respected even though the annotation is `SECONDS`. |
| `1m` | 1 minute | `m` suffix explicitly specifies minutes. |
| `PT15S` | 15 seconds | ISO-8601 carries explicit duration semantics. |

An error-prone misconception is thinking the annotation "forces all values to seconds". That is false.

For example:

~~~properties
app.client.connect-timeout=250ms
~~~

is still 250 ms. The annotation does not turn 250 ms into 250 seconds.

Similarly:

~~~properties
app.client.connect-timeout=2m
~~~

is 2 minutes, not 2 seconds. This is useful when you want a convenient **default unit for bare numbers** while still allowing deployers to choose a different unit when needed.

### Practical Rule

**Write suffixes in new configurations** if you want operators to recognize the unit at a glance:

~~~yaml
app:
  client:
    connect-timeout: 15s
    read-timeout: 250ms
~~~

Meanwhile, `@DurationUnit` is vital when maintaining compatibility with **existing suffixless numbers**, or when a project has an explicit contract such as "all bare timeout values in this module are in seconds".

## 8. Duration Suffixes Supported by Spring Boot

According to Spring Boot 3.3 documentation, human-readable `Duration` syntax supports these suffixes:

| Suffix | Unit | Example | Meaning |
| --- | --- | --- | --- |
| `ns` | Nanosecond | `500ns` | 500 billionths of a second. |
| `us` | Microsecond | `250us` | 250 millionths of a second. |
| `ms` | Millisecond | `500ms` | Half a second. |
| `s` | Second | `30s` | 30 seconds. |
| `m` | Minute | `2m` | 2 minutes. |
| `h` | Hour | `1h` | 1 hour. |
| `d` | Day | `1d` | 24 hours. |

Some conversions:

~~~text
1s    = 1000ms
1ms   = 1000us
1us   = 1000ns
1m    = 60s
1h    = 60m
1d    = 24h
~~~

`Duration` is based on an exact length of time, so `1d` corresponds to 24 hours. Do not use it to replace a calendar rule like "same time tomorrow in local timezone" in all cases; that can involve calendars and daylight saving time.

### Distinguishing the Letter m

In `Duration` syntax:

~~~text
5m = 5 minutes
~~~

Not 5 months.

If you need to represent calendar months or years, the right type is usually `java.time.Period` with its own rules, not `Duration` with `@DurationUnit`.

### Can You Use y or w?

Do not assume `Period` symbols `y` or `w` work as readable `Duration` suffixes. For `Duration` per Spring Boot documentation, use the suffixes in the table or the corresponding ISO-8601 form.

## 9. ISO-8601 and Duration.parse: How Does It Differ from 30s?

Spring Boot supports both readable syntax like `30s` and ISO-8601 syntax like `PT30S`.

Example:

~~~properties
jobs.retry-delay=PT2M
jobs.execution-timeout=PT1H30M
jobs.poll-interval=PT0.5S
~~~

Corresponding values:

~~~java
Duration.ofMinutes(2)
Duration.ofMinutes(90)
Duration.ofMillis(500)
~~~

Point to remember:

~~~java
Duration.parse("PT30S")
~~~

is standard Java syntax and creates `Duration.ofSeconds(30)`.

Whereas:

~~~java
Duration.parse("30s")
~~~

is **not** ISO-8601 syntax accepted by Java's `Duration.parse`. Spring Boot supports `30s` via its own configuration converter. Do not confuse Spring Boot Binder's feature with the default capability of `java.time.Duration.parse`.

### When to Choose ISO-8601?

ISO-8601 is helpful when configuration is shared with other systems already using that standard or when expressing compound durations clearly. Short suffix syntax such as `30s` or `5m` is usually easier for operators to read in Spring Boot configuration files.

## 10. @DurationUnit in Constructor Binding

Spring Boot 3.x supports constructor binding for immutable configuration classes. With multiple `Duration` parameters, you can specify the unit on a **constructor parameter**.

Example:

~~~java
package com.example.demo.config;

import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "jobs")
public class JobProperties {

    private final Duration executionTimeout;
    private final Duration retryDelay;

    public JobProperties(
            @DurationUnit(ChronoUnit.SECONDS)
            @DefaultValue("30s")
            Duration executionTimeout,

            @DefaultValue("500ms")
            Duration retryDelay) {
        this.executionTimeout = executionTimeout;
        this.retryDelay = retryDelay;
    }

    public Duration getExecutionTimeout() {
        return executionTimeout;
    }

    public Duration getRetryDelay() {
        return retryDelay;
    }
}
~~~

When this class has a constructor needing binding and is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, the binder can construct the bean from configuration values.

Example:

~~~yaml
jobs:
  execution-timeout: 45
  retry-delay: 2s
~~~

Result:

~~~text
executionTimeout = 45 seconds
retryDelay       = 2 seconds
~~~

For `executionTimeout`, `45` has no unit, so `@DurationUnit(SECONDS)` determines its interpretation. For `retryDelay`, `2s` has its own unit, so no annotation is needed.

### Where Can @DurationUnit Be Placed?

Per the Spring Boot 3.x API, `@DurationUnit` is designed for **fields** or **parameters**. Two common placements:

- Field of a JavaBean bound via setters.
- Constructor parameter in constructor binding.

Do not assume you can place the annotation on any arbitrary Java method and expect the binder to pick it up. With constructor binding, the safe pattern is annotating the `Duration` **constructor parameter** itself.

### Records

With records:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "jobs")
public record SimpleJobProperties(
        @DurationUnit(ChronoUnit.SECONDS) Duration executionTimeout,
        Duration retryDelay) {
}
~~~

A record component can carry annotations applicable to fields/parameters, which the Java compiler propagates to the corresponding elements as appropriate. In projects using constructor binding, readers should understand this annotation applies to converting the value for the `executionTimeout` component. If a class has a complex constructor layout, write an explicit constructor/parameter to make binding conditions clear.

**Important:** constructor binding for `@ConfigurationProperties` needs an appropriate registration mechanism, not an arbitrary record annotated with `@Component` hoping Spring will automatically use the binder for constructor parameters.

## 11. Default Unit Is Completely Different from Default Value

Both concepts include the word "default", yet they are very different.

### 11.1. Default Unit

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration timeout;
~~~

This answers:

> If the configuration source has a bare number like `20`, 20 **of what unit** does it mean?

Answer: 20 seconds.

It does **not** answer:

> If the `timeout` key is completely absent, what value should be used?

### 11.2. Default Value in a JavaBean

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration timeout = Duration.ofSeconds(20);
~~~

If the key is not provided and nothing else overrides it, the initialized value `Duration.ofSeconds(20)` can be preserved in JavaBean binding.

If configuration specifies:

~~~properties
app.timeout=40
~~~

then the binder converts `40` in seconds and overwrites the field with `Duration.ofSeconds(40)`.

### 11.3. Default Value in Constructor Binding

~~~java
public JobProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        @DefaultValue("20s")
        Duration timeout) {
    this.timeout = timeout;
}
~~~

`@DefaultValue("20s")` describes the fallback value **when the property is missing** in constructor binding. Meanwhile, `@DurationUnit(SECONDS)` determines the unit when the source supplies a bare number.

Comparison table:

| Scenario | @DurationUnit(SECONDS) | @DefaultValue("20s") |
| --- | --- | --- |
| Source has `timeout=40` | 40 seconds | Default not needed. |
| Source has `timeout=500ms` | 500 ms | Default not needed. |
| Source lacks `timeout` | Does not invent 20 | Fallback value of 20 seconds. |

Do not use `@DurationUnit` as a substitute for `@DefaultValue`, and do not use `@DefaultValue` to replace the bare-number unit rule of a field.

## 12. Why Is Migrating from long to Duration Error-Prone?

A legacy project has the class:

~~~java
@ConfigurationProperties(prefix = "cache")
public class CacheProperties {
    private long expirySeconds;

    public long getExpirySeconds() {
        return expirySeconds;
    }

    public void setExpirySeconds(long expirySeconds) {
        this.expirySeconds = expirySeconds;
    }
}
~~~

File:

~~~properties
cache.expiry-seconds=60
~~~

In the older version of the application, code did:

~~~java
Duration expiry = Duration.ofSeconds(
        properties.getExpirySeconds());
~~~

The business meaning was **60 seconds**.

After upgrading the design, you might want to use `Duration`:

~~~java
@ConfigurationProperties(prefix = "cache")
public class CacheProperties {
    private Duration expirySeconds;
    // getters/setters
}
~~~

However, if the `expirySeconds` field has **no** unit annotation and the file still says `60`, the binder may treat `60` as **60 ms**. This is a serious backward-compatibility bug.

### How to Preserve Meaning

~~~java
@ConfigurationProperties(prefix = "cache")
public class CacheProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration expirySeconds;

    public Duration getExpirySeconds() {
        return expirySeconds;
    }

    public void setExpirySeconds(Duration expirySeconds) {
        this.expirySeconds = expirySeconds;
    }
}
~~~

With:

~~~properties
cache.expiry-seconds=60
~~~

the binder now constructs `Duration.ofSeconds(60)`. The meaning of the old configuration is preserved.

This is a primary use case for `@DurationUnit`: **migrating from traditional numeric properties to `Duration` without silently changing the unit of existing data**.

### Another Option: Update the Source Data

If you control every configuration source, you can switch:

~~~properties
cache.expiry-seconds=60
~~~

to:

~~~properties
cache.expiry=60s
~~~

and rename the property/field accordingly. However, when multiple deployment environments, secret managers, environment variables, and external files exist outside the JAR, not every place may be updated at the same time.

`@DurationUnit(SECONDS)` lets you support legacy bare numbers during a migration window. Even so, define the new contract clearly: for all new configurations, explicit suffixes help prevent confusion.

## 13. Do Not Rely on Field Names to Guess Units

Naming a field:

~~~java
Duration timeoutSeconds;
~~~

does not force the binder to interpret:

~~~properties
app.timeout-seconds=30
~~~

as 30 seconds. A name containing `Seconds` is just a property name; it **does not automatically create a unit annotation**.

You need:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration timeoutSeconds;
~~~

or an explicit suffix in the configuration source:

~~~properties
app.timeout-seconds=30s
~~~

In new designs, naming it `timeout` + a suffixed value `30s` is usually easier to maintain than encoding the unit in the field name and still having to remember the annotation. Still, unit-containing names may need to be retained for compatibility with existing configurations.

Similarly:

~~~java
Duration retryDelayMillis;
~~~

does not guarantee every source writes milliseconds. If a source has `2s`, the result is still 2 seconds in `Duration` binding; `Millis` in the Java name does not override an explicit suffix.

## 14. YAML, Properties, Environment Variables, and CLI Follow the Same Rule

The default unit is a rule **of the `Duration` target when the binder converts types**, not a rule limited to one file format.

Example class:

~~~java
@ConfigurationProperties(prefix = "app.jobs")
public record JobsProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration timeout) {
}
~~~

The value can be provided via Properties:

~~~properties
app.jobs.timeout=20
~~~

Via YAML:

~~~yaml
app:
  jobs:
    timeout: 20
~~~

Via an environment variable on a Unix-style shell:

~~~bash
APP_JOBS_TIMEOUT=20 java -jar app.jar
~~~

Or via command line:

~~~bash
java -jar app.jar --app.jobs.timeout=20
~~~

Under standard binding conditions, if this is the final effective value of the property, the binder converts `20` into **20 seconds** because of the annotation.

If changed to:

~~~bash
java -jar app.jar --app.jobs.timeout=500ms
~~~

the result is **500 milliseconds**.

### Which Source Wins?

If YAML has:

~~~yaml
app:
  jobs:
    timeout: 30s
~~~

while CLI specifies:

~~~bash
java -jar app.jar --app.jobs.timeout=15
~~~

in a standard Spring Boot run, CLI has higher precedence than Config Data files. The binder reads **15** from CLI and then applies `@DurationUnit(SECONDS)`, yielding **15 seconds**.

Think in two steps:

1. `Environment` selects the **effective configuration value**.
2. The binder converts that value to `Duration` using the **unit determined by the suffix or annotation**.

Do not confuse `PropertySource` ordering with unit policy.

## 15. @DurationUnit Does Not Apply Globally to Environment.getProperty

Distinguish two code snippets:

~~~java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration timeout) {
}
~~~

and:

~~~java
Duration timeout = environment.getProperty(
        "client.timeout", Duration.class);
~~~

The first goes through the `@ConfigurationProperties` binder with metadata from the `timeout` member, including `@DurationUnit`.

The second merely asks `Environment` to convert the property named `client.timeout` to `Duration`. That call **does not automatically pick up annotations located on another class**, so do not assume it applies `ClientProperties`'s `SECONDS` unit.

For instance, if `client.timeout=30`, reading via the bound properties bean can yield 30 seconds, whereas a standalone `Duration` conversion without unit metadata typically defaults to milliseconds.

To avoid two interpretations for one key:

- Prefer using the **bound properties bean** in services that need the timeout.
- Or write **explicit units** in the source: `30s`.
- If you must read the raw string directly, convert it under an explicit contract; do not silently multiply by 1,000 in multiple places.

### @Value

~~~java
@Value("${client.timeout}")
private Duration timeout;
~~~

`@Value` is a placeholder injection mechanism; it does not necessarily carry the same unit metadata as the `@ConfigurationProperties` binder. Thus, when `@DurationUnit` is needed, stick to the properties bean model or always include suffixes in the source.

In application code, avoid having multiple read paths for the same property that interpret bare numbers in different units.

## 16. Duration Conversion and Validation Are Two Separate Things

Suppose:

~~~properties
app.retry-delay=0s
~~~

The binder can convert this value to:

~~~java
Duration.ZERO
~~~

However, whether a **zero delay** makes sense for business logic is a different question.

Or:

~~~properties
app.request-timeout=-1s
~~~

If the system accepts a negative `Duration`, that does not mean a negative timeout is valid for the HTTP client you use. Each API may require a different range.

`@DurationUnit` does not automatically guarantee:

- Value is greater than 0.
- Value is non-negative.
- Value does not exceed safe limits.
- Value matches the unit expected by the HTTP/scheduler library.
- Value is initialized when the key is missing.

You can validate explicitly at usage time:

~~~java
Duration timeout = properties.requestTimeout();

if (timeout == null || timeout.isZero() || timeout.isNegative()) {
    throw new IllegalArgumentException(
            "app.request-timeout must be a positive duration");
}
~~~

With a `@ConfigurationProperties` group, you can also integrate Bean Validation or custom validation rules to catch bad configuration early at startup.

### Do Not Treat Type Conversion as Business Validation

~~~properties
app.request-timeout=999999d
~~~

This may be far larger than needed, even though the unit syntax is valid and the Java type can represent it. Validation should check sensible bounds if the application requires them.

## 17. When the Key Is Missing: @DurationUnit Does Not Provide a Default Value

Class:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration startupDelay) {
}
~~~

If `app.startup-delay` is missing, the annotation does not turn it into a default of `0s`, `1s`, or `30s`. The resulting value depends on constructor binding behavior, declared defaults, and key absence.

If the parameter is required, the clear approach is validation or an explicit default:

~~~java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private final Duration startupDelay;

    public AppProperties(
            @DurationUnit(ChronoUnit.SECONDS)
            @DefaultValue("3s")
            Duration startupDelay) {
        this.startupDelay = startupDelay;
    }

    public Duration getStartupDelay() {
        return startupDelay;
    }
}
~~~

With proper constructor binding, if the key is absent, `@DefaultValue("3s")` provides 3 seconds. If the key is `app.startup-delay=20`, the unit annotation makes the value 20 seconds.

### What If @DefaultValue("3") Is Used?

When a parameter has both `@DefaultValue("3")` and `@DurationUnit(ChronoUnit.SECONDS)`, the unit definition can be used to interpret that bare number. Yet to save readers from guessing, default configuration is clearer when written as `@DefaultValue("3s")`.

This is also a good organizational rule: **defaults state their own unit**, while the annotation still protects bare numbers passed later by deployers.

## 18. Distinguishing Duration, Period, and DataSize

Spring Boot has similarly named annotations:

| Target Type | Meaning | Bare Number Default Unit | Annotation to Change Unit |
| --- | --- | --- | --- |
| `Duration` | Time span on seconds/nanoseconds timeline | Milliseconds | `@DurationUnit` |
| `Period` | Calendar years, months, and days | Days | `@PeriodUnit` |
| `DataSize` | Data capacity | Bytes | `@DataSizeUnit` |

Duration example:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
Duration timeout;
~~~

Period example (different purpose):

~~~java
@PeriodUnit(ChronoUnit.WEEKS)
Period retentionPeriod;
~~~

DataSize example:

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
DataSize bufferSize;
~~~

These annotations are not interchangeable. `@DurationUnit` does not accept `DataUnit` and does not mean "change any kind of unit".

### Comparing m in Duration and Period

In Duration:

~~~text
3m = 3 minutes
~~~

In Period syntax:

~~~text
3m = 3 months
~~~

This is why the target Java type matters so much. Identical character strings do not necessarily carry the same meaning when bound to different types.

### Why Be Careful with Period?

A calendar month does not have a single fixed number of seconds across all cases. If a business requirement says "retain data for 3 calendar months", using `Period` or an appropriate date model is usually better than turning it into `Duration.ofDays(90)`.

Conversely, a "30-second timeout" clearly belongs to `Duration`.

## 19. Integrating Duration into Client APIs with Their Own Units

Some Java APIs accept `Duration` directly:

~~~java
someClient.setTimeout(properties.requestTimeout());
~~~

This snippet is illustrative for libraries offering such a method. In this case, `Duration` avoids ambiguous `long` conversions.

However, many other APIs take a number plus an implicit unit:

~~~java
long millis = properties.requestTimeout().toMillis();
~~~

Or:

~~~java
long seconds = properties.requestTimeout().getSeconds();
~~~

**Unit correctness must be checked at the API boundary.** If the library expects milliseconds and you pass `getSeconds()`, the timeout will be 1,000 times shorter in many cases.

### Precision Considerations

A `Duration` can be smaller than 1 ms:

~~~properties
app.poll-interval=250us
~~~

If you use:

~~~java
Duration d = properties.pollInterval();
long ms = d.toMillis();
~~~

`d.toMillis()` can truncate sub-millisecond portions when converting to an integer. Depending on your needs, keep `Duration` or use an API supporting nanoseconds/microseconds.

Some libraries impose minimum or maximum timeout limits. `@DurationUnit` is no substitute for reading the receiving library's contract.

## 20. Real-World Configuration: Multiple Timeouts with Different Units

Suppose a system handles HTTP operations, retries, and caching:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "app.runtime")
public record RuntimeProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration connectTimeout,

        @DurationUnit(ChronoUnit.SECONDS)
        Duration readTimeout,

        @DurationUnit(ChronoUnit.MILLISECONDS)
        Duration retryDelay,

        @DurationUnit(ChronoUnit.MINUTES)
        Duration cacheTtl) {
}
~~~

Source:

~~~yaml
app:
  runtime:
    connect-timeout: 5
    read-timeout: 30
    retry-delay: 250
    cache-ttl: 10
~~~

Result:

| Field | Source Number | Default Unit | Value |
| --- | ---: | --- | --- |
| `connectTimeout` | 5 | `SECONDS` | 5s |
| `readTimeout` | 30 | `SECONDS` | 30s |
| `retryDelay` | 250 | `MILLIS` | 250ms |
| `cacheTtl` | 10 | `MINUTES` | 10m |

If the deployer specifies units explicitly:

~~~yaml
app:
  runtime:
    connect-timeout: 750ms
    read-timeout: 1m
    retry-delay: 2s
    cache-ttl: 1h
~~~

then the results are:

| Field | Suffixed Value | Duration |
| --- | --- | --- |
| `connectTimeout` | `750ms` | 750ms |
| `readTimeout` | `1m` | 60s |
| `retryDelay` | `2s` | 2000ms |
| `cacheTtl` | `1h` | 60m |

The annotation is a fallback rule when **no suffix is present**, not a restriction on which units may be written in the file.

## 21. Distinguishing Unit Annotations from Renaming Properties

Two changes can vary independently:

~~~java
@ConfigurationProperties(prefix = "remote.client")
public record RemoteClientProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration connectTimeout) {
}
~~~

Canonical key name:

~~~properties
remote.client.connect-timeout=30
~~~

- `remote.client`: prefix.
- `connectTimeout`: record component name.
- `connect-timeout`: member name in configuration after relaxed binding.
- `@DurationUnit(SECONDS)`: how the **value `30`** is interpreted.

Changing `@DurationUnit` from `SECONDS` to `MILLIS` does not rename the key; it changes how bare numbers are interpreted.

Changing the prefix from `remote.client` to `remote.gateway` does not change the unit; it changes where the binder looks up values.

Renaming the member from `connectTimeout` to `connectionTimeout` does not change the unit; however, it changes the canonical key name that must be supplied.

Do not mix all three changes in one configuration edit without a compatibility plan.

## 22. Diagnosing When Duration Differs from Expectations

When a result is too short, too long, or wrong, inspect in order.

### Step 1: Check Whether the Source Value Has a Suffix

~~~text
timeout=30
timeout=30s
timeout=30000ms
~~~

These three forms do not behave identically when unit annotations change. Determine the actual string received by the binder after sources are merged.

### Step 2: Check Whether the Field/Parameter Has @DurationUnit

~~~java
@DurationUnit(ChronoUnit.SECONDS)
Duration timeout;
~~~

If absent, bare numbers default to ms in `Duration` binding.

If the annotation sits on another class not used for the current binding, it has no effect on this conversion path.

### Step 3: Identify the Binding Type

- JavaBean field and setter.
- Constructor parameter.
- Record component.
- `@Bean @ConfigurationProperties` attached to a mutable instance.
- Direct `Environment.getProperty(..., Duration.class)` lookup.
- `@Value`.

Do not assume annotation metadata applies on read paths that do not use the properties binder.

### Step 4: Check Higher-Precedence Sources

If the file has `30s` but CLI has `--app.timeout=10`, the binder can receive the bare number `10` from CLI and then apply the unit from the annotation.

### Step 5: Inspect Using Explicit Units

In a test app with non-sensitive values:

~~~java
Duration timeout = properties.timeout();

System.out.println("timeout ISO = " + timeout);
System.out.println("timeout ms  = " + timeout.toMillis());
System.out.println("timeout sec = " + timeout.getSeconds());
~~~

Use conversion methods to verify the exact value. Do not look only at `Duration.toString()` and assume the source had a suffix matching the printed output.

### Step 6: Check When Passed to Another API

If the properties bean holds 30 seconds correctly yet the HTTP client still times out after 30 ms, the bug may lie in the API call—for example passing `getSeconds()` to a method expecting milliseconds. `@DurationUnit` did its job at the binding layer; the bug occurred afterward.

## 23. Common Mistakes

### Mistake 1 — Thinking 30 Is Always 30 Seconds

~~~properties
app.timeout=30
~~~

Without a unit annotation, `Duration` can be 30 ms. If you want 30 seconds, write `30s` or place `@DurationUnit(SECONDS)` on the right field/parameter.

### Mistake 2 — Adding @DurationUnit Thinking It Supplies a Default Value

~~~java
@DurationUnit(ChronoUnit.SECONDS)
Duration timeout;
~~~

If `app.timeout` is missing, the annotation has no number to convert. Define the default value using a field initializer, `@DefaultValue`, or an appropriate binding mechanism.

### Mistake 3 — Thinking the Annotation Overrides Explicit Suffixes

~~~java
@DurationUnit(ChronoUnit.SECONDS)
Duration timeout;
~~~

~~~properties
app.timeout=500ms
~~~

The result is still 500 ms.

### Mistake 4 — Using long and Expecting @DurationUnit to Create a Duration

~~~java
long timeout;
~~~

`@DurationUnit` is designed to change the unit when converting to **Duration**. If you only use `long`, you must define the unit and convert to `Duration` with your own logic.

### Mistake 5 — Changing long Seconds to Duration and Forgetting the Annotation

Previously `timeoutSeconds=30` meant 30 seconds. After changing to `Duration` without `@DurationUnit(SECONDS)`, the bare number `30` can mean 30 ms. This is a classic migration bug.

### Mistake 6 — Misusing the m Suffix

~~~properties
app.timeout=3m
~~~

With `Duration`, the value is 3 **minutes**, not 3 months.

### Mistake 7 — Thinking @Value Picks Up @DurationUnit from Another Class

If a service uses `@Value("${app.timeout}")` while another properties bean has a unit annotation, do not assume the injected value follows that other bean's annotation. Use the properties bean consistently or write suffixes in the source.

### Mistake 8 — Not Registering @ConfigurationProperties

A class merely annotated with `@ConfigurationProperties` is not automatically a bean. Register it via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` in the appropriate context if you want the Spring binder to create the configuration bean.

### Mistake 9 — Using Duration Units for DataSize or Period

`@DurationUnit` is not `@DataSizeUnit` or `@PeriodUnit`. A single letter `m` means different things depending on the Java type.

### Mistake 10 — Failing to Validate Business Bounds

The binder can convert a duration that makes no sense for the application. Add validation for positive timeouts, upper limits, and compatibility with consuming APIs.

### Mistake 11 — Assuming toMillis() Preserves Full Precision

If a `Duration` has microsecond/nanosecond parts, converting to integer milliseconds can drop the sub-millisecond remainder. Keep `Duration` up to the usage boundary whenever possible.

### Mistake 12 — Changing the Default Unit Between Versions Without Notice

If an application has a bare configuration `30000` meaning 30 seconds under the ms default, and code later adds `@DurationUnit(SECONDS)` while keeping the old value, the data becomes 30,000 seconds. Changing the annotation must be paired with a plan to update or preserve configuration semantics.

## 24. Testing Duration Binding

A practical approach is writing Spring Boot tests with test-specific configuration properties.

Suppose the bean is:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "demo.timing")
public record TimingProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration timeout,
        Duration interval) {
}
~~~

and the application has `@ConfigurationPropertiesScan` enabled.

### 24.1. Testing Bare Numbers

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
        "demo.timing.timeout=30",
        "demo.timing.interval=30"
})
class TimingBindingTest {

    @Autowired
    TimingProperties properties;

    @Test
    void distinguishesDefaultUnits() {
        assertEquals(
                Duration.ofSeconds(30),
                properties.timeout());

        assertEquals(
                Duration.ofMillis(30),
                properties.interval());
    }
}
~~~

Despite the identical source value `30`, the two fields have different default units.

### 24.2. Testing Explicit Suffixes

You can create another test class:

~~~java
@SpringBootTest(properties = {
        "demo.timing.timeout=250ms",
        "demo.timing.interval=2s"
})
class ExplicitUnitBindingTest {

    @Autowired
    TimingProperties properties;

    @Test
    void explicitUnitsAreRespected() {
        assertEquals(
                Duration.ofMillis(250),
                properties.timeout());

        assertEquals(
                Duration.ofSeconds(2),
                properties.interval());
    }
}
~~~

The unit annotation on `timeout` does not turn `250ms` into 250 seconds; `interval` has no annotation yet still understands `2s` as two seconds.

### 24.3. Testing Defaults When Keys Are Missing

With constructor binding using `@DefaultValue("5s")`, omit the corresponding key and assert the result is `Duration.ofSeconds(5)`. This tests the **default value**, independent of testing the default unit for bare numbers.

### 24.4. Testing Migration

If the legacy system had `timeout-seconds=60`, write a verification test:

~~~java
assertEquals(
        Duration.ofSeconds(60),
        properties.timeoutSeconds());
~~~

while the source still passes `60`. This test catches unintended unit changes when switching a field from `long` to `Duration`.

## 25. Value Prediction Exercises

### Exercise 1 — No @DurationUnit

~~~java
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(Duration timeout) {
}
~~~

~~~properties
service.timeout=1000
~~~

How long is `timeout`?

**Answer:** 1,000 ms, or 1 second. `1000` is a bare number and the default unit for `Duration` binding is ms.

### Exercise 2 — With @DurationUnit(SECONDS)

~~~java
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration timeout) {
}
~~~

~~~properties
service.timeout=1000
~~~

**Answer:** 1,000 seconds. It is no longer 1 second, because the annotation specifies seconds for bare numbers.

### Exercise 3 — Suffix Beats Default Unit

Keep `@DurationUnit(ChronoUnit.SECONDS)` but use:

~~~properties
service.timeout=1000ms
~~~

**Answer:** 1 second. The `ms` suffix is an explicit unit.

### Exercise 4 — ISO-8601

~~~properties
service.timeout=PT1M30S
~~~

**Answer:** 90 seconds. The annotation does not need to infer a unit from a bare number.

### Exercise 5 — Two Different Durations

~~~java
@ConfigurationProperties(prefix = "jobs")
public record JobProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        Duration executionTimeout,
        Duration pollInterval) {
}
~~~

~~~yaml
jobs:
  execution-timeout: 5
  poll-interval: 5
~~~

**Answer:** `executionTimeout` is 5 seconds; `pollInterval` is 5 milliseconds.

### Exercise 6 — Overriding via CLI

YAML:

~~~yaml
jobs:
  execution-timeout: 15s
~~~

CLI:

~~~bash
java -jar app.jar --jobs.execution-timeout=20
~~~

With `@DurationUnit(ChronoUnit.SECONDS)` on the member:

**Answer:** 20 seconds from the higher-precedence CLI source, interpreted by the binder using the annotation's unit.

### Exercise 7 — Suffixed Durations in YAML

~~~yaml
jobs:
  retry-delay: 500ms
  cache-ttl: 2h
  timeout: 30s
~~~

With corresponding `Duration` fields, these are 500 ms, 2 hours, and 30 seconds respectively—no unit annotations are needed to interpret these three values.

### Exercise 8 — Distinguishing @DefaultValue and @DurationUnit

~~~java
public JobProperties(
        @DurationUnit(ChronoUnit.MINUTES)
        @DefaultValue("2m")
        Duration cacheTtl) {
    this.cacheTtl = cacheTtl;
}
~~~

Cases:

| Configuration | Result |
| --- | --- |
| Missing `cache-ttl` key | 2 minutes via `@DefaultValue`. |
| `cache-ttl=10` | 10 minutes via `@DurationUnit(MINUTES)`. |
| `cache-ttl=30s` | 30 seconds because of the explicit suffix. |
| `cache-ttl=PT1H` | 1 hour per ISO-8601. |

### Exercise 9 — Spotting a Migration Bug

A legacy project uses `long timeoutSeconds` with value `30`; old code runs `Duration.ofSeconds(timeoutSeconds)`. Later the field type changes to `Duration` while keeping `30`.

**Answer:** without adding `@DurationUnit(SECONDS)` or updating the source to `30s`, the meaning risks changing from 30 seconds to 30 milliseconds.

### Exercise 10 — Distinguishing Types

Given the same string `3m`:

- Bound to `Duration`: 3 minutes.
- Bound to `Period` in simple style: 3 months.

**Answer:** do not treat `3m` as a universal unit independent of the target type.

## 26. Guidelines for Resilient Configuration Design

When designing new modules, apply these principles:

### 26.1. Prefer Descriptive Key Names

~~~yaml
http:
  client:
    connect-timeout: 5s
    read-timeout: 30s
~~~

The names `connect-timeout` and `read-timeout` clarify business intent. The `s` clarifies the unit.

### 26.2. Prefer Suffixed Values in New Data

~~~yaml
jobs:
  retry-delay: 200ms
  execution-timeout: 2m
~~~

The file can be read and understood without opening Java source code to inspect annotations.

### 26.3. Use @DurationUnit for Bare-Number Contracts

When multiple systems already provide `timeout=30` meaning 30 seconds, `@DurationUnit(SECONDS)` preserves that meaning when binding to `Duration`.

### 26.4. Use Explicit Default Values for Missing Keys

If an application must have a 10-second timeout when unconfigured, declare a default value with an explicit unit rather than hoping `@DurationUnit` supplies `10` on its own.

### 26.5. Validate Conversion and Business Values

Non-positive timeouts, abnormally large values, or values incompatible with an API should be caught by validation or startup check code.

### 26.6. Keep Duration as Close to the Usage Boundary as Possible

If an API accepts `Duration`, pass it directly. If an API only takes a number, convert to the unit it requires and check for precision-loss/overflow risks.

### 26.7. Test Both Bare Numbers and Suffixed Values

One test with `30` and one test with `500ms` is a simple way to catch mistakes with `@DurationUnit`.

## 27. Summary Table

| Question | Rule |
| --- | --- |
| What is bare `30` bound to `Duration` by default? | 30 milliseconds. |
| What does `@DurationUnit(SECONDS)` change? | Bare `30` on that member becomes 30 seconds. |
| Does `@DurationUnit` turn `500ms` into 500 seconds? | No. The explicit `ms` suffix is respected. |
| Do `30s` and `PT30S` produce the same `Duration`? | Yes, both equal 30 seconds when bound properly. |
| Does a missing key with `@DurationUnit(SECONDS)` give 30 seconds? | No; a separate default value is required. |
| Are JavaBean field defaults and `@DefaultValue` the same as unit annotations? | No; they supply **values** when keys are missing. |
| Does `@DurationUnit` apply to every `Environment.getProperty(..., Duration.class)`? | Metadata from another properties bean does not carry over to standalone calls. |
| What is `3m` for `Duration`? | 3 minutes, not 3 months. |
| What to watch out for when migrating `long timeoutSeconds` to `Duration`? | Preserve the seconds unit contract via annotation or update sources. |
| Are suffixes required in the file when using the annotation? | Not required, but suffixes make the file self-describing. |

## 28. Conclusion

In Spring Boot, **suffixless duration numbers bound to `Duration` default to milliseconds**. The `@DurationUnit` annotation changes the default unit **for the corresponding field or constructor parameter**, for example from milliseconds to seconds or minutes. When the source already writes `500ms`, `30s`, `2m`, or `PT30S`, the expression itself carries an explicit unit and needs no annotation guesswork.

More importantly, distinguish:

1. **Default unit**: how a bare number like `30` is interpreted (ms, s, or m).
2. **Default value**: what value is used when **the property is absent**.
3. **Effective value**: chosen by `Environment` across YAML, Properties, environment variables, System properties, and CLI.
4. **Business-valid value**: required by validation and the consuming API.

For new configurations, write `30s` or `500ms` so readers never have to guess. For legacy configurations using bare numbers, `@DurationUnit` is a valuable tool for preserving units while upgrading your design to `Duration`. After binding, keep `Duration` typed and only convert to a number when a downstream API demands a specific unit.

## References

- [Spring Boot 3.3 — Externalized Configuration, Converting Durations](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion).
- [Spring Boot — DurationUnit API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/DurationUnit.html).
- [Java — Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html).
- [Java — ChronoUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoUnit.html).