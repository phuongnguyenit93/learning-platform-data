# Configuring Time Durations with Duration

## 1. Lesson Objectives

In a Spring Boot application, many configuration values represent **a time duration**: connection timeouts, request timeouts, retry delays, cache lifetimes, intervals between checks, or session idle timeouts.

A common legacy approach is storing these values as numbers:

~~~properties
client.connect-timeout=5000
client.retry-delay=1000
~~~

However, the numbers **5000** and **1000** do not specify whether they represent milliseconds or seconds. When moving to another system or revisiting the file months later, operators can easily misread the unit.

Spring Boot includes **configuration properties conversion** specifically for **java.time.Duration**. As a result, configuration can be written clearly:

~~~properties
client.connect-timeout=5s
client.retry-delay=250ms
client.session-timeout=30m
~~~

Java code uses the **Duration** type instead of parsing strings into numbers manually.

After this lesson, you will be able to:

- Understand what **Duration** represents and how it differs from **Period** and **LocalDateTime**.
- Write duration values in the three formats supported by Spring Boot.
- Distinguish the **ns**, **us**, **ms**, **s**, **m**, **h**, and **d** suffixes.
- Know that **unitless numeric values default to milliseconds**, unless **@DurationUnit** is declared.
- Declare **@ConfigurationProperties** using `Duration` via Java records or JavaBeans.
- Combine **@DefaultValue**, **@DurationUnit**, validation, and external configuration sources.
- Read durations from YAML, properties, environment variables, and startup arguments.
- Avoid conversion errors, unit mix-ups, and invalid values.
- Write tests to verify that configuration binds properly.

The examples use **Spring Boot 3.3.x** and **Java 21** as their context.

## 2. What Does Duration in Java Represent?

**java.time.Duration** is a type from the Java Time API used to represent **an amount of time** based on seconds and nanoseconds, rather than a specific calendar date or instant.

Several ways to create a `Duration` in Java:

~~~java
import java.time.Duration;

Duration connectTimeout = Duration.ofSeconds(5);
Duration retryDelay = Duration.ofMillis(250);
Duration sessionTimeout = Duration.ofMinutes(30);
Duration backoff = Duration.ofHours(2);
Duration oneDay = Duration.ofDays(1);
~~~

Commonly used methods:

~~~java
Duration timeout = Duration.ofSeconds(5);

long milliseconds = timeout.toMillis();   // 5000
long seconds = timeout.getSeconds();       // 5
boolean zero = timeout.isZero();           // false
boolean negative = timeout.isNegative();   // false

Duration doubled = timeout.multipliedBy(2);
Duration total = timeout.plusMillis(500);
~~~

**Duration** does not open network connections, schedule jobs, or pause the application on its own. It is **a value describing an amount of time**. The consuming component—such as an HTTP client or scheduler—decides how to apply it.

For example, if a property named **retry-delay** is **500ms**, retry logic can use that value to decide how long to wait. If it is **connect-timeout**, an HTTP client can use the same `Duration` type with an entirely different meaning.

### 2.1. Duration Differs from Instants and Calendar Dates

| Java Type | Purpose |
| --- | --- |
| **Duration** | An amount of time measured in time units, such as 5 seconds or 2 hours |
| **Period** | A calendar-based span, such as 2 months or 3 days |
| **Instant** | A point on the timeline |
| **LocalDateTime** | Local date and time, without a timezone |
| **ZonedDateTime** | Date and time with a timezone |

**Duration.ofDays(1)** is an interval of **24 hours**. If a business requirement says "tomorrow at the same local time", that can differ from 24 hours in environments with daylight saving time changes. When working with calendar rules, consider **Period**, **LocalDate**, **ZonedDateTime**, or corresponding calendar APIs.

For timeouts, retry delays, and technical wait intervals, **Duration** is typically the right type.

## 3. Three Ways Spring Boot Accepts Duration Values

When binding a property to **Duration** via **@ConfigurationProperties**, Spring Boot supports three key representations.

### 3.1. Plain Integer

~~~properties
demo.client.connect-timeout=5000
~~~

Without another unit configuration, **5000** is interpreted as **5000 milliseconds**, equivalent to **5 seconds**.

This syntax is concise but error-prone. Looking at the number alone does not reveal what unit the author intended.

### 3.2. ISO-8601 Standard

~~~properties
demo.client.connect-timeout=PT5S
demo.client.session-timeout=PT30M
demo.client.long-timeout=PT2H
~~~

ISO-8601 strings use the syntax supported by **java.time.Duration**:

- **PT5S**: 5 seconds.
- **PT30M**: 30 minutes.
- **PT2H**: 2 hours.
- **PT1H30M**: 1 hour and 30 minutes.
- **PT0.5S**: half a second.

This form is useful when systems or tools need a standardized representation that can be passed across platforms.

### 3.3. Human-Readable Value with a Unit Suffix

~~~properties
demo.client.connect-timeout=5s
demo.client.retry-delay=250ms
demo.client.session-timeout=30m
demo.client.maintenance-delay=2h
~~~

This is the most convenient form for most Spring Boot applications: readers immediately see that **5s** is five seconds and **250ms** is 250 milliseconds.

**There is no need to manually parse strings with Duration.parse(...)** in a configuration class using **@ConfigurationProperties**. The Spring Boot binder has its own conversion mechanism to understand all of the forms above, including **5s**, which is a readable format rather than Java's ISO-8601 syntax.

