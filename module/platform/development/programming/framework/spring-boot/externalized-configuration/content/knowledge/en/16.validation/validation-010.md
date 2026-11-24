# Distinguishing Binding Errors, Conversion Errors, and Constraint Violations

In Spring Boot Externalized Configuration, an application can read dozens or hundreds of values from `application.yml`, `application.properties`, profile-specific files, environment variables, JVM system properties, or command-line arguments. These values populate `Environment`, and Spring Boot's `Binder` binds them into `@ConfigurationProperties` to construct typed Java objects. Afterward, when configured, **Bean Validation** checks rules such as presence, non-blankness, or valid ranges.

When an application fails to start due to configuration, three distinct issues often get lumped together as "validation errors": **binding errors**, **type conversion errors**, and **constraint validation errors**. Grouping them leads troubleshooting down the wrong path: someone adds `@NotNull` trying to fix `"abc"` failing to parse as `int`, someone tweaks a converter when the real bug is a misspelled YAML prefix, or someone deletes `@Validated` to hide an out-of-range port.

This lesson clarifies the exact responsibility of each layer, how they relate, what clues appear in exceptions and logs, how to read `Property`/`Value`/`Origin`/`Reason`, how to build reproducible examples, and a debugging workflow for Spring Boot 3.x (Java 17+).

## 1. Three Different Questions During Startup

Consider the input configuration:

~~~yaml
app:
  notification:
    endpoint: https://notify.example.test
    timeout: 2s
    max-retries: 3
    enabled: true
~~~

Model:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
    URI endpoint,
    Duration timeout,
    int maxRetries,
    boolean enabled
) {}
~~~

Spring Boot must answer three questions in sequence:

1. **Binding:** Which keys under prefix `app.notification` correspond to which record components? Can the object be constructed with that Java shape?
2. **Conversion:** Does `"2s"` convert to `Duration`? Does `"3"` become `int`? Does the URL convert to `URI`?
3. **Constraint validation:** Once typed values exist, do they satisfy business rules—such as `maxRetries >= 0`, `endpoint != null`, or `timeout` being required?

These three questions are connected yet **not the same error**. Conversion is a sub-step within binding: when conversion fails, Spring Boot typically surfaces it through an outer binding exception. Validation is also invoked during configuration-properties binding, yet its **failure reason** stems from constraints on present or missing data.

### Event Flow

~~~text
External configuration sources
  application.yml / application.properties
  profiles / imports / environment / -D / --args
                    |
                    v
          Environment / PropertySource
                    |
                    v
        Config Data and Binder key lookup
                    |
          +---------+-----------+
          |                     |
          v                     v
     Keys mappable?       Key shape mismatches
     Name/prefix/shape    target; Binder cannot
     compatible?          construct object
          |                     |
          v                     v
     Type conversion        BINDING FAILURE
     String -> Java type
          |
     +----+---------------------+
     |                          |
     v                          v
  Succeeded               CONVERSION FAILURE
     |                    (often wrapped in a
     |                     binding exception)
     v
  Configuration object
     |
     v
  Bean Validation (if enabled)
     |
     +-----> Constraint violated
     |            |
     |            v
     |       VALIDATION FAILURE
     v
  Configuration bean ready
~~~

**Key takeaway:** outer exception names like `ConfigurationPropertiesBindException` or `BindException` are not enough to pinpoint the cause. Inspect the **cause chain**, `Reason`, offending key, and target type.

## 2. Quick Comparison Table

| Criterion | Binding Error | Conversion Error | Constraint Violation |
| --- | --- | --- | --- |
| Failing question | Do keys/structure map onto the model? | Can the value convert to the required Java type? | Does the bound value satisfy rules? |
| Example | YAML uses an object where Java expects a list; constructor cannot bind | `max-retries=many` for an `int` field | `max-retries=-2` with `@Min(0)` |
| Root cause | Shape, prefix, accessors, bean registration/constructor, mismatched keys | Format, converter, target type, enum, units | Constraints, business rules, required values |
| Common symptoms | `BindException`, `Failed to bind properties` | `ConversionFailedException` or wrapped conversion cause | `BindValidationException` or validation errors |
| Wrong data type? | Possibly, since conversion happens during bind | Yes | Not necessarily; type may be completely valid |
| `@Validated` required? | Not required for bind errors | Not required for conversion errors | Usually required for config-properties Bean Validation |
| Primary fix | Fix config names/shape or model/binding mechanism | Fix value or converter/Java type | Fix value to satisfy rule or revise invalid rule |
| Can occur at startup? | Yes | Yes | Yes, if validation is configured |

A minimal example to remember:

~~~properties
# Mapping/structure error, if Java expects List<Server>
app.servers.name=primary

# Conversion error, if field expects int
app.max-retries=many

# Validation error, if field is int with @Min(0)
app.max-retries=-3
~~~

In the final example, Java converts `-3` to an integer cleanly. The error occurs only when evaluating `@Min(0)`. Do not call it a "number parsing error."

## 3. Prerequisite: `@ConfigurationProperties` Must Be Registered

Before classifying those three errors, verify the **configuration properties bean** is registered properly. Declaring a record alone is not enough:

~~~java
package com.example.demo.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
    URI endpoint,
    Duration timeout,
    int maxRetries
) {}
~~~

Register via scanning:

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

Or register explicitly:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {}
~~~

If the app reports `required a bean of type NotificationProperties that could not be found`, first check **bean registration**: scanning/enabling annotations, package placement, and whether the configuration class was loaded. **A missing bean does not mean a data constraint failed.** Without the bean registered, the Binder never even starts validating the object.

For constructor-bound records, avoid adding `@Component` just to make Spring detect the class: component construction and configuration-properties constructor binding follow two distinct instantiation paths.

## 4. What Is a Binding Error?

**Binding** is the process where Spring Boot takes matching property keys, resolves nested structures and collections, and assigns or passes them into a Java object—via setters on mutable JavaBeans or constructors on immutable records/classes.