## 4. Table of Units Supported by Spring Boot

According to Spring Boot 3.3 documentation, simple-style suffixes include:

| Suffix | Unit | Example | Meaning |
| --- | --- | --- | --- |
| **ns** | Nanosecond | **100ns** | 100 nanoseconds |
| **us** | Microsecond | **50us** | 50 microseconds |
| **ms** | Millisecond | **500ms** | Half a second |
| **s** | Second | **10s** | 10 seconds |
| **m** | Minute | **15m** | 15 minutes |
| **h** | Hour | **2h** | 2 hours |
| **d** | Day | **3d** | 3 days, equivalent to 72 hours |

Points to remember:

- **ms** is milliseconds, **m** is minutes. These two suffixes cannot be used interchangeably.
- **us** is microseconds, **ns** is nanoseconds.
- **h** represents hours and **d** represents a duration measured in 24-hour days.
- Keep suffixes in the exact documented form, especially when values flow across multiple systems.
- Do not assume that suffixes like **w** (weeks), **mo** (months), or **y** (years) are valid for `Duration`. For calendar units such as months and years, look at **Period**.
- Do not combine multiple unit pairs in one simple-style string like **1h30m** and assume it will be supported. Use **PT1H30M** in ISO-8601, or write **90m** when appropriate.

### 4.1. Equivalent Duration Strings

| Numeric Form | ISO Form | Suffixed Form | Duration |
| --- | --- | --- | --- |
| **500** | **PT0.5S** | **500ms** | Half a second |
| **1000** | **PT1S** | **1s** | One second |
| **5000** | **PT5S** | **5s** | Five seconds |
| **60000** | **PT1M** | **1m** | One minute |
| **3600000** | **PT1H** | **1h** | One hour |

**The table assumes the default unit is milliseconds.** If the field or constructor parameter is annotated with **@DurationUnit(ChronoUnit.SECONDS)**, plain numbers must be interpreted in the new unit.

## 5. Default for Suffixless Numbers: Milliseconds

This is the most important rule when migrating legacy systems to `Duration`.

Suppose the record is:

~~~java
package com.example.duration;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.client")
public record ClientTimeoutProperties(
        Duration connectTimeout) {
}
~~~

If the configuration file specifies:

~~~properties
demo.client.connect-timeout=30
~~~

then **connectTimeout** is interpreted as **30 milliseconds**, not 30 seconds.

If the actual intent is 30 seconds, clarify it explicitly:

~~~properties
demo.client.connect-timeout=30s
~~~

Or:

~~~properties
demo.client.connect-timeout=PT30S
~~~

A typical deployment mistake:

~~~text
Intent:     30-second timeout
Config:     30
Result:     30 milliseconds
Impact:     requests time out unexpectedly
~~~

**Recommendation in new configurations:** always include the unit suffix in the file or environment variable, even when the default is milliseconds. For example, **500ms** is clearer than **500**.

## 6. Changing the Default Unit with @DurationUnit

Sometimes legacy projects already use plain numbers meaning **seconds**:

~~~properties
legacy.session-timeout=30
~~~

If you change the property type from **long** to **Duration** without announcing a syntax change, Spring Boot will interpret **30** as 30 milliseconds. To preserve the legacy meaning, you can use **@DurationUnit**.

Annotation:

~~~java
import org.springframework.boot.convert.DurationUnit;
import java.time.temporal.ChronoUnit;
~~~

Example of a JavaBean with a field and getter/setter:

~~~java
package com.example.duration;

import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "legacy")
public class LegacySessionProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration sessionTimeout = Duration.ofSeconds(30);

    public Duration getSessionTimeout() {
        return sessionTimeout;
    }

    public void setSessionTimeout(Duration sessionTimeout) {
        this.sessionTimeout = sessionTimeout;
    }
}
~~~

With the class above:

~~~properties
legacy.session-timeout=30
~~~

means **30 seconds**, because the field is annotated with **@DurationUnit(ChronoUnit.SECONDS)**.

However:

~~~properties
legacy.session-timeout=500ms
~~~

is still **500 milliseconds** because the string already has an explicit unit suffix. **@DurationUnit** changes the **default unit when none is stated**; it does not override an explicitly declared suffix.

### 6.1. Placing @DurationUnit on a Constructor Parameter

Spring Boot 3.3 also supports constructor binding. Example using an immutable class:

~~~java
package com.example.duration;

import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "demo.session")
public class SessionProperties {

    private final Duration sessionTimeout;
    private final Duration readTimeout;

    public SessionProperties(
            @DurationUnit(ChronoUnit.SECONDS)
            @DefaultValue("30s") Duration sessionTimeout,
            @DefaultValue("1000ms") Duration readTimeout) {
        this.sessionTimeout = sessionTimeout;
        this.readTimeout = readTimeout;
    }

    public Duration getSessionTimeout() {
        return sessionTimeout;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }
}
~~~

Values:

~~~properties
demo.session.session-timeout=60
demo.session.read-timeout=500
~~~

will be interpreted as:

~~~text
sessionTimeout -> 60 seconds
readTimeout    -> 500 milliseconds
~~~

**@DurationUnit** is attached to **sessionTimeout**, not to the entire class or every `Duration` field.

### 6.2. When Should You Use @DurationUnit?

Consider **@DurationUnit** when:

- Migrating from a legacy numeric property whose implicit unit is not milliseconds.
- Maintaining compatibility with deployment tooling that always passes plain numbers in seconds or minutes.
- A public configuration API has an explicit contract that suffixless numbers are interpreted in a specific unit.

For new configuration, the clearest approach is still usually placing suffixes such as **5s**, **250ms**, and **2m** directly in the file.

## 7. Declaring Duration Configuration in application.yml

A payment-processing application might need:

- Connection timeout.
- Request timeout.
- Delay before the next retry.
- Session idle timeout.

YAML configuration:

~~~yaml
demo:
  client:
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      initial-delay: 250ms
      max-delay: 5s

  session:
    idle-timeout: 30m
~~~

Corresponding flat property names:

~~~text
demo.client.connect-timeout
demo.client.request-timeout
demo.client.retry.initial-delay
demo.client.retry.max-delay
demo.session.idle-timeout
~~~

Values like **2s** or **30m** are held as text/scalars in Config Data and converted to **Duration** when bound to the target type.

To keep configuration clear when values are complex or contain spaces, you can use quotes in YAML:

~~~yaml
demo:
  client:
    request-timeout: "PT10S"
    connect-timeout: "2s"
~~~

For ordinary simple-style durations, quotes are not required, though using them consistently can help prevent unintended scalar interpretations.

### 7.1. application.properties Version

~~~properties
demo.client.connect-timeout=2s
demo.client.request-timeout=10s
demo.client.retry.initial-delay=250ms
demo.client.retry.max-delay=5s
demo.session.idle-timeout=30m
~~~

YAML and properties are two ways of representing the same set of keys. Do not declare two files with the same name and conflicting values without understanding Spring Boot's Config Data precedence rules.

## 8. Java Records with Duration and Nested Configuration

Assume an app using Java 21, Spring Boot 3.3.x, and the **spring-boot-starter-web** dependency.

A configuration properties record:

~~~java
package com.example.duration;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.client")
public record ClientProperties(
        @DefaultValue("2s") Duration connectTimeout,
        @DefaultValue("10s") Duration requestTimeout,
        Retry retry) {

    public record Retry(
            @DefaultValue("250ms") Duration initialDelay,
            @DefaultValue("5s") Duration maxDelay) {
    }
}
~~~

With the YAML from the previous section, Spring Boot binds:

~~~text
ClientProperties
  connectTimeout = PT2S
  requestTimeout = PT10S
  retry
    initialDelay = PT0.25S
    maxDelay     = PT5S
~~~

**@DefaultValue** takes effect when the corresponding property is not provided for constructor binding. It does not mean every missing configuration is valid; for nested objects, whether the child object is created also depends on whether data is present or an appropriate default nested binding is declared.

If **retry** is required, use validation or require all properties. If you want the nested record to always be created even when no properties exist in that branch, Spring Boot supports specifying an empty default on the nested constructor parameter to request nested object creation combined with defaults for inner fields.

### 8.1. Registering @ConfigurationPropertiesScan

~~~java
package com.example.duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DurationApplication {

    public static void main(String[] args) {
        SpringApplication.run(DurationApplication.class, args);
    }
}
~~~

With the app class in package **com.example.duration**, the **ClientProperties** record in the same package is discovered by scanning.

An alternative:

~~~java
@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class DurationApplication {
    public static void main(String[] args) {
        SpringApplication.run(DurationApplication.class, args);
    }
}
~~~

The alternative requires importing **org.springframework.boot.context.properties.EnableConfigurationProperties**. The two registration styles—**scan** and **enable**—do not need to be combined.

With constructor binding/records, do not merely put **@Component** on the record and expect Spring Boot to automatically bind constructor parameters as properties.

## 9. Example Reading Converted Configuration

To observe the result, you can use a simple REST controller:

~~~java
package com.example.duration;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DurationController {

    private final ClientProperties properties;

    public DurationController(ClientProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/duration-demo")
    public Map<String, Object> read() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("connectTimeoutMs",
                properties.connectTimeout().toMillis());
        result.put("requestTimeoutSeconds",
                properties.requestTimeout().getSeconds());
        result.put("retryInitialDelayMs",
                properties.retry().initialDelay().toMillis());
        result.put("retryMaxDelayMs",
                properties.retry().maxDelay().toMillis());
        return result;
    }
}
~~~

With the configuration:

~~~yaml
demo:
  client:
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      initial-delay: 250ms
      max-delay: 5s
~~~

calling:

~~~bash
curl http://localhost:8080/duration-demo
~~~

yields the illustrative output:

~~~json
{
  "connectTimeoutMs": 2000,
  "requestTimeoutSeconds": 10,
  "retryInitialDelayMs": 250,
  "retryMaxDelayMs": 5000
}
~~~

The controller only demonstrates converting and reading `Duration`. It does not perform real network requests or scheduling, so the values introduce no external infrastructure dependencies.

**In production applications, never expose an endpoint that returns sensitive configuration.** This example only contains mock timeouts and delays.

## 10. Supplying Duration via Environment Variables

Configuring outside the JAR is one of Spring Boot's primary strengths. You can change timeout values of the same artifact at deployment time.

Canonical names:

~~~text
demo.client.connect-timeout
demo.client.request-timeout
demo.client.retry.initial-delay
demo.client.retry.max-delay
~~~

Corresponding environment variables under relaxed binding:

~~~text
DEMO_CLIENT_CONNECTTIMEOUT
DEMO_CLIENT_REQUESTTIMEOUT
DEMO_CLIENT_RETRY_INITIALDELAY
DEMO_CLIENT_RETRY_MAXDELAY
~~~

Rule for converting from canonical name to environment variable:

1. Replace dots **.** with underscores **_**.
2. Remove hyphens **-**.
3. Uppercase the name.

The value after the **=** sign still uses `Duration` syntax:

~~~bash
DEMO_CLIENT_CONNECTTIMEOUT=5s \
DEMO_CLIENT_REQUESTTIMEOUT=15s \
DEMO_CLIENT_RETRY_INITIALDELAY=500ms \
DEMO_CLIENT_RETRY_MAXDELAY=8s \
java -jar app.jar
~~~

With PowerShell:

~~~powershell
$env:DEMO_CLIENT_CONNECTTIMEOUT = "5s"
$env:DEMO_CLIENT_REQUESTTIMEOUT = "15s"
$env:DEMO_CLIENT_RETRY_INITIALDELAY = "500ms"
$env:DEMO_CLIENT_RETRY_MAXDELAY = "8s"
java -jar app.jar
~~~

The key point is that **the unit lives in the value**, not in the environment variable name. The name **DEMO_CLIENT_CONNECTTIMEOUT** works for **5s**, **5000ms**, or **PT5S**.

### 10.1. Command-Line Arguments

~~~bash
java -jar app.jar \
  --demo.client.connect-timeout=5s \
  --demo.client.request-timeout=15s
~~~

This command uses the same canonical keys as Config Data. When command-line properties are enabled in standard Spring Boot configuration, they have high precedence for matching keys.

### 10.2. Java System Properties

~~~bash
java \
  -Ddemo.client.connect-timeout=5s \
  -Ddemo.client.request-timeout=15s \
  -jar app.jar
~~~

Remember to place **-D** arguments before **-jar**.

**You do not need to rebuild the JAR** just to adjust a `Duration` if the application reads configuration via externalized configuration.

## 11. How Does Source Precedence Affect Duration?

Suppose:

**application.yml**:

~~~yaml
demo:
  client:
    connect-timeout: 2s
~~~

**application-prod.yml**:

~~~yaml
demo:
  client:
    connect-timeout: 4s
~~~

Environment variable:

~~~text
DEMO_CLIENT_CONNECTTIMEOUT=6s
~~~

Command-line argument:

~~~text
--demo.client.connect-timeout=8s
~~~

If the **prod** profile is active and all of these sources are supplied simultaneously under normal Spring Boot settings, higher-precedence sources override lower ones. Command-line arguments typically win for this key, so **ClientProperties.connectTimeout()** receives 8 seconds.

**The binder does not add durations together.** It selects the property value according to precedence and converts **the final value** to `Duration`.

Therefore:

~~~text
application.yml          2s
application-prod.yml     4s
environment variable     6s
command line             8s
--------------------------------
Example result           Duration.ofSeconds(8)
~~~

If you omit the command-line argument while keeping the environment variable, you can get 6 seconds. If you omit both env and argument, profile-specific Config Data can determine the value.

### 11.1. Clear Units Make Overrides Safe

Avoid writing:

~~~yaml
demo:
  client:
    connect-timeout: 2000
~~~

and then supplying:

~~~text
DEMO_CLIENT_CONNECTTIMEOUT=4
~~~

expecting 4 seconds. Without a special **@DurationUnit**, **4** is only **4 milliseconds**.

Supply:

~~~text
DEMO_CLIENT_CONNECTTIMEOUT=4s
~~~

## 12. Using @DurationUnit in Records and Constructor Binding

For projects using Java records that need to **override the default unit** for a `Duration` field, you can illustrate it on a record component:

~~~java
package com.example.duration;

import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "demo.timeout")
public record TimeoutProperties(
        @DurationUnit(ChronoUnit.SECONDS)
        @DefaultValue("30s") Duration session,
        @DefaultValue("500ms") Duration read) {
}
~~~

If Spring Boot binds:

~~~properties
demo.timeout.session=45
demo.timeout.read=600
~~~

then:

~~~text
session = 45 seconds
read    = 600 milliseconds
~~~

Whereas if configured as:

~~~properties
demo.timeout.session=500ms
~~~

then `Duration` is still 500 milliseconds, because the suffix is stated explicitly.

**@DurationUnit is not an annotation to constrain the magnitude of a duration.** It only affects how unitless values are interpreted. If you need to verify that a timeout is greater than 0, use validation or appropriate guard logic.

## 13. Duration in Java Should Not Be Handled as an Arbitrary String

Example of a risky pattern:

~~~java
String rawTimeout = environment.getProperty(
        "demo.client.connect-timeout");
long timeout = Long.parseLong(rawTimeout);
~~~

This snippet fails if the configuration is **5s**, and even when using **5000**, the code still has to decide the unit manually.

Replace it with a typed model:

~~~java
@ConfigurationProperties(prefix = "demo.client")
public record ClientProperties(Duration connectTimeout) {
}
~~~

After binding:

~~~java
Duration timeout = properties.connectTimeout();
~~~

This creates one consistent contract across YAML, properties, env, and CLI.

If you only need to look up a single key without creating a configuration properties bean, **Environment** has a typed lookup overload:

~~~java
Duration timeout = environment.getProperty(
        "demo.client.connect-timeout",
        Duration.class);
~~~

`Environment`'s type conversion depends on the active `ConversionService`, whereas `Duration` conversion is explicitly documented by Spring Boot for **@ConfigurationProperties Binder**. For complex `Duration` values or when you want consistent validation and defaults, **@ConfigurationProperties** is preferred.

## 14. Configuring Durations in a JavaBean with Setters

Not every application uses records. A mutable class can still bind `Duration`:

~~~java
package com.example.duration;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.polling")
public class PollingProperties {

    private Duration interval = Duration.ofSeconds(10);
    private Duration initialDelay = Duration.ofSeconds(2);

    public Duration getInterval() {
        return interval;
    }

    public void setInterval(Duration interval) {
        this.interval = interval;
    }

    public Duration getInitialDelay() {
        return initialDelay;
    }

    public void setInitialDelay(Duration initialDelay) {
        this.initialDelay = initialDelay;
    }
}
~~~

Configuration:

~~~yaml
demo:
  polling:
    interval: 15s
    initial-delay: 3s
~~~

If no values are provided for these properties, the JavaBean has fields initialized to **Duration.ofSeconds(10)** and **Duration.ofSeconds(2)**.

Comparison:

- **JavaBean setters**: can initialize defaults directly on the fields.
- **Record/constructor binding**: can use **@DefaultValue** on the component or parameter.
- **YAML configuration**: can also keep shared default values right in Config Data.

There is no need to combine every default-setting style on the same field. Pick one clear strategy.

## 15. @DefaultValue for Duration in Constructor Binding

Example:

~~~java
package com.example.duration;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.job")
public record JobProperties(
        @DefaultValue("5s") Duration startupDelay,
        @DefaultValue("1m") Duration runInterval) {
}
~~~

If the properties are absent:

~~~text
demo.job.startup-delay
demo.job.run-interval
~~~

then the record can be constructed with:

~~~text
startupDelay = 5 seconds
runInterval  = 1 minute
~~~

You should include **the unit suffix in @DefaultValue**, especially when readers may not know the bare-number rule.

`@DefaultValue` annotations can be combined with `@DurationUnit` when supporting suffixless numbers from configuration sources. However, with defaults written explicitly as **5s** or **1m**, the meaning does not depend on an implicit unit.

### 15.1. Missing Values and null

If a `Duration` record component is not provided and has no default, that component can receive **null** depending on binding conditions. If subsequent code calls **timeout.toMillis()**, a `NullPointerException` can occur.

Use **@NotNull** validation, a sensible default, or fail-fast behavior depending on the application contract.

## 16. Validation for Time Durations

A `Duration` that parses successfully **does not mean** it is valid for every purpose.

For example:

~~~yaml
demo:
  client:
    connect-timeout: -5s
    request-timeout: 0s
~~~

As a duration concept, `Duration` can represent negative numbers and zero. However, an HTTP client may require a positive timeout or attach a special meaning to 0; an excessively large value may also be unsuitable.

### 16.1. @NotNull for Required Fields

If the project has the dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

you can use:

~~~java
package com.example.duration;

import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.client")
public record ValidatedTimeoutProperties(
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout) {
}
~~~

When a required property is absent, validation can report an error during context initialization.

**This is an alternative illustrative type** to `ClientProperties`; do not register both under the same prefix in a single exercise project.

### 16.2. Checking Positivity with Custom Logic

Bean Validation **@Min** and **@Positive** are generally intended for numeric types; do not assume they work directly on **Duration** without a validator supporting that type.

A simple approach is checking when creating the bean that consumes the configuration:

~~~java
public static Duration requirePositive(
        Duration value,
        String propertyName) {

    if (value == null || value.isZero() || value.isNegative()) {
        throw new IllegalArgumentException(
                propertyName + " must be positive");
    }
    return value;
}
~~~

Usage:

~~~java
Duration connectTimeout = requirePositive(
        properties.connectTimeout(),
        "demo.client.connect-timeout");
~~~

In larger projects, you can create a **custom Bean Validation constraint** for `Duration` to keep constraints directly on the configuration model.

### 16.3. Zero Can Have Special Meanings

Some frameworks or clients interpret **0** as "unlimited" or "disable timeout", whereas some APIs treat zero as no wait. Do not make one blanket assumption across all libraries.

When designing a property like **connect-timeout**, clearly document:

- Supported units and formats.
- Whether **0s** is accepted.
- Whether negative values are forbidden.
- Appropriate upper limits.
- Whether disabling the timeout is allowed, and which syntax achieves it.

## 17. Using Duration in Business Logic

Suppose a service computes retry delays:

~~~java
package com.example.duration;

import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class RetryDelayService {

    private final ClientProperties properties;

    public RetryDelayService(ClientProperties properties) {
        this.properties = properties;
    }

    public Duration initialDelay() {
        return properties.retry().initialDelay();
    }

    public Duration nextDelay(int attempt) {
        Duration initial = properties.retry().initialDelay();
        Duration maximum = properties.retry().maxDelay();

        if (attempt <= 1) {
            return initial;
        }

        long multiplier = Math.min(attempt, 10);
        Duration computed = initial.multipliedBy(multiplier);

        return computed.compareTo(maximum) > 0
                ? maximum
                : computed;
    }
}
~~~