Typical binding problems:

- YAML structure differs from Java target: mixing up a list and an object.
- Nested property path does not match fields accessible to the Binder.
- Setter-bound type lacks an appropriate constructor or setter.
- Constructor binding cannot resolve required constructor/parameter names in complex setups.
- Strict unknown-field mode is enabled, and the source contains unbound keys.
- A value fails conversion, halting binding (classify further as a conversion error).
- A validation violation is wrapped in a binding exception (inspect the inner reason).

**"Binding failure" is a broad umbrella.** Whenever you see "bind" in logs, check the root cause before deciding whether it is shape, conversion, or validation.

### Structural Binding Error Example

The model expects a list:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record GatewayProperties(List<Gateway> gateways) {
    public record Gateway(String name, URI url) {}
}
~~~

Yet YAML writes a single object:

~~~yaml
app:
  gateways:
    name: primary
    url: https://gateway.example.test
~~~

Here `gateways` is a mapping object, whereas Java expects `List<Gateway>`. Depending on the binding path and converters, Spring Boot fails to construct the expected list and throws a bind error or leaves fields unbound.

The matching structure is a YAML sequence:

~~~yaml
app:
  gateways:
    - name: primary
      url: https://gateway.example.test
    - name: backup
      url: https://backup.example.test
~~~

In `.properties`, lists require indices:

~~~properties
app.gateways[0].name=primary
app.gateways[0].url=https://gateway.example.test
app.gateways[1].name=backup
app.gateways[1].url=https://backup.example.test
~~~

Do not try to fix this by adding `@Min` or `@NotNull`: they cannot convert a YAML mapping into a sequence.

## 5. Misaligned Nesting Levels

Suppose Java expects:

~~~java
@ConfigurationProperties(prefix = "app")
public record MailProperties(
    Mail mail
) {
    public record Mail(
        String host,
        Security security
    ) {}
    public record Security(
        boolean tlsEnabled,
        int port
    ) {}
}
~~~

Correct YAML:

~~~yaml
app:
  mail:
    host: smtp.example.test
    security:
      tls-enabled: true
      port: 587
~~~

Misaligned YAML:

~~~yaml
app:
  mail:
    host: smtp.example.test
    tls-enabled: true
    port: 587
~~~

`tls-enabled` and `port` are not under `app.mail.security`. When the Binder ignores unrecognized fields by default, the app might even start up with `security` equal to `null` or holding unexpected defaults. If strict binding or validation is configured, startup fails.

**Very important:** "failing to bind an intended field" does not always fail startup. Missing keys or unknown keys are often ignored by default; validation and tests are needed to catch them.

### Key Names and Relaxed Binding

Spring Boot supports relaxed binding, so:

~~~properties
app.mail.security.tls-enabled=true
~~~

maps to `boolean tlsEnabled` in the matching nested record.

However, relaxed binding does not fix typos:

~~~properties
app.mail.securty.tls-enabled=true
~~~

`securty` does not match `security`; a missing `i` is not guessed by the Binder. For required keys, use validation so missing properties fail loudly instead of silently receiving defaults.

## 6. Unknown Properties and `ignoreUnknownFields`

`@ConfigurationProperties` has an `ignoreUnknownFields` attribute. Its default behavior **ignores unrecognized fields** in many binding scenarios rather than failing on every typo.

Example:

~~~java
@ConfigurationProperties(
    prefix = "app.mail",
    ignoreUnknownFields = false
)
public class MailProperties {
    private String host;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }
}
~~~

File:

~~~properties
app.mail.host=smtp.example.test
app.mail.hots=smtp.other.example.test
~~~

`hots` is an unknown property relative to the JavaBean's `host`. With strict binding enabled, the Binder reports an error for unbound properties.

In practice, `ignoreUnknownFields=false` helps catch leftover or misspelled keys under a prefix owned exclusively by one class. However, do not enable it blindly across shared prefixes: strict binding will reject valid keys belonging to other beans under that prefix.

### `ignoreUnknownFields` vs. `ignoreInvalidFields`

`@ConfigurationProperties` also has `ignoreInvalidFields`, defaulting to `false`. Their meanings differ:

- **Unknown field:** source contains a key the model has no field for; e.g., `app.mail.hots`.
- **Invalid field:** key matches a field, yet its value cannot convert/bind to the required type; e.g., `app.mail.port=abc` for `int port`.

Never set `ignoreInvalidFields=true` just to "let the app run" when types are wrong. Doing so leaves objects with missing data or unsafe defaults, causing business bugs later.

## 7. What Is a Conversion Error?

A conversion error happens when the Binder **located the right property path**, yet the value cannot convert into the target Java type.

Common conversions:

| Source Value | Target Type | Expected Outcome |
| --- | --- | --- |
| `"3"` | `int` / `Integer` | `3` |
| `"true"` | `boolean` / `Boolean` | `true` |
| `"750ms"` | `Duration` | 750 milliseconds |
| `"10MB"` | `DataSize` | 10 megabytes per `DataSize` rules |
| `"https://api.example.test"` | `URI` | Valid `URI` |
| `"EMAIL"` | `Channel` enum | `Channel.EMAIL` if defined |

Clear conversion errors:

~~~properties
app.notification.max-retries=many
app.notification.timeout=soon
app.notification.enabled=maybe
~~~

When Java expects `int`, `Duration`, and `boolean`, those values fail standard converters and halt startup.

### Reproducible Example

Model:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    int maxAttempts,
    Duration backoff
) {}
~~~

Invalid config:

~~~properties
app.retry.max-attempts=three
app.retry.backoff=250ms
~~~

`app.retry.max-attempts` **has the exact right key name** and targets `maxAttempts`. Yet `"three"` cannot convert to `int`. Error reports mention the target type (`java.lang.Integer` or `int`) and a number-parsing cause.

Fix with type-valid data:

~~~properties
app.retry.max-attempts=3
app.retry.backoff=250ms
~~~

**No need to change the prefix, remove `@Validated`, or alter the constructor** when the fault is converting `"three"`.

## 8. Reading Conversion Exceptions

In a Spring Boot stack trace, a conversion error may pass through multiple layers:

~~~text
BeanCreationException / ConfigurationPropertiesBindException
  └─ BindException: Failed to bind properties under 'app.retry'
       └─ ConversionFailedException
            └─ NumberFormatException
~~~

This is an **illustrative cause chain**, not a guarantee every version prints these exact four classes in this order. Depending on type, converter, bean registration, and Spring Boot version, exact exception classes can vary.

Focus on three facts:

1. **Key name:** which property failed conversion?
2. **Target type:** `int`, `Duration`, enum, or a custom type?
3. **Source value:** what string failed to convert, and which file/profile/env/CLI flag supplied it?

Illustrative error message:

~~~text
Failed to bind properties under 'app.retry.max-attempts'
to int:

    Property: app.retry.max-attempts
    Value: "three"
    Origin: class path resource [application.properties] - 1:24
    Reason: failed to convert java.lang.String to int
~~~

`Origin`, line numbers, and layout vary by Spring Boot version and source type. When `Origin` points to a line in `application.properties` or an environment variable, fix the **actual winning source**, not a lower-precedence file open in your IDE.

## 9. Enums, `Duration`, `DataSize`, and Custom Types

Conversion is not limited to parsing numbers from strings.

### Enum

~~~java
public enum DeliveryMode {
    SYNC, ASYNC
}
~~~

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(DeliveryMode mode) {}
~~~

~~~properties
app.delivery.mode=ASYNC
~~~

binds cleanly. Conversely:

~~~properties
app.delivery.mode=SUPERFAST
~~~

has no matching enum constant. This is a type conversion or binding-value error, **not a `@Pattern` validation error** when the model uses an enum.

### `Duration`

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

~~~properties
app.client.timeout=1500ms
~~~

is valid. By contrast, `app.client.timeout=tomorrow` is not a `Duration` format recognized by Spring Boot's converter.

### `DataSize`

~~~java
@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(DataSize maxSize) {}
~~~

~~~properties
app.upload.max-size=10MB
~~~

binds via `DataSize` conversion. `app.upload.max-size=very-big` fails during conversion.

### Custom Types

If an application defines a record:

~~~java
public record RegionCode(String value) {}
~~~

and typed properties expect `RegionCode`, register an appropriate converter. For custom configuration-properties conversion, Spring Boot supports converters qualified with `@ConfigurationPropertiesBinding`:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class RegionConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    public static Converter<String, RegionCode> regionCodeConverter() {
        return RegionCode::new;
    }
}
~~~

This illustrates adding a custom converter. In Spring Boot 3.x, `static` factory methods for binding converters are recommended to avoid prematurely initializing the `@Configuration` class.

If the converter is missing or throws an exception on malformed input, failure surfaces during conversion. Do not add `@NotBlank` to `RegionCode` trying to fix the fact that the Binder does not know how to construct a `RegionCode` at all.

## 10. What Is a Constraint Validation Error?

Once the Binder holds type-valid data, the application still must check **business validity**. That is Bean Validation's responsibility when configured.

Example:

~~~java
import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
    @NotNull URI endpoint,
    @NotNull Duration timeout,
    @Min(0) @Max(10) int maxRetries
) {}
~~~

File:

~~~properties
app.notification.endpoint=https://notify.example.test
app.notification.timeout=2s
app.notification.max-retries=-3
~~~

Here `-3` **converts to `int` cleanly**, yet violates `@Min(0)`. Thus the primary cause is a **validation failure**, not a conversion failure.

Fix the value to a non-negative integer up to 10:

~~~properties
app.notification.max-retries=3
~~~

Or if business logic genuinely permits negative numbers (unusual for retry counts), revise the validation rule. Never drop a constraint solely to silence an error without verifying the contract.

## 11. Enabling Bean Validation Properly

In Spring Boot 3.x, standard constraints live in `jakarta.validation.constraints.*`. Projects need a compatible validator implementation/provider; in Spring Boot, typically add the starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Assuming the project uses Spring Boot dependency management, do not hardcode a starter version in these examples.

Config bean:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
    @NotBlank String host,
    @Positive int port
) {}
~~~

`@Validated` on the root configuration-properties bean triggers constraint checks via binding/validation integration. Having a provider gives you the Bean Validation implementation; without that dependency, do not expect `@NotBlank` or `@Positive` to run automatically.

For older Spring Boot 2.x releases using `javax.validation.*`, stick to the namespace compatible with your project. Never mix `javax.validation` and `jakarta.validation` imports randomly.

## 12. `@NotNull`, `@NotBlank`, `@Min`: Choosing the Right Constraint

| Constraint | Primary Purpose | Good Example |
| --- | --- | --- |
| `@NotNull` | Value must not be null | `URI endpoint`, `Duration timeout` |
| `@NotBlank` | String not null/empty/whitespace-only | `String host` |
| `@NotEmpty` | String, array, collection, or map not empty | `List<String> recipients` |
| `@Min(0)` | Number must be >= 0 | Retry count |
| `@Max(65535)` | Number must not exceed upper bound | Port (paired with `@Min(1)`) |
| `@Positive` | Positive number | Pool size |
| `@Pattern(...)` | String matches regex | Formatted code |
| `@Size(min=..., max=...)` | Length/size bounds on String/collection/map/array | Max recipient count |

Example:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
    @NotBlank String name,
    @Min(1) @Max(32) int concurrency,
    @NotNull Duration pollInterval
) {}
~~~

Values:

~~~properties
app.worker.name=consumer-1
app.worker.concurrency=0
app.worker.poll-interval=2s
~~~