This service returns **Duration**, without forcing data into milliseconds right away.

If a scheduling library later requires milliseconds, convert at the **integration boundary**:

~~~java
long delayMillis = retryDelayService.nextDelay(3).toMillis();
~~~

Avoid converting back and forth between `String`, `long`, and `Duration` across every layer of the application.

**Caution:** multiplications or numeric conversions can overflow for huge `Duration` values. In real business configuration, validation should cap values. If nanosecond precision is needed, do not convert to milliseconds too early because sub-millisecond parts will be lost.

## 18. Duration and Profile-Specific Configuration

The same `Duration` field can take different values per profile.

**application.yml**:

~~~yaml
demo:
  client:
    connect-timeout: 2s
    request-timeout: 10s
~~~

**application-dev.yml**:

~~~yaml
demo:
  client:
    request-timeout: 30s
~~~

**application-prod.yml**:

~~~yaml
demo:
  client:
    connect-timeout: 5s
    request-timeout: 8s
~~~

Run:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

or:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Spring Boot loads Config Data files according to the profile and binds `Duration` from the effective value.

You do not need to declare **two separate `ClientProperties` classes** for dev and prod. One Java model works across environments; only configuration data changes.

If system properties, environment variables, or command-line arguments override values, they still participate in the overall precedence order.

## 19. Using Duration in Docker Compose

Example of a container running the application:

~~~yaml
services:
  api:
    image: example/duration-demo:1.0.0
    ports:
      - "8080:8080"
    environment:
      DEMO_CLIENT_CONNECTTIMEOUT: "5s"
      DEMO_CLIENT_REQUESTTIMEOUT: "15s"
      DEMO_CLIENT_RETRY_INITIALDELAY: "500ms"
      DEMO_CLIENT_RETRY_MAXDELAY: "8s"
~~~

The **environment** section holds string values. Docker Compose passes them into the container environment; Spring Boot Binder is what turns those strings into **Duration**.

Quote values to explicitly denote strings, especially when configuration contains **0**, bare numbers, or values YAML might parse as another data type.

If Compose's **.env** file is only used as an interpolation source, make sure variables are passed through the Compose configuration into the container. Simply declaring a value in **.env** does not guarantee it appears in the Java process environment.

## 20. Using Duration in Kubernetes

A **containers** snippet inside a Pod template:

~~~yaml
containers:
  - name: app
    image: example/duration-demo:1.0.0
    env:
      - name: DEMO_CLIENT_CONNECTTIMEOUT
        value: "5s"
      - name: DEMO_CLIENT_REQUESTTIMEOUT
        value: "15s"
      - name: DEMO_CLIENT_RETRY_INITIALDELAY
        value: "500ms"
~~~

This is an illustrative YAML snippet, not a full Deployment manifest.

Kubernetes does not need to understand what **5s** or **500ms** mean in these environment variables. It passes strings to the container; Spring Boot handles conversion during configuration binding.

If you mount a ConfigMap as an **application.yml** file, `Duration` values can also be loaded via Config Data; you still must verify the file location, path, and precedence order.

**Do not put real secrets into illustrative configs or debug endpoints.** A `Duration` itself is not secret, but the configuration system may also hold other sensitive keys.

## 21. Duration and Period Are Not the Same

Spring Boot supports both **Duration** and **Period**, but they solve different problems.

For example:

~~~text
Duration: 5s, 2h, 1d
Period:   3d, 2w, 1m, 1y
~~~

In simple-style **Duration** notation:

~~~text
m = minutes
~~~

In simple-style **Period** notation:

~~~text
m = months
~~~

This is critical when changing the Java type. **5m** is 5 minutes when bound to `Duration`, but can represent 5 months when bound to `Period` under its rules.

Use `Duration` for:

- Connect timeout.
- Request timeout.
- Retry delay.
- Duration-based cache TTL.
- Polling interval.
- Backoff time.

Consider `Period` or calendar APIs for:

- A 3-calendar-month term.
- A 1-year renewal.
- Adding days/months/years to a `LocalDate`.
- End-date rules based on a local calendar.

Do not use **Duration.ofDays(30)** as a default substitute for the concept of "one month".

## 22. Upgrading Legacy Properties from long to Duration

Suppose a legacy application has:

~~~java
private long timeoutSeconds;
~~~

and configuration:

~~~properties
legacy.timeout-seconds=30
~~~

There are two migration strategies:

### 22.1. Keep the Old Key and Add @DurationUnit

Class:

~~~java
@ConfigurationProperties(prefix = "legacy")
public class LegacyProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration timeoutSeconds;

    public Duration getTimeoutSeconds() {
        return timeoutSeconds;
    }

    public void setTimeoutSeconds(Duration timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds;
    }
}
~~~

Now **30** is still interpreted as 30 seconds, allowing migration to `Duration` without breaking the implicit unit contract of legacy deployment files.

**Note:** the example class above needs imports for **java.time.Duration**, **java.time.temporal.ChronoUnit**, **org.springframework.boot.context.properties.ConfigurationProperties**, and **org.springframework.boot.convert.DurationUnit**, as shown in earlier examples.