`concurrency=0` converts to `int` cleanly yet violates `@Min(1)`. Meanwhile, `concurrency=abc` fails conversion to `int` before numeric validation on bound values ever runs.

### One Annotation Does Not Fit Every Type

Never put `@NotBlank` on `int` or `Duration` as a generic "required" marker. `@NotBlank` is for `CharSequence`. For positive numbers, use `@Positive`/`@Min`; for required `Duration`, use `@NotNull` plus a custom constraint or compatible mechanism when duration bounds are needed.

Putting a constraint on an incompatible type produces a validator configuration failure rather than a normal "invalid property value" error. Match constraints to Java types.

## 13. Missing Properties: Validation Failure or No Error at All

An omitted key is not automatically a conversion error.

Example:

~~~java
@ConfigurationProperties(prefix = "app")
public record FeatureProperties(
    String endpoint,
    Integer maxRetries
) {}
~~~

If `app.endpoint` and `app.max-retries` are absent, the Binder can create the object with null components under constructor binding. **Without required constraints**, the app boots and fails only when a service accesses the null value.

Add constraints:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record FeatureProperties(
    @NotBlank String endpoint,
    @NotNull Integer maxRetries
) {}
~~~

With validation active, missing values trigger constraint violations, making the application **fail fast** at startup.

With primitives like `int`, `@NotNull` cannot catch missing values because primitives have no null state. To require explicit declaration, use wrapper `Integer` + `@NotNull` or an equivalent mechanism.

### Missing vs. Empty vs. Invalid

~~~properties
# Case A: key omitted
# app.worker.name is not declared

# Case B: key present with empty value
app.worker.name=

# Case C: value present yet fails constraint
app.worker.name=   
~~~

For `String name` with `@NotBlank`, both empty and whitespace-only strings fail. If the key is omitted completely and the model receives null, `@NotBlank` catches null too.

Meanwhile, if Java expects `int concurrency` and config supplies `app.worker.concurrency=abc`, the primary failure is conversion. Fix the input to an integer rather than just adding `@NotNull`.

## 14. Validating Nested Objects with `@Valid`

A frequently missed detail is putting `@Validated` on the root while nested object fields go unvalidated.

YAML example:

~~~yaml
app:
  outbound:
    base-url: https://api.example.test
    retry:
      max-attempts: -1
      backoff: 200ms
~~~

Model:

~~~java
import java.net.URI;
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.outbound")
public record OutboundProperties(
    @NotNull URI baseUrl,
    @NotNull @Valid Retry retry
) {
    public record Retry(
        @Min(0) int maxAttempts,
        @NotNull Duration backoff
    ) {}
}
~~~

The root `OutboundProperties` is validated, and `@Valid` cascades into nested `Retry` per Bean Validation rules. With `max-attempts=-1`, integer conversion succeeds and the nested constraint fails.

If `retry` is missing entirely, `@NotNull` on `retry` catches null. If the nested object exists without `backoff`, `@Valid` combined with `@NotNull` on the nested field catches it.

### `List<@Valid Item>` and Nested `Map`s

Example:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record GatewayCatalog(
    @NotEmpty List<@Valid Gateway> gateways
) {
    public record Gateway(
        @NotBlank String id,
        @NotNull URI url,
        @Min(1) int weight
    ) {}
}
~~~

If `app.gateways[1].id` is blank or `weight=0`, Bean Validation reports the violation on that element when provider and cascade wiring are configured properly.

A `Map<String, @Valid Target>` structure is likewise validated across its values. Never assume `@Validated` alone discovers constraints deep inside an object tree without explicit cascading.

## 15. Validation vs. Conversion Inside Nested Lists

Using `GatewayCatalog` from above, compare four sources:

**Type conversion failure:**

~~~properties
app.gateways[0].id=primary
app.gateways[0].url=https://api.example.test
app.gateways[0].weight=heavy
~~~

`weight` expects `int` but receives `"heavy"`, so conversion fails.

**Constraint violation:**

~~~properties
app.gateways[0].id=primary
app.gateways[0].url=https://api.example.test
app.gateways[0].weight=0
~~~

`0` is a valid `int`, yet violates `@Min(1)`.

**Missing required field:**

~~~properties
app.gateways[0].id=primary
app.gateways[0].weight=2
~~~

Without `url`, when the record declares `@NotNull URI url`, validation fails after binding (assuming the object is instantiated and cascaded).

**Structural shape mismatch:**

~~~properties
app.gateways.id=primary
~~~

The source omits the list index. First and foremost, this is a structural binding issue—not `weight`'s type or `@Min`.

Each case demands a different fix, even though startup logs may all begin with "Failed to bind properties."

## 16. When Is a YAML Error Outside All Three Categories?

An important exception: not every externalized configuration error even reaches the Binder.

Example of malformed YAML syntax:

~~~yaml
app:
  retry:
    max-attempts: [1, 2
~~~

The sequence `[1, 2` is unclosed, so the YAML parser fails **before Spring Boot ever extracts key/value pairs** to bind into Java.

Or YAML has duplicate keys rejected by the parser:

~~~yaml
app:
  enabled: true
  enabled: false
~~~

Depending on parser configuration, loading YAML reports a duplicate-key failure prior to binding. Fix the file syntax rather than changing `@Min` or `String -> Integer` converters.

Other issues occurring before binding:

- `spring.config.import` points to a required location that does not exist.
- Configuration file lacks read permissions or uses an incompatible encoding.
- A profile name or Config Data document violates Spring Boot placement rules.
- Unresolved placeholders in a context expecting a valid value.
- Conflicting sources or failures loading a custom `PropertySource`.

**Proper diagnosis starts by identifying the failing layer**: Config Data parsing/loading, binding, conversion, validation, and only then startup beans/business logic.

## 17. Reading Startup Messages: `Property`, `Value`, `Origin`, `Reason`

Spring Boot's failure analysis formats many configuration errors into a structured block:

~~~text
Failed to bind properties under 'app.retry' to RetryProperties:

    Property: app.retry.max-attempts
    Value: "many"
    Origin: class path resource [application.yml] - 4:19
    Reason: failed to convert java.lang.String to int
~~~

This is a **simulated format** for learning how to read logs. Exact layout varies by Boot version, converter, bean type, and config source. Inspect four parts:

- **`Property`:** which key the Binder evaluated. Check prefix, spelling, hyphens, and list indices.
- **`Value`:** the actual value that reached the Binder, not necessarily what is in the file open in your IDE.
- **`Origin`:** source file/line or origin metadata. When present, use it to jump directly to what needs fixing.
- **`Reason`:** the ultimate failure cause, vital for distinguishing conversion from validation.

For sources like environment variables or programmatic sources, `Origin` formats differently. Not every failure prints a neat four-line block.

### Logs Can Contain Secrets

If a property is a password, API key, or token, the logged value may be sensitive even though some mechanisms sanitize certain keys. Never paste raw logs containing secrets into public issues. Share only minimal info: key name, error category, target type, source kind, and sanitized messages.

## 18. Outer Exceptions vs. Root Cause

A startup failure may be wrapped across several exception layers:

~~~text
org.springframework.beans.factory.BeanCreationException
  -> org.springframework.boot.context.properties.ConfigurationPropertiesBindException
     -> org.springframework.boot.context.properties.bind.BindException
        -> ...
~~~

The `...` could be a conversion error, a validation error, or an object instantiation failure. **Never follow a naive rule like "seeing `BindException` means YAML is wrong."**

Common names:

| Exception / Concept Name | What to Understand |
| --- | --- |
| `BeanCreationException` | Spring failed to create a bean; very broad, not only config errors |
| `ConfigurationPropertiesBindException` | Binding a configuration properties bean failed; inspect cause |
| `BindException` (Spring Boot Binder) | Error binding a prefix/value into a target |
| `ConversionFailedException` | Signals type conversion failure, often wrapped |
| `BindValidationException` | Signals validation failure during binding |
| `NumberFormatException` | Often the deep root cause when converting `String` to a number |
| `ConstraintViolationException` | Bean Validation exception in many contexts; not every config validation failure uses this exact class |
| `IllegalArgumentException` | Very broad; can originate from converters, constructors, custom validators, or other logic |

Spring applications also contain `BindException` classes in different packages for other data-binding mechanisms; do not confuse **Spring Boot configuration properties Binder** exceptions with Spring MVC form/request binding exceptions.

When inspecting exceptions, check **full package names**, the cause chain, and failure analyzer output.

## 19. Similar Symptoms, Different Causes

Suppose the app prints:

~~~text
Application failed to start
Failed to bind properties under 'app.server'
~~~

Completely different root causes can produce that headline.

**Case A — wrong type:**

~~~properties
app.server.port=abc
~~~

Java expects `int port`. This is a conversion failure.

**Case B — valid integer out of range:**

~~~properties
app.server.port=70000
~~~

Java uses `@Min(1) @Max(65535) int port`. This is a validation failure when constraints are enabled.

**Case C — missing required property:**

~~~properties
# app.server.host is omitted
~~~

Java uses `@NotBlank String host`. This is normally a validation failure if binding constructs the object with null `host`.

**Case D — misspelled key:**

~~~properties
app.server.hots=localhost
~~~

Java uses `String host`. With unknown fields ignored, the Binder provides no value for `host`; if `@NotBlank` is active, validation catches it. If strict unknown-field binding is enabled, a binding error for unrecognized properties occurs.

**Case E — wrong structure:**

~~~yaml
app:
  server:
    endpoints:
      id: primary
~~~

Java expects `List<Endpoint> endpoints`. This is a structural mismatch at the binding layer.

**Case F — missing config bean:** class is annotated yet never scanned/enabled. This is a bean registration issue, not value conversion or constraint validation.

The outermost headline cannot uniquely identify the category without `Reason` and the cause chain.

## 20. Fixing Errors at the Right Layer

| Error | Proper Fix | Misguided Fix |
| --- | --- | --- |
| YAML mapping instead of sequence | Use `-` for list items or change model to an object | Add `@NotNull` to the list |
| Prefix `app.clients` vs. `app.client` | Align key/prefix names | Change `maxRetries` |
| Missing valid setter/constructor binding | Fix model or bean registration path | Disable validation |
| `"abc"` for `int` | Supply a valid integer | Add `@Min(0)` |
| `"tomorrow"` for `Duration` | Use units like `ms`/`s` or a matching converter | Rename the bean |
| Non-existent enum value | Use a valid enum constant or deliberate custom converter | Add `@NotBlank` to the enum |
| `-1` with `@Min(0)` | Supply a non-negative number or revise rule | Replace integer converter |
| Blank host with `@NotBlank` | Supply a non-blank host | Set `ignoreInvalidFields` |
| Nested object has constraints not cascading | Add `@Valid` at the right boundary | Parse YAML manually |
| Config source fails to load | Fix file/path/config import | Change `@Validated` |
| Runtime value differs from expected file | Check active profiles and `PropertySource` precedence | Edit record getters |

For production configurations, never disable validation, loosen constraints, or ignore invalid fields just to make the process boot. Doing so turns a clear startup failure into hard-to-trace business bugs under live traffic.

## 21. Precedence Can Make You Edit the Wrong Source

Suppose the base file has:

~~~properties
app.retry.max-attempts=3
~~~

Yet the app runs with:

~~~bash
java -jar app.jar --app.retry.max-attempts=many
~~~

Command-line arguments normally outrank standard Config Data. Even though the file says `3`, the Binder sees `"many"` and fails converting to `int`.

If you edit `app.retry.max-attempts` in the file from `3` to `4` while keeping `--app.retry.max-attempts=many`, the failure persists. That is why `Origin` and effective values matter.

Similarly:

~~~bash
APP_RETRY_MAXATTEMPTS=bad java -jar app.jar
~~~

in a matching shell injects `"bad"` from the environment variable. If it overrides the config file, fix the deployment environment.

**Binding, conversion, and validation always run on values supplied by the effective configuration**, not automatically on the first file a developer opens.

## 22. Profile-Specific Config Can Fail Only in One Environment

Example:

~~~yaml
# application.yml
app:
  worker:
    concurrency: 4
~~~

~~~yaml
# application-prod.yml
app:
  worker:
    concurrency: many
~~~

Without the `prod` profile, the app binds `4` normally. When `prod` is active, `"many"` from the profile file becomes effective and conversion to `int` fails.

Run:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Check:

1. Which profiles are active?
2. Which profile-specific files loaded?
3. Are `spring.config.import` or external configurations overriding anything?
4. Does `Origin` point to the production file?
5. Do values match both types and constraints?

Passing locally does not prove every profile is valid. For critical properties, run context tests covering realistic deployment profiles and scenarios.

## 23. Testing Conversion Failures with `ApplicationContextRunner`

Spring Boot Test's `ApplicationContextRunner` creates a small context with given input properties to verify whether startup fails.

Example model:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    int maxAttempts,
    Duration backoff
) {}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class RetryConversionTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void invalidIntegerFailsDuringBinding() {
        runner
            .withPropertyValues(
                "app.retry.max-attempts=many",
                "app.retry.backoff=250ms"
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .isNotNull();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(RetryProperties.class)
    static class TestConfig {}
}
~~~

This test verifies the context fails to start with the bad value. If you want to **assert specifically that it is a conversion failure** rather than any startup failure, inspect the root cause, exception message, or stable exception types for your Spring Boot version.

Avoid asserting the exact full failure analyzer text, as formatting changes across versions.

## 24. Testing Constraint Failures with `ApplicationContextRunner`

Validated model:

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    @Min(0) int maxAttempts
) {}
~~~

Assume the test classpath includes a Bean Validation provider and the context configures the validator properly. Test a type-valid value that violates the constraint:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class RetryValidationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class)
            .withConfiguration(
                org.springframework.boot.autoconfigure.AutoConfigurations
                    .of(ValidationAutoConfiguration.class)
            );

    @Test
    void negativeRetryCountViolatesConstraint() {
        runner
            .withPropertyValues("app.retry.max-attempts=-2")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .isNotNull();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(RetryProperties.class)
    static class TestConfig {}
}
~~~

This example requires `spring-boot-starter-test` and `spring-boot-starter-validation` for the project. It demonstrates that **`-2` is a valid integer**; rejection comes from `@Min(0)`.

If this test does not fail, check whether a validation provider was added to the context, whether the record has `@Validated`, and whether the type is registered. Do not jump to concluding Spring Boot ignored `@Min`.

## 25. Testing Structural Binding Failures

Write a test for shape mismatches between property keys and target types:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record GatewayProperties(List<Gateway> gateways) {
    public record Gateway(String id, URI url) {}
}
~~~

Input without indices:

~~~properties
app.gateways.id=primary
app.gateways.url=https://gateway.example.test
~~~

In tests, assert the startup outcome or bound bean values (if the context starts), and compare against the **expected list shape**. Distinguish a hard binding failure from the Binder skipping unrecognized keys and leaving fields null/empty. To prevent both, use indexed syntax alongside validation on required lists.

Valid example:

~~~properties
app.gateways[0].id=primary
app.gateways[0].url=https://gateway.example.test
~~~

A meaningful binding test asserts more than "no exception thrown." It verifies the **exact element count, field values, and types**. Never assume that because the Binder read a file, every key populated the object.

## 26. `@SpringBootTest` for Testing Real Configuration Sources

When you need to test how Spring Boot loads real YAML, profiles, imports, and auto-configuration, use `@SpringBootTest`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "app.retry.max-attempts=3",
    "app.retry.backoff=500ms"
})
class RetryPropertiesIntegrationTest {

    @Autowired
    RetryProperties retry;

    @Test
    void bindsValidConfiguration() {
        assertThat(retry.maxAttempts()).isEqualTo(3);
        assertThat(retry.backoff())
            .isEqualTo(Duration.ofMillis(500));
    }
}
~~~

This assumes the application registers `RetryProperties` via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. This is the **positive path**: data binds into the expected Java types.

For negative paths where startup fails, `ApplicationContextRunner` makes asserting failures much cleaner than a `@SpringBootTest` crashing before the test method runs. Pick the tool matching what you need to verify.

## 27. Building a Three-Layer Test Matrix

A clear test strategy keeps one model and varies inputs:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
    @NotBlank String name,
    @Min(1) @Max(16) int concurrency,
    @NotNull Duration pollInterval
) {}
~~~

| Case | Typical Input | Expectation |
| --- | --- | --- |
| Success | `name=worker-1`, `concurrency=4`, `poll-interval=2s` | Bind + convert + validate succeed |
| Conversion failure | `concurrency=many` | Conversion failure |
| Validation failure | `concurrency=0` | Validation failure |
| Missing required | omit `name` | Validation failure if enabled |
| Shape mismatch | `poll-interval` nested under another object | Key fails to bind; validation may report missing |
| Unknown field | `concurency=4` missing `r` | Ignored or rejected by strict binding |
| CLI override | `--app.worker.concurrency=bad` | Conversion failure on winning source |
| YAML parse failure | Unclosed list bracket or bad YAML syntax | Config loading failure before binding |

Write matching assertions for each case. Simply asserting `hasFailed` proves an error occurred; for clear classification, inspect the cause chain and, where needed, assert the exact property path or cause type. Ensure validation actually has a provider, or constraint-violation cases will silently pass.

## 28. `@Value` Has Different Failure Behavior Than `@ConfigurationProperties`