### 22.2. Switch to a New Key and Require Explicit Units

Example:

~~~properties
legacy.timeout=30s
~~~

This is an opportunity to redesign the configuration API. However, renaming **timeout-seconds** to **timeout** can break environments or manifests still using the old key. If consumers exist, you need a key-rename migration plan, documentation, and tests.

**Relaxed binding does not automatically treat two semantically different names like `timeout-seconds` and `timeout` as aliases of one another.**

## 23. Testing Duration Conversion

Suppose the Spring Boot app has registered:

~~~java
@ConfigurationProperties(prefix = "demo.client")
public record ClientProperties(
        Duration connectTimeout,
        Duration requestTimeout,
        Retry retry) {

    public record Retry(
            Duration initialDelay,
            Duration maxDelay) {
    }
}
~~~

You can use a test context:

~~~java
package com.example.duration;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
    "demo.client.connect-timeout=500ms",
    "demo.client.request-timeout=PT10S",
    "demo.client.retry.initial-delay=250ms",
    "demo.client.retry.max-delay=5s"
})
class DurationBindingTest {

    @Autowired
    ClientProperties properties;

    @Test
    void bindsDurationFromSeveralFormats() {
        assertEquals(
                Duration.ofMillis(500),
                properties.connectTimeout());
        assertEquals(
                Duration.ofSeconds(10),
                properties.requestTimeout());
        assertEquals(
                Duration.ofMillis(250),
                properties.retry().initialDelay());
        assertEquals(
                Duration.ofSeconds(5),
                properties.retry().maxDelay());
    }
}
~~~

The test assumes the project includes **spring-boot-starter-test** and has registered `ClientProperties` via **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties**.

**Key point:** the test passes different `Duration` styles—simple style with suffixes, ISO-8601, and unit-annotated values. Spring Boot Binder converts them to the same Java type.

### 23.1. Testing Suffixless Numeric Values

Another test for the default milliseconds rule:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration sessionTimeout;
~~~

should verify:

~~~text
session-timeout=30    -> Duration.ofSeconds(30)
session-timeout=30s   -> Duration.ofSeconds(30)
session-timeout=500ms -> Duration.ofMillis(500)
~~~

If **@DurationUnit** is removed, **30** must be interpreted as 30 milliseconds. When upgrading legacy systems, write tests proving this exact rule.

## 24. Checking Binding Failures and Diagnostics

At startup, if a `Duration` configuration value is invalid, the binder can report a value conversion error.

Example:

~~~properties
demo.client.connect-timeout=maybe
~~~

**maybe** is not a valid duration. If the binder needs to create a `Duration` from that key, binding can fail.

Diagnostic checklist:

1. Identify the exact key name being bound.
2. Identify the final effective property from Config Data, env, CLI, or another source.
3. Check whether the field/constructor parameter is **Duration** or mistakenly `String`, `long`, or `Period`.
4. Check the value syntax: number, ISO-8601, or number with suffix.
5. If using a suffixless number, check **@DurationUnit** and the default unit.
6. Check for overly large or small numbers causing overflow during conversion.
7. If the error comes from validation, distinguish it from a `Duration` parsing error.
8. Check active profiles and overrides from the deployment environment.

**Do not log the entire `Environment` while debugging**, because sources may contain passwords, tokens, or internal details. Log only non-sensitive keys and values needed for diagnosis.

An example of enabling detailed configuration logs in development:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.properties=DEBUG
~~~

Debug logs can help locate binding failures, though exact content and verbosity depend on version, logger, and situation. Do not assume it will always print every key.

## 25. Common Mistakes

### 25.1. Forgetting the Suffix and Getting Milliseconds

~~~properties
demo.client.connect-timeout=30
~~~

Defaults to **30ms**, not **30s**. Fix: write **30s** or declare `@DurationUnit` when preserving a legacy contract.

### 25.2. Confusing m with ms

~~~properties
retry-delay=5m
~~~

**5m** is 5 minutes, not 5 milliseconds. For 5 milliseconds, use **5ms**.

### 25.3. Using Month/Year Symbols with Duration

A requirement like "renew after 2 months" usually belongs to **Period** or calendar operations. Do not expect `Duration` to treat a month as a fixed length.

### 25.4. Using Duration.parse(...) for Simple-Style Strings

~~~java
Duration.parse("5s")
~~~

This is not an example of standard Java ISO-8601 syntax. If you need direct parsing outside the binder, use Java's API with ISO-8601 or Spring Boot's conversion mechanism; do not assume `java.time.Duration.parse` understands all Boot suffixes.

### 25.5. Treating @DurationUnit as a Forced Unit

`@DurationUnit` only changes the default unit for **values without a suffix**. **500ms** still means milliseconds when the field is annotated with **@DurationUnit(SECONDS)**.

### 25.6. Doing Arithmetic in Milliseconds Too Early

Converting a `Duration` to a `long` via **toMillis()** can lose nanoseconds or overflow for huge spans. Keep `Duration` in logic and convert only at the API boundary requiring a numeric type.

### 25.7. Not Checking Zero or Negative Values

A `Duration` can represent zero or negative numbers; not every client or scheduler accepts them. Add dedicated validation according to business semantics.

### 25.8. Confusing YAML Value with Property Name