A component can inject:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WorkerClient {
    private final int concurrency;

    public WorkerClient(
        @Value("${app.worker.concurrency}") int concurrency
    ) {
        this.concurrency = concurrency;
    }
}
~~~

If the key is missing, placeholder resolution fails during bean creation. If the value is `"many"`, `@Value` conversion throws an injection/type-mismatch error. These are externalized-config errors, yet they do not travel through the exact same pipeline or exception classes as Spring Boot's `@ConfigurationProperties` Binder.

Do not automatically label every `@Value` error as a `ConfigurationPropertiesBindException`. Exact exception classes depend on the injection mechanism.

### When to Prefer `@ConfigurationProperties`?

When a group of settings shares typed fields and constraints, `@ConfigurationProperties` keeps modeling, binding, and validation clean and cohesive. `@Value` fits a few standalone scalars. Avoid scattering dozens of `@Value` annotations with ad-hoc checks when they belong to one configuration contract.

## 29. Do Not Obscure Errors with Reckless Fallbacks

Example:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private int concurrency = 4;
    // getters, setters...
}
~~~

Default `4` is helpful when an optional key is omitted. However, if `concurrency` is required in production, never define a default that hides missing deployment config.

Likewise, setting `ignoreInvalidFields=true` prevents wrong-typed inputs from failing startup as expected, leaving the bean with defaults or missing values. That is dangerous when an app handles money, timeouts, ports, or authorization.

Rule of thumb:

- **Use defaults** when business semantics define a safe fallback.
- **Use validation** when missing or invalid values must halt startup.
- **Never ignore invalid fields** merely to reduce startup errors.
- **Inspect effective value sources** so you do not mistake an override error for a default.

## 30. Separating Scopes: Syntax, Type, and Business Rules

The layers also correspond to distinct data-checking responsibilities:

| Layer | Example Question | Tool |
| --- | --- | --- |
| File syntax/structure | Can YAML be parsed? | YAML/properties parser, Config Data loader |
| Mapping/binding | Which field does `app.worker.concurrency` map to? | Spring Boot Binder |
| Type conversion | Does `"4"` become `int`? Does `"2s"` become `Duration`? | `ConversionService`/converters |
| Constraint validation | Is `concurrency` between 1 and 16? | Bean Validation |
| Cross-field validation | Is `readTimeout >= connectTimeout`? | Custom class-level constraint or post-bind check |
| Runtime logic | Is the remote endpoint reachable? | Health checks/service logic, not the Binder |

Never stuff network calls or database queries into a converter just to "validate config." A syntactically valid endpoint URI is not guaranteed reachable; that is an operational/runtime concern, not a `ConversionService` task.

Validation should check conditions that are local, fast, and deterministic. External dependency checks need timeout/retry policies and deployment-appropriate startup failure strategies.

## 31. Cross-Field Validation Across Multiple Properties

A domain example with `connectTimeout` and `readTimeout`:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    @NotNull Duration connectTimeout,
    @NotNull Duration readTimeout
) {}
~~~

The requirement "`readTimeout` must be greater than or equal to `connectTimeout`" is not captured by two `@NotNull` annotations. Use a custom **class-level Bean Validation constraint** like `@ValidTimeoutPair` or an explicit validation step fitting your architecture.

Cross-field rules are **constraint validation**, not conversion. Both `10s` and `2s` convert to valid `Duration`s; the failure is violating `readTimeout >= connectTimeout`.

If a custom validator seems to need external resources, revisit the design: startup-phase validation should have minimal dependencies and clear messages.

## 32. Writing Helpful Error Messages

For custom constraints, messages should indicate:

- Which property or group is invalid.
- Which value rule or relationship was violated, without leaking secrets.
- The allowed range or a valid format example.
- Which source can fix it, if known.

Example message:

~~~text
app.worker.concurrency must be between 1 and 16
~~~

Or:

~~~text
app.client.read-timeout must be >= app.client.connect-timeout
~~~

For conversion errors, helpful messages state the target type:

~~~text
app.worker.poll-interval must be a valid Duration
(e.g. 250ms, 2s, 1m)
~~~

Never replace the entire stack trace with a vague message like "Invalid config." Preserve the cause so operators know whether it is mapping, conversion, or a constraint.

## 33. Troubleshooting When Using a Custom `Converter`

Some projects use custom domain types:

~~~java
public record CurrencyCode(String value) {}
~~~

with a custom converter:

~~~java
public final class CurrencyCodeConverter
        implements Converter<String, CurrencyCode> {

    @Override
    public CurrencyCode convert(String source) {
        String code = source.trim().toUpperCase();
        if (code.length() != 3) {
            throw new IllegalArgumentException(
                "Currency code must have 3 characters");
        }
        return new CurrencyCode(code);
    }
}
~~~

If the Binder cannot find a path from `String` to `CurrencyCode`, that is a **conversion configuration problem**. If the converter runs and throws an exception on `"LONGCODE"`, that is still a conversion failure at parsing time.

If an additional rule states "the currency code must be in the application's supported list," enforce that via Bean Validation or deliberate domain validation after type creation. This separates two questions:

1. Can the string produce a structurally valid `CurrencyCode`?
2. Is that code permitted by business policy?

Not every project must separate those two steps identically, yet distinguishing them keeps messages and tests focused on the right responsibility.

## 34. Binding Errors in Mutable JavaBeans vs. Immutable Records

The two binding models exhibit different failure modes.

### JavaBean Setter Binding

~~~java
@ConfigurationProperties(prefix = "app.pool")
public class PoolProperties {
    private int maxSize = 8;

    public int getMaxSize() {
        return maxSize;
    }

    public void setMaxSize(int maxSize) {
        this.maxSize = maxSize;
    }
}
~~~

If a setter is missing or a field cannot bind via JavaBean rules, values may fail to populate as expected. Inspect constructors, getters/setters, visibility, and bean registration.

### Record Constructor Binding

~~~java
@ConfigurationProperties(prefix = "app.pool")
public record PoolProperties(int maxSize) {}
~~~

When registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, the Binder uses the record constructor.

However:

~~~java
@Component
@ConfigurationProperties(prefix = "app.pool")
public record PoolProperties(int maxSize) {}
~~~

puts the type onto the regular component-construction path. Spring tries to autowire bean dependencies for constructor parameters instead of letting the Binder pass property values. Bean creation errors here stem from **wrong registration/instantiation**, not `@Min` or `max-size` values.

## 35. 10-Step Debugging Workflow

1. **Read the exception and root cause**, not just "Application run failed."
2. **Identify the failing stage:** file parse/load, bean registration, binding, conversion, validation, or service startup.
3. **Verify keys:** prefix, relaxed binding, field names, list indices, and nested paths.
4. **Verify value shapes:** does scalar/list/map structure match the Java target?
5. **Verify Java types:** do `Integer`, `Duration`, enums, or custom types have converters?
6. **Verify constraints:** `@NotBlank`, `@NotNull`, `@Min`, `@Valid`, and is the validator provider running?
7. **Check overriding sources:** profiles, imports, env vars, system properties, and CLI flags; check `Origin` if available.
8. **Check bean registration:** scan/enable annotations, packages, constructor- vs. setter-binding setup.
9. **Write a minimal test:** use `ApplicationContextRunner` to isolate one input failure; use integration tests for multi-source setups.
10. **Fix the right layer and verify startup** with valid values; never turn on error-ignoring flags to mask bugs.

Once startup succeeds, if runtime behavior is still wrong, check the bound values and how consumers use them. "No exception" does not guarantee every optional key received the intended value.

## 36. Error Identification Exercises

### Exercise 1: Unparseable Numeric Configuration

~~~properties
app.worker.concurrency=several
~~~

Java: `int concurrency` with `@Min(1)`.

**Answer:** conversion failure, because there is no integer to pass to `@Min(1)`.

### Exercise 2: Valid Integer Out of Range

~~~properties
app.worker.concurrency=0
~~~

Java: `@Min(1) int concurrency`.

**Answer:** validation failure when Bean Validation is enabled.

### Exercise 3: Missing Required String

`app.worker.name` is omitted; Java has `@NotBlank String name`.

**Answer:** if the Binder constructs the bean with `name=null` and validation is active, `@NotBlank` is violated; not a `String` parsing error.

### Exercise 4: List Written as an Object

~~~yaml
app:
  servers:
    host: one.example.test
~~~

Java: `List<Server> servers`.

**Answer:** binding shape mismatch; use a YAML sequence with `-` or change the model.

### Exercise 5: Misspelled Key with Unknown Fields Ignored

~~~properties
app.mail.hots=smtp.example.test
~~~

Java: `String host`, no validation.

**Answer:** startup may succeed without error, yet `host` never receives the value. That is why required keys need constraints or strict binding where appropriate.

### Exercise 6: Non-Existent Enum Constant

~~~properties
app.delivery.mode=INSTANTLY
~~~

Java: `DeliveryMode mode` where enum only defines `SYNC` and `ASYNC`.

**Answer:** conversion failure, not a `@Pattern` failure.

### Exercise 7: Un-Cascaded Nested Constraint

Root model has `@Validated`, nested field has `@Min`, without `@Valid` cascading configured.

**Answer:** Bean Validation may skip evaluating the nested constraint. Add `@Valid` and a provider—do not edit the YAML if it intentionally supplies an invalid test value.

### Exercise 8: Unparseable YAML

~~~yaml
app:
  tags: [one, two
~~~

**Answer:** Config Data parsing error, prior to binding/conversion/validation.

### Exercise 9: Error Comes from CLI, Not File

File has `app.retry.max-attempts=3`. Command adds `--app.retry.max-attempts=many`.

**Answer:** conversion failure on the effective value `"many"`; fix the CLI flag or higher-precedence source.

### Exercise 10: Unregistered Bean

A record has `@ConfigurationProperties`, yet the app never scans or enables that type.

**Answer:** bean registration failure; you cannot assume any constraints executed.

## 37. Real-World Log Reading Checklist

| Diagnostic Question | If "Yes", Focus On |
| --- | --- |
| YAML/parser error before any prefix appears? | Config loading, not Bean Validation |
| `required a bean ... could not be found`? | Bean registration / package scanning |
| `Failed to bind properties under ...`? | Inspect cause; can belong to any of the three categories |
| `Failed to convert ...` or converter exception? | Conversion |
| `@NotBlank`/`@Min`/constraint violation? | Validation |
| Key looks almost right with a missing letter? | Binding name/prefix, unknown fields |
| `Value` differs from the file you have open? | `PropertySource` precedence / active profile |
| `Origin` points to a different file? | Fix the winning source |
| `List` target yet YAML lacks `-`? | Binding structure |
| JavaBean type without setters? | Binding model |
| `@Component` record asking for `int`/`URI` beans? | Wrong instantiation/registration mechanism |
| Type-valid scalar breaking a business rule? | Constraint / domain validation |
| Are provider and `@Validated` configured? | Validation setup |
| Fails only in prod? | Profile-specific Config Data and overrides |

## 38. Summary

You can summarize the three layers with three questions:

- **Binding:** "Can I map the configuration structure onto the exact shape of my Java objects?"
- **Conversion:** "Can the source values convert into the Java types required by the model?"
- **Validation:** "Do the bound values satisfy all constraints and business rules?"

These are related layers of responsibility, not isolated silos: both conversion failures and validation failures can be **wrapped inside binding exceptions**. When troubleshooting, start with `Property`, `Value`, `Origin`, and especially `Reason`/root cause. Fix mapping errors in shape or registration; fix conversion errors in format or converters; fix constraint violations in values or intentional validation rules. Never disable `@Validated` or ignore invalid fields just to let the app boot, because a clear startup configuration error easily turns into unpredictable runtime behavior.