~~~yaml
demo:
  client:
    connect-timeout: 5s
~~~

**connect-timeout** is the canonical name; **5s** is the value to convert. The corresponding Java field can be named **connectTimeout** via relaxed binding.

### 25.9. Manually Converting String to long

This removes the ability to use **500ms** or **PT5S** and obscures the implicit unit. Use **Duration** and the binder when configuration represents a duration.

### 25.10. Forgetting to Register Configuration Properties

Having the annotation without scanning or enabling prevents the bean from being created properly. With record constructor binding, use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

### 25.11. Thinking Editing an Env Var Updates Running Beans

Normally configuration properties are bound when the context starts. Changing a variable in another terminal does not update already-bound beans. Restart or perform a rolling deploy when changing configuration via standard mechanisms.

### 25.12. Using the Wrong Property for the Consuming Semantics

A syntactically valid `Duration` does not guarantee the library uses the same timeout meaning. For example, connect timeout differs from read timeout, request timeout, and idle timeout. Property names and docs must make this clear.

## 26. Hands-On Exercises

### Exercise A — Compare Three Duration Formats

1. Create **demo.client.connect-timeout** in YAML.
2. Try **5000**, **PT5S**, and **5s** in turn.
3. Print **connectTimeout().toMillis()** from a local endpoint.
4. Observe that all equal **5000 ms** when `@DurationUnit` is not used.

### Exercise B — Observe the Default Unit

1. Change the property to **30**.
2. Keep the `Duration` field without `@DurationUnit`.
3. Observe the result **30ms**.
4. Add **@DurationUnit(ChronoUnit.SECONDS)**.
5. Restart with the same value **30** and observe **30s**.

**Goal:** understand how the annotation changes the default unit of suffixless numbers.

### Exercise C — Same JAR, Different Environments

1. Build the application once.
2. In YAML, set **request-timeout: 10s**.
3. Start with **DEMO_CLIENT_REQUESTTIMEOUT=15s**.
4. Call the endpoint to inspect the effective value.
5. Stop and re-run with **--demo.client.request-timeout=20s**.

**Goal:** recognize configuration source precedence and how one `Duration` field can receive different values at deployment.

### Exercise D — Test ISO-8601

1. Set **connect-timeout: PT0.5S**.
2. Bind to `Duration`.
3. Verify **toMillis() = 500**.
4. Try **PT1M30S** and verify 90 seconds.

**Goal:** understand ISO-8601 syntax and its equivalence to simple-style units.

### Exercise E — Test Conversion and Validation Errors

1. Try **request-timeout: wrong**.
2. Observe the type conversion error on startup.
3. Change it to **0s**: it parses successfully.
4. Use a `> 0` check or an appropriate custom validator.
5. Distinguish parsing errors from business constraint errors.

### Exercise F — Migrate from long

1. Create a legacy property **session-timeout: 30** with a "seconds" contract.
2. Change the Java type from `long` to `Duration`.
3. Add **@DurationUnit(ChronoUnit.SECONDS)**.
4. Test **30**, **30s**, and **500ms**.
5. Document for operators that explicit suffixes are supported.

**Goal:** change the type without silently altering the unit of released configurations.

## 27. Checklist Before Using Duration for a Property

- Does the property represent a **technical time span** or a **calendar day/month** concept?
- Does the name clearly describe **connect**, **read**, **request**, **idle**, or **retry** timeout?
- Does the YAML/properties file have an **explicit unit suffix**?
- If users pass suffixless numbers, is the default unit documented?
- Is **@DurationUnit** needed to preserve backward compatibility?
- Is there a sensible default in YAML or **@DefaultValue**?
- What does **0** mean for the actual component?
- Are negative values blocked per business requirements?
- Is there an upper bound to avoid overflow or excessively long waits?
- Is the environment variable name properly derived from the canonical property?
- Is the type registered via proper scanning/enabling?
- Are there tests verifying important formats and the default unit?
- Does changing the configuration require restarting the application?
- Is there documentation for operators covering ISO format, simple units, and fallback?

## 28. Summary

- **java.time.Duration** is the right type to represent timeouts, delays, and intervals in Java.
- Spring Boot provides dedicated `Duration` conversion in **@ConfigurationProperties**.
- Three supported formats are **plain numbers**, **ISO-8601**, and **numbers with unit suffixes**.
- Documented unit suffixes include **ns**, **us**, **ms**, **s**, **m**, **h**, and **d**.
- **Suffixless numbers default to milliseconds**.
- **@DurationUnit** changes the default unit, which is especially helpful when migrating from legacy `long` properties.
- **@DefaultValue** can supply defaults in constructor binding, while JavaBeans can use field initializers.
- The same `Duration` property can be supplied from YAML, properties, env, system properties, or CLI.
- Distinguish **Duration** from **Period** when business rules involve calendars.
- Valid type conversion is not enough: define the semantics of zero, negatives, and valid limits.
- Keep `Duration` in code until a specific API requires milliseconds or another numeric unit.

## Official References

- Spring Boot 3.3 Reference — Externalized Configuration, sections *Converting Durations*, *Constructor Binding*, *Properties Conversion*, *Relaxed Binding*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Java 21 API — Duration: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html
- Java 21 API — Period: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html
- Spring Boot API — DurationUnit: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/convert/DurationUnit.html