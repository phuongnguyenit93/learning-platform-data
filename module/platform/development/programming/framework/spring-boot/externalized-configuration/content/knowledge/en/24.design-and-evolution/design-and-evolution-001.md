# Building a Configuration Contract: Key Names, Types, Units, Defaults, and Constraints in Spring Boot

## 1. Configuration as a System API

A Spring Boot application can read parameters from `application.yml`, `application.properties`, environment variables, JVM system properties, command-line arguments, Config Data imports, and other sources. Because of this, the same artifact can run in development, staging, and production.

However, configuration keys are not merely internal variables. They form a **contract between application authors, operators, and the deployment system**. Once a key is placed into a Helm chart, Docker Compose, a secret manager, CI/CD, or partner documentation, renaming it or changing its meaning can cause failures similar to breaking a public Java API.

For example:

~~~yaml
acme:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test
    connect-timeout: 5s
    max-retries: 3
    buffer-size: 2MB
~~~

To qualify as a contract, the application must clearly answer:

- Does `connect-timeout: 5` mean 5 milliseconds or 5 seconds?
- Does `buffer-size: 2` mean 2 bytes or 2 megabytes?
- If `max-retries` is omitted, is there a default?
- Is `endpoint` required when `enabled=false`?
- Is HTTP allowed, or only HTTPS?
- Is `max-retries=-1` forbidden, or is it a sentinel for infinite retries?
- Which keys contain secrets and must not be logged?
- When both a file and an environment variable define the same key, which source wins?
- If a key is renamed, until when are existing deployments supported?

An under-specified configuration can **bind successfully by type** yet cause dangerous behavior: excessive retries, overly short timeouts, oversized buffer allocations, or connecting to the wrong environment.

> **Configuration contract** = stable key name + data type + unit + default/requiredness + valid bounds + precedence + security + upgrade rules.

The Java examples target Spring Boot 3.x, Java 17+, and `jakarta.validation`. For other versions, cross-check the API of the BOM in use.

## 2. Specification Template for a Key

A minimal contract table:

| Field | What to document |
| --- | --- |
| Canonical name | Canonical key in kebab-case |
| Prefix | Which module owns the key |
| Meaning | Which behavior uses it |
| Java type | `boolean`, `Duration`, `DataSize`, `URI`, `int`, enum, collection |
| Unit | `ms`/`s`, `B`/`KB`/`MB`; how a bare number without a suffix is interpreted |
| Default value | What the target object receives when the key is completely absent |
| Required | Always required or only under a specific condition |
| Valid domain | Min, max, regex, scheme, relationship with other keys |
| Allowed sources | YAML, env, secret, CLI; how overrides work |
| Sensitivity level | Public, internal, secret |
| Compatibility | Legacy name, deprecated status, replacement, and version |
| Tests | Missing, invalid, override, legacy, and edge cases |

Example for a data delivery module:

| Key | Type/Unit | Default | Rules |
| --- | --- | --- | --- |
| `acme.delivery.enabled` | Boolean | `false` | Enabled only when explicitly chosen by the operator |
| `acme.delivery.endpoint` | URI | None | Required when enabled, HTTPS absolute URI with host |
| `acme.delivery.connect-timeout` | Duration | `5s` | Greater than 0, at most `30s` |
| `acme.delivery.max-retries` | int | `3` | From 0 to 10 |
| `acme.delivery.buffer-size` | DataSize | `2MB` | From `64KB` to `64MB` |
| `acme.delivery.security.api-key-enabled` | Boolean | `false` | Enables the API key mechanism |
| `acme.delivery.security.api-key` | String/secret | None | Required if enabled and API-key auth is enabled |

This is an **application-designed contract**, not a built-in Spring Boot key set.

## 3. Key Naming Conventions: kebab-case and Namespaces

Spring Boot recommends the canonical form using lowercase letters and hyphens between words within a segment:

~~~properties
acme.delivery.connect-timeout=5s
acme.delivery.max-retries=3
acme.delivery.buffer-size=2MB
~~~

Best practices:

1. Use an application- or module-specific prefix: `acme.delivery`.
2. Name by meaning: `connect-timeout`, not just `timeout` if multiple timeout types exist.
3. Publish a single canonical name for operators.
4. Avoid names tied to internal classes or specific environments such as `prod-timeout`.
5. Keep segments consistent, e.g., `max-retries` instead of mixing `retryMax` and `max_retry`.
6. Do not occupy the `spring.*` prefix for application business keys.
7. Treat a published key as an API that requires lifecycle management.

An illustrative namespace table:

~~~text
acme.delivery.*   — sending data to partners
acme.catalog.*    — product synchronization
acme.cache.*      — business caching
acme.audit.*      — audit logging
~~~

Avoid a generic `app.timeout` key used by three teams with three different meanings.

### 3.1. Java Fields Differ from Canonical Key Names

~~~java
@ConfigurationProperties(prefix = "acme.delivery")
public record DeliveryProperties(Duration connectTimeout) {
}
~~~

~~~yaml
acme:
  delivery:
    connect-timeout: 5s
~~~

Java uses camelCase for fields/components, while YAML publishes kebab-case. Spring Boot relaxed binding bridges the two forms; there is no need to write Java fields with hyphenated names.

### 3.2. Mapping to OS Environment Variables

Under the environment variable rules for `@ConfigurationProperties`:

- Dots `.` are replaced with underscores.
- Hyphens `-` are **removed**.
- Characters are converted to uppercase.

For example:

~~~text
acme.delivery.enabled          → ACME_DELIVERY_ENABLED
acme.delivery.connect-timeout  → ACME_DELIVERY_CONNECTTIMEOUT
acme.delivery.max-retries      → ACME_DELIVERY_MAXRETRIES
acme.delivery.buffer-size      → ACME_DELIVERY_BUFFERSIZE
~~~

Do not casually assert that `ACME_DELIVERY_CONNECT_TIMEOUT` will always bind identically to `ACME_DELIVERY_CONNECTTIMEOUT` in every case. Explicitly document the form specified by Spring Boot in deployment guides.

When using placeholders or `@Value`, prefer the canonical name:

~~~java
@Value("${acme.delivery.connect-timeout:5s}")
private Duration connectTimeout;
~~~

However, with multiple related properties in a group, `@ConfigurationProperties` is usually easier to test and maintain than scattering dozens of `@Value` annotations across services.

## 4. Java Types Express Meaning Instead of Just Holding Strings

Do not pick `String` for every value and parse it manually at each consumer.

| Meaning | Recommended Type | Configuration Example |
| --- | --- | --- |
| On/off | `boolean`, `Boolean` | `true` |
| Retry count | `int`, `Integer` | `3` |
| Large count | `long` | `1000000` |
| Timeout | `java.time.Duration` | `750ms`, `5s` |
| Size / Capacity | `DataSize` | `512KB`, `2MB` |
| Endpoint URI | `java.net.URI` | `https://api.example.test` |
| Closed choice | `enum` | `SYNC`, `ASYNC` |
| Ordered list | `List<T>` | YAML sequence |
| Lookup by name | `Map<String,T>` | YAML map |
| Credential | Secret value/`String` | Supplied from secret store |

### 4.1. Primitive vs Wrapper and Missing Properties

~~~java
private int retries;
~~~

`int` has a Java default of 0; if the key is missing, this value can mask the fact that it was never configured.

~~~java
@NotNull
private Integer retries;
~~~

With an uninitialized `Integer`, `null` lets you check for "not declared". If 0 is an intentional valid default, publish it. If the key is required, use a nullable type with appropriate validation.

### 4.2. An Enum Is a Versioned Contract

~~~java
public enum DeliveryMode {
    DISABLED,
    ASYNC,
    SYNC
}
~~~

Choose an enum when the value set is genuinely closed. Renaming an enum constant can break binding for older inputs; if you rename one, provide a compatibility layer or migration. A value set that changes frequently may not be a good fit for an enum.

## 5. Duration: Publish Units, Do Not Rely on Bare Numbers

A `Duration` property in Spring Boot interprets an integer without a suffix as **milliseconds** by default, unless `@DurationUnit` metadata specifies another unit.

~~~properties
acme.delivery.connect-timeout=5
~~~

Without a unit-overriding annotation, this is **5ms**, not 5s.

Write explicitly:

~~~properties
acme.delivery.connect-timeout=5s
~~~

Suffixes supported by Spring Boot include:

| Suffix | Meaning |
| --- | --- |
| `ns` | Nanoseconds |
| `us` | Microseconds |
| `ms` | Milliseconds |
| `s` | Seconds |
| `m` | Minutes |
| `h` | Hours |
| `d` | Days |

ISO-8601 format such as `PT5S` can also be used. For operators, `5s` is usually easier to read.

Changing the default unit for values **without a suffix**:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.convert.DurationUnit;

@DurationUnit(ChronoUnit.SECONDS)
private Duration connectTimeout;
~~~

Then `connect-timeout: 5` is interpreted as 5 seconds. However, if the property **does not exist**, the annotation does not generate a value of 5 seconds; it only describes the **unit**, not the default.

Contract recommendation: new deployment examples should always include explicit suffixes. If upgrading from a `long` field in seconds to `Duration`, use `@DurationUnit(SECONDS)` when you need to preserve the meaning of legacy bare numbers.

## 6. DataSize: Publish Unit System and Bounds

Spring Boot supports `org.springframework.util.unit.DataSize` to represent byte sizes.

~~~properties
acme.delivery.buffer-size=2MB
~~~

| Unit | Suffix | Bytes |
| --- | --- | ---: |
| Byte | `B` | 1 |
| Kilobyte | `KB` | 1,024 |
| Megabyte | `MB` | 1,048,576 |
| Gigabyte | `GB` | 1,073,741,824 |
| Terabyte | `TB` | 1,099,511,627,776 |

These suffixes in `DataSize` use binary conventions (powers of 1024), not decimal `1MB=1,000,000B`.

~~~java
DataSize size = DataSize.ofMegabytes(2);
long bytes = size.toBytes();  // 2097152
~~~

A bare number without a suffix defaults to **bytes**:

~~~yaml
acme:
  delivery:
    buffer-size: 2
~~~

Without other metadata, this is 2 bytes, not 2MB.

You can define a default unit:

~~~java
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataUnit;

@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize bufferSize;
~~~

Then `buffer-size: 2` is interpreted as 2MB, while `buffer-size: 512KB` remains 512KB because it has an explicit suffix.

**Do not confuse unit with default:** `@DataSizeUnit(MEGABYTES)` does not turn a missing field into 1MB or 2MB. To define a default, declare an initializer or `@DefaultValue`.

### 6.1. Bounds Differ from Type Conversion

`DataSize.ofBytes(0)` and negative values can be parsed and represented, yet the application may require a minimum buffer of 64KB. Successful conversion **does not mean** the configuration is valid; validation must be added.

## 7. Required, Optional, and Default Are Three Different Policies

A key can be designed as:

- **Required**: fail startup if missing.
- **Optional + safe default**: use an intentional default if missing.
- **Optional + absent means disabled**: absence means "do not use".
- **Conditionally required**: e.g., endpoint is required if the feature is enabled.
- **Mutually constrained**: e.g., combined retries and timeout must not exceed a time budget.

For example:

| Key | Policy | Rationale |
| --- | --- | --- |
| `enabled` | Default false | Do not enable external integrations automatically |
| `connect-timeout` | Default 5s | Bounded wait time |
| `max-retries` | Default 3 | Avoid infinite retries |
| `buffer-size` | Default 2MB | Predictable resource usage |
| `endpoint` | Required when enabled | Cannot send without a destination |
| `security.api-key` | Required when auth enabled | No fallback secret |

### 7.1. Defaults in a JavaBean Initializer

~~~java
@ConfigurationProperties(prefix = "acme.delivery")
public class DeliveryProperties {
    private Duration connectTimeout = Duration.ofSeconds(5);
    private int maxRetries = 3;

    // getters/setters
}
~~~

When the binder receives no override, the initializer provides the value. If a valid property comes from the environment, the binder can override it according to the winning property source.

### 7.2. Defaults in Constructor/Record Binding

In Spring Boot 3.x:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import java.time.Duration;

@ConfigurationProperties(prefix = "acme.delivery")
public record DeliveryProperties(
    @DefaultValue("5s") Duration connectTimeout,
    @DefaultValue("3") int maxRetries) {
}
~~~

`@DefaultValue("5s")` is converted to `Duration` when no value is supplied. It differs from `@DurationUnit(SECONDS)`, which only changes how an **already present** bare number is interpreted.

### 7.3. Object Defaults Do Not Automatically Appear in Environment

Suppose the record has a default of `5s`, but no `acme.delivery.connect-timeout` property exists in any source.

~~~java
DeliveryProperties props = ...; // bound
Duration configured = props.connectTimeout(); // PT5S

String raw = environment.getProperty(
        "acme.delivery.connect-timeout"); // may be null
~~~

Spring Boot does not write configuration object defaults back into a `PropertySource`. This matters when a `@ConditionalOnProperty` or another component reads `Environment` directly.

If components need the same default, prefer injecting the shared properties bean, or supply the default via a configuration source suited to the contract. There is no reason to assume `Environment` getters will automatically return `@DefaultValue`.

## 8. Complete Example with a `@ConfigurationProperties` Record

Designing a model for the delivery module:

~~~java
package com.example.delivery;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.delivery")
public record DeliveryProperties(
        @DefaultValue("false") boolean enabled,
        URI endpoint,
        @NotNull @DefaultValue("5s") Duration connectTimeout,
        @Min(0) @Max(10) @DefaultValue("3") int maxRetries,
        @NotNull @DefaultValue("2MB") DataSize bufferSize,
        @Valid @DefaultValue Security security) {

    public record Security(
            @DefaultValue("false") boolean apiKeyEnabled,
            String apiKey) {
    }
}
~~~

Explanation:

- `enabled` is off by default.
- `endpoint` can be null, because the contract only requires it when enabled=true.
- `connectTimeout` defaults to 5s and is non-null.
- `maxRetries` is bounded to 0–10 via Bean Validation.
- `bufferSize` defaults to 2MB; min/max bounds require a custom rule.
- `Security` is a nested record; `@Valid` enables cascading constraints into the nested object.
- `@DefaultValue` without arguments on the nested component allows creating an instance from its defaults when the corresponding section is absent.

Registering in the application:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DeliveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DeliveryApplication.class, args);
    }
}
~~~

Or register explicitly with `@EnableConfigurationProperties(DeliveryProperties.class)` on a scanned configuration class.

### 8.1. Sample YAML

~~~yaml
acme:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test
    connect-timeout: 5s
    max-retries: 3
    buffer-size: 2MB
    security:
      api-key-enabled: true
      api-key: "${DELIVERY_API_KEY}"
~~~

`DELIVERY_API_KEY` must be supplied via an appropriate environment/secret mechanism. Never store real API keys in example files.

## 9. Binding, Conversion, and Semantic Validation

A contract needs to distinguish three layers:

| Layer | Sample Error | Where Detected |
| --- | --- | --- |
| Config Data syntax | Invalid YAML indentation | Parser |
| Type conversion | `connect-timeout: abc` | Binder/Converter |
| Business rule | `connect-timeout: 0s`, `max-retries: 99` | Validator |

Because `Duration.ZERO` is a valid `Duration`, conversion alone cannot decide whether it is acceptable as a network timeout.

### 9.1. Jakarta Bean Validation

Spring Boot 3.x uses `jakarta.validation.*` when a compatible Bean Validation implementation is present, typically via:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

For example:

~~~java
@Min(0) @Max(10) int maxRetries
@NotNull Duration connectTimeout
~~~

If an operator sets `max-retries=99`, the application can fail when creating the configuration properties bean instead of starting to process requests with an unreasonable retry count.

However, `@NotNull Duration` does not require a positive Duration. `@NotNull URI` also does not require the URI to have an HTTPS scheme and a host. Additional logic is needed.

## 10. Cross-Field Rules and Custom Spring Validator

Example contract:

~~~text
if enabled=false:
    endpoint may be absent

if enabled=true:
    endpoint must be an absolute HTTPS URI with a host

if enabled=true and security.api-key-enabled=true:
    security.api-key must not be null/blank

always:
    timeout > 0 and <= 30s
    buffer-size >= 64KB and <= 64MB
    max-retries from 0 through 10
~~~

An illustrative validator:

~~~java
package com.example.delivery;

import java.net.URI;
import java.time.Duration;

import org.springframework.util.unit.DataSize;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class DeliveryPropertiesValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return DeliveryProperties.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        DeliveryProperties props = (DeliveryProperties) target;

        Duration time = props.connectTimeout();
        if (time == null || time.isZero()
                || time.isNegative()
                || time.compareTo(Duration.ofSeconds(30)) > 0) {
            errors.rejectValue("connectTimeout",
                "delivery.timeout.invalid",
                "connect-timeout must be positive and at most 30s");
        }

        DataSize size = props.bufferSize();
        if (size == null
                || size.compareTo(DataSize.ofKilobytes(64)) < 0
                || size.compareTo(DataSize.ofMegabytes(64)) > 0) {
            errors.rejectValue("bufferSize",
                "delivery.buffer.invalid",
                "buffer-size must be between 64KB and 64MB");
        }

        if (props.enabled()) {
            URI endpoint = props.endpoint();
            if (endpoint == null
                    || !endpoint.isAbsolute()
                    || !"https".equalsIgnoreCase(endpoint.getScheme())
                    || endpoint.getHost() == null) {
                errors.rejectValue("endpoint",
                    "delivery.endpoint.invalid",
                    "endpoint must be an absolute HTTPS URI with a host");
            }

            DeliveryProperties.Security security = props.security();
            if (security != null && security.apiKeyEnabled()
                    && (security.apiKey() == null
                        || security.apiKey().isBlank())) {
                errors.rejectValue("security.apiKey",
                    "delivery.security.keyMissing",
                    "security.api-key is required with API-key auth");
            }
        }
    }
}
~~~

Register the dedicated validator with Spring Boot's bean name:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.Validator;

@Configuration(proxyBeanMethods = false)
public class DeliveryValidationConfiguration {

    @Bean(name = "configurationPropertiesValidator")
    public static Validator configurationPropertiesValidator() {
        return new DeliveryPropertiesValidator();
    }
}
~~~

The factory method should be **static** because Spring Boot may need the validator very early in the lifecycle. `supports` must check the type to avoid mistakenly casting other `@ConfigurationProperties` beans.

The validator uses `errors.rejectValue(...)` to report the field and reason. Do not print raw secret values. Beyond Spring's `Validator`, a class-level Jakarta custom constraint can be used if the codebase prefers that style.

If nested `Security` has additional rules, handle null according to the contract without assuming the nested object is always present in every binding arrangement.

## 11. Do Not Use Defaults to Mask Invalid Configuration Data

Two distinct cases:

~~~text
Missing acme.delivery.max-retries:
  uses default 3

Present acme.delivery.max-retries=not-a-number:
  conversion error; cannot fall back to default 3 as if the key were absent

Present acme.delivery.max-retries=999:
  binds int successfully but violates @Max(10)
~~~

`@DefaultValue` is not a mechanism for auto-healing broken inputs. When an operator supplies an invalid value, the appropriate behavior for an important key is to report a clear error, typically failing startup.

Silently falling back to a default can cause the application to run **differently than expected** with no diagnostic signal.

## 12. PropertySource Precedence Is Also Part of the Contract

Suppose you have a file:

~~~yaml
acme:
  delivery:
    connect-timeout: 5s
~~~

Environment variable:

~~~bash
ACME_DELIVERY_CONNECTTIMEOUT=8s
~~~

Command-line argument:

~~~bash
java -jar app.jar --acme.delivery.connect-timeout=10s
~~~

In standard Spring Boot mode, CLI has higher precedence than OS environment, and OS environment has higher precedence than Config Data files. Without a higher special source, the effective value is **10s**.

| Present Sources | Resulting Value |
| --- | --- |
| No key anywhere | Object default `5s` |
| File `5s` | `5s` |
| File `5s` and env `8s` | `8s` |
| File `5s`, env `8s`, CLI `10s` | `10s` |

Do not combine them additively, and do not treat the object default as a high-priority source.

Note that source order can be customized or affected by test property sources and command-line processing. The contract should state which sources a deployment environment is allowed to override with.

### 12.1. Profiles and Config Data

Profile-specific files such as `application-prod.yml` have precedence within the Config Data group, yet can still be overridden by OS environment variables, JVM system properties, or CLI arguments.

Bootstrap-level keys such as `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` must be available **early** to control file discovery; they should not be placed solely inside the very file they are meant to locate.

A deployment template should specify the profile, config location, environment variable names, and required/optional policy for files.

## 13. List/Map: The Contract Must Describe Override Semantics

Suppose:

~~~yaml
# application.yml
acme:
  delivery:
    targets:
      - apac
      - eu
    weights:
      apac: 2
      eu: 1
~~~

Profile `prod`:

~~~yaml
# application-prod.yml
acme:
  delivery:
    targets:
      - apac
    weights:
      apac: 3
      us: 1
~~~

With standard Spring Boot collection binding:

- A **List** from a higher-precedence source replaces the previous list: `targets=[apac]`.
- A **Map** can merge keys, taking duplicate keys from the higher-precedence source: `weights={apac:3,eu:1,us:1}`.

An operator assuming two Lists concatenate may accidentally drop targets. Therefore, when a contract uses a List, explicitly state "override replaces entire list" and provide full profile examples.

For Maps, also watch the syntax of keys containing special characters or dots; when keys must be preserved verbatim, Spring Boot has dedicated bracket notation. Do not design arbitrary keys without binding tests.

## 14. Secrets Have Different Policies Than Regular Properties

Never set a production API key as a default just to make the app "easy to run". For secrets, the contract must classify:

- Is it required, and when?
- Which injection sources are accepted?
- Are secret files / config trees supported?
- Does rotation require a restart/refresh?
- How are missing-secret errors reported without leaking the value?
- May the property be exposed via Actuator or startup logs?

YAML example referencing an environment variable:

~~~yaml
acme:
  delivery:
    security:
      api-key-enabled: true
      api-key: "${DELIVERY_API_KEY}"
~~~

`DELIVERY_API_KEY` must be supplied via an appropriate secrets mechanism—such as Docker/Kubernetes Secrets, a secret store, or a config tree depending on infrastructure.

Never log:

~~~java
log.info("allDeliveryConfig={}", deliveryProperties);
~~~

if the object may contain `apiKey`. A record with an auto-generated `toString()` requires extra caution when logging objects.

Good error message:

~~~text
acme.delivery.security.api-key is required when API-key auth is enabled
~~~

Bad error message:

~~~text
Invalid API key value = actual-secret-string...
~~~

`@ConfigurationProperties` and `@Validated` are not secret managers. They assist with binding and validation; data protection still depends on sources, permissions, logs, and how the application handles values.

## 15. Metadata: Helping IDEs and Operators Discover Keys

A contract should be structured so tooling can provide autocomplete, descriptions, defaults, and deprecation notices.

Spring Boot supports configuration metadata at:

~~~text
META-INF/spring-configuration-metadata.json
~~~

With Maven, the annotation processor can be added:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Depending on the Maven/Gradle compiler and annotation processing setup, ensure the processor actually runs.

An illustrative metadata JSON:

~~~json
{
  "properties": [
    {
      "name": "acme.delivery.connect-timeout",
      "type": "java.time.Duration",
      "description": "Connection establishment timeout.",
      "defaultValue": "5s"
    },
    {
      "name": "acme.delivery.max-retries",
      "type": "java.lang.Integer",
      "description": "Maximum number of retries.",
      "defaultValue": 3
    }
  ]
}
~~~

Metadata supports tooling and documentation; **it is not a runtime `PropertySource`**. Editing `defaultValue` in metadata JSON does not automatically change the bean's runtime default.

### 15.1. Hints and Additional Descriptions

You can place a file at:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

For example:

~~~json
{
  "properties": [
    {
      "name": "acme.delivery.endpoint",
      "type": "java.net.URI",
      "description": "Absolute HTTPS URI when delivery is enabled."
    }
  ],
  "hints": [
    {
      "name": "acme.delivery.mode",
      "values": [
        {"value": "sync", "description": "Synchronous calls."},
        {"value": "async", "description": "Asynchronous delivery."}
      ]
    }
  ]
}
~~~

Hints help IDEs suggest options; they do not enforce validation. If only sync/async are allowed, use an enum or a runtime validation constraint.

## 16. Renaming a Key Is a Versioned Change

Suppose an older application has:

~~~properties
acme.delivery.retry-count=3
~~~

The new version wants to replace it with:

~~~properties
acme.delivery.max-retries=3
~~~

Renaming only the Java field is insufficient. Older deployments may still pass `retry-count` while the Binder no longer picks it up as intended. If the new field has a default of `3`, the mistake may even be masked.

A sensible migration workflow:

1. Announce the new key and the rationale.
2. Decide whether a transition period supporting both old and new keys is needed.
3. If compatibility is needed, implement it explicitly at runtime, not just in docs.
4. Define **which wins if both old and new keys are present**.
5. Emit controlled warnings when the old key is still used.
6. Update Helm/Compose/Kubernetes/systemd/CI/secrets.
7. Test both configuration forms.
8. Mark deprecated in metadata and include guidance in release notes.
9. Remove old support only according to your versioning policy.

### 16.1. Deprecation Metadata Does Not Create a Runtime Alias

In `additional-spring-configuration-metadata.json`:

~~~json
{
  "properties": [
    {
      "name": "acme.delivery.retry-count",
      "type": "java.lang.Integer",
      "deprecation": {
        "level": "warning",
        "reason": "Renamed for consistency with other retry settings.",
        "replacement": "acme.delivery.max-retries"
      }
    }
  ]
}
~~~

This helps IDEs warn that the old key is about to be replaced. However, `replacement` **does not automatically make the Binder treat the old key as an alias for the new key**. Runtime support for the old key requires corresponding code or a migration mechanism.

You can specify:

~~~text
New key only: use new.
Old key only: accept old + warn.
Both: use new + warn about old.
Neither: use default.
~~~

Contract tests must verify the exact policy rather than leaving it to chance based on precedence between two differently named keys.

## 17. Changing Type, Unit, or Default Can Also Be Breaking

| Change | Risk |
| --- | --- |
| `long timeoutSeconds` → `Duration` defaulting to ms | Value `5` changes from 5s to 5ms |
| `long bufferBytes` → `DataSize` with default unit MB | Value `2` changes meaning |
| `String mode` → enum | Legacy mode values may fail to parse |
| `List<T>` → `Map<String,T>` | Changes YAML shape and merge semantics |
| Default retries `3` → `0` | Behavior when key is absent changes completely |
| Accepting 60s timeout → max 30s | Existing deployments may fail startup |
| Optional endpoint → required | All manifests must be updated |
| Optional secret → required | Secure provisioning needed before deploy |

If an old `long timeoutSeconds` field previously interpreted bare numbers as seconds, when upgrading to `Duration` you can use:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration timeout;
~~~

Similarly for sizes:

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize buffer;
~~~

This preserves how bare numbers are interpreted when needed. New documentation should still require explicit suffixes such as `5s` and `2MB`, along with a migration plan for the old key.

Do not treat changing a default as "internal" if it affects production whenever operators do not override the key.

## 18. Operator Documentation Needs Complete Examples

A good configuration README should include a contract table, YAML snippets, OS environment examples, secret injection guidance, common errors, migration notes, and verification steps.

Development:

~~~yaml
acme:
  delivery:
    enabled: false
    connect-timeout: 5s
    max-retries: 1
    buffer-size: 512KB
~~~

Production:

~~~yaml
acme:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test
    connect-timeout: 3s
    max-retries: 3
    buffer-size: 8MB
    security:
      api-key-enabled: true
      api-key: "${DELIVERY_API_KEY}"
~~~

Corresponding OS env:

~~~bash
ACME_DELIVERY_ENABLED=true
ACME_DELIVERY_CONNECTTIMEOUT=3s
ACME_DELIVERY_MAXRETRIES=3
ACME_DELIVERY_BUFFERSIZE=8MB
~~~

For the API key, inject via a dedicated secret mechanism. Never log or commit credentials.

When documenting defaults, state **what happens when the key is missing**, not just a value shown in an example file. When documenting requiredness, state whether errors occur **at startup or upon request**, and under what conditions.

## 19. Testing the Contract with `ApplicationContextRunner`

Spring Boot's `ApplicationContextRunner` is well-suited for testing binding and startup validation in a small scope.

~~~java
package com.example.delivery;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesContractTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ConfigurationPropertiesAutoConfiguration.class))
            .withUserConfiguration(
                Registration.class,
                DeliveryValidationConfiguration.class);

    @Test
    void usesSafeDefaultsWhenDisabled() {
        runner.withPropertyValues("acme.delivery.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();

                DeliveryProperties props =
                    context.getBean(DeliveryProperties.class);

                assertThat(props.enabled()).isFalse();
                assertThat(props.connectTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(5));
                assertThat(props.maxRetries()).isEqualTo(3);
                assertThat(props.bufferSize().toBytes())
                    .isEqualTo(2L * 1024 * 1024);
            });
    }

    @Test
    void bindsExplicitUnits() {
        runner.withPropertyValues(
            "acme.delivery.enabled=true",
            "acme.delivery.endpoint=https://gateway.example.test",
            "acme.delivery.connect-timeout=750ms",
            "acme.delivery.buffer-size=512KB")
            .run(context -> {
                assertThat(context).hasNotFailed();

                DeliveryProperties props =
                    context.getBean(DeliveryProperties.class);

                assertThat(props.connectTimeout())
                    .isEqualTo(java.time.Duration.ofMillis(750));
                assertThat(props.bufferSize().toBytes())
                    .isEqualTo(512L * 1024);
            });
    }

    @Test
    void rejectsRetriesAboveMaximum() {
        runner.withPropertyValues(
            "acme.delivery.enabled=true",
            "acme.delivery.endpoint=https://gateway.example.test",
            "acme.delivery.max-retries=99")
            .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void rejectsEnabledDeliveryWithoutEndpoint() {
        runner.withPropertyValues(
            "acme.delivery.enabled=true")
            .run(context -> assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class Registration {
    }
}
~~~

This test relies on the model and validator from the previous sections. If using Jakarta constraints, ensure a compatible Bean Validation implementation (typically `spring-boot-starter-validation`) is on the test runtime classpath.

### 19.1. Cases Not to Skip

| Input | Expectation |
| --- | --- |
| Missing optional keys | Uses safe defaults |
| `enabled=false`, missing endpoint | Succeeds if contract allows |
| `enabled=true`, missing endpoint | Fails startup |
| `endpoint=http://...` | Fails if HTTPS is required |
| `connect-timeout=0s` | Fails |
| `connect-timeout=31s` | Fails |
| `connect-timeout=750ms` | Parses accurately |
| `buffer-size=1B` | Fails if minimum is 64KB |
| `max-retries=-1` | Fails |
| `max-retries=11` | Fails |
| `max-retries=abc` | Fails conversion |
| API-key auth enabled, secret missing | Fails without leaking secret |
| Env var overrides YAML | Receives value per precedence |
| Legacy + new key both declared | Follows migration policy |

Do not write only happy-path tests, because contract bugs usually surface with missing, invalid, or legacy-formatted inputs.

## 20. Distinguishing Binding Tests from Real Config Data Tests

`ApplicationContextRunner.withPropertyValues(...)` creates test property sources and works well for verifying binding. However, it **does not prove** that `application-prod.yml` files or `spring.config.import` entries are fully loaded by `SpringApplication` in a real deployment.

When the contract depends on:

- Active profiles.
- Config Data locations or imports.
- Environment variable names.
- Docker/Kubernetes mounts.
- Precedence between files and CLI.
- Startup fail-fast on missing secrets.

Add integration/smoke tests using the appropriate `SpringApplication` path and realistic manifests. With Spring TestContext, note that `@TestPropertySource` and `@DynamicPropertySource` have their own precedence, so tests using them can **differ** from production source ordering.

A deployment smoke test can run with non-sensitive environment configuration and assert a marker such as `acme.deployment.id`. It should not dump the entire `Environment`.

## 21. Contracts Must Balance Fail-Fast and Availability

Errors that should be caught early:

- Wrong URI scheme or host.
- Retries exceeding bounds.
- Zero timeout in an API requiring a positive timeout.
- Missing required secret.
- Two incompatible fields.

Checks that should not casually be placed inside a configuration validator:

- Attempting database/HTTP connections with long waits.
- Calling external APIs to validate tokens while the binder is running.
- Reading repositories or using uninitialized service beans.
- Modifying configuration or writing files as a validation side effect.

Clearly separate **data-valid configuration** from **external dependencies actually being ready**. For the latter, use health/readiness checks or integration verification with dedicated timeouts and policies.

## 22. When Writing a Reusable Spring Boot Starter

A starter may be consumed by many applications, so its configuration contract must be even more stable:

1. Use a dedicated namespace that does not collide with built-in keys.
2. Provide type-safe `@ConfigurationProperties`.
3. Document defaults, units, allowed values, and missing-key behavior.
4. Generate metadata and documentation automatically where appropriate.
5. Register auto-configuration with clear conditions.
6. Do not automatically enable production connections just because the starter is on the classpath, unless the contract permits it.
7. Never create default secrets.
8. Add tests for a project that **does not configure the starter**.
9. Provide a deprecation policy and release notes when changing keys.
10. Cross-check support per Spring Boot version.

With `@ConditionalOnProperty`, remember that **defaults in `@ConfigurationProperties` do not automatically appear in `Environment`**. Conditions reading `Environment` must intentionally define `matchIfMissing`/`havingValue` or source defaults; do not rely on a record initializer magically influencing a condition.

## 23. Common Design Mistakes

| Misconception | Correct Understanding |
| --- | --- |
| "Having `@ConfigurationProperties` means we have a contract." | A contract needs clear names, types, units, defaults, constraints, precedence, and upgrade rules. |
| "Relaxed binding lets us name keys arbitrarily." | It follows specific rules; still publish a single canonical form. |
| "`Duration` interprets `5` as 5s." | The default is typically 5ms without `@DurationUnit`. |
| "`DataSize` interprets `2` as 2MB." | The default is typically 2B without `@DataSizeUnit`. |
| "`@DurationUnit` creates a default." | It only specifies the unit for an already-present bare number. |
| "`@DefaultValue` updates `Environment`." | No; object fallbacks do not create a `PropertySource`. |
| "Successful URI parsing means a safe HTTPS URL." | Semantic validation is required for scheme/host and custom policies. |
| "Successful value conversion means valid." | Conversion is distinct from validation. |
| "Renaming a Java field is a safe rename." | Legacy deployments can lose key binding. |
| "Metadata `replacement` creates an alias automatically." | No; runtime migration requires explicit implementation. |
| "A profile List concatenates with the default List." | Lists are normally replaced, not concatenated. |
| "Secrets can have production defaults in the repo." | Real credentials must not exist in artifacts or docs. |
| "`@ConditionalOnProperty` sees record defaults." | Conditions read `Environment`, not Java object defaults. |
| "`withPropertyValues` tests prove real YAML/imports." | That only tests binding from test properties; test Config Data separately. |

## 24. Exercise 1 — Designing a Contract for an Event Processor

Requirements include:

~~~text
processor.enabled
processor.max-in-flight
processor.retry-delay
processor.max-payload
processor.dead-letter-topic
~~~

Propose types, defaults, and constraints.

One approach:

| Key | Java Type | Default | Constraint |
| --- | --- | --- | --- |
| `acme.processor.enabled` | boolean | `false` | Enabled only when chosen by the operator |
| `acme.processor.max-in-flight` | int | `16` | 1–256 when enabled |
| `acme.processor.retry-delay` | Duration | `1s` | >0, <=1m |
| `acme.processor.max-payload` | DataSize | `1MB` | 1KB–32MB |
| `acme.processor.dead-letter-topic` | String | None | Required when dead-letter mode is enabled |

**Explanation:** names reflect domain meaning; types support units; defaults are safe; rules check not only types but also cap resource consumption.

## 25. Exercise 2 — Spotting Under-Specified Contracts

Legacy code:

~~~java
@ConfigurationProperties(prefix = "app")
public class BadProperties {
    private long timeout = 5;
    private long buffer = 2;
    private int retries = -1;
    // getters/setters
}
~~~

Issues:

- Prefix is overly broad and prone to collisions.
- `timeout` does not state connect/read/total timeout.
- `5` states no unit.
- `buffer=2` does not clarify bytes vs MB.
- `retries=-1` has no defined semantics.
- No min/max validation.
- No way to fail when a required key is missing.
- No documentation on env variable names, migration, and precedence.

A better design: `acme.delivery.connect-timeout=5s` of type `Duration`, `acme.delivery.buffer-size=2MB` of type `DataSize`, and `acme.delivery.max-retries=3` bounded in `[0,10]`.

## 26. Exercise 3 — Predicting Binding

Record:

~~~java
@ConfigurationProperties(prefix = "acme.delivery")
public record SimpleProperties(
    @DefaultValue("5s") Duration connectTimeout,
    @DefaultValue("2MB") DataSize bufferSize,
    @DefaultValue("3") int maxRetries) {
}
~~~

**A. None of the three keys are configured.** Bound values: 5s, 2MB, 3.

**B. YAML has `connect-timeout: 10`.** Without `@DurationUnit`, bare numbers are interpreted in ms: result is 10ms.

**C. YAML has `buffer-size: 512KB`.** Result is 512KB = 524,288 bytes.

**D. YAML has `max-retries: 3`, OS env has `ACME_DELIVERY_MAXRETRIES=6`.** In normal mode, env wins and the result is 6.

**E. YAML has `max-retries: 99` with no validator.** Binding to `int` succeeds; a constraint is required to enforce business bounds.

**F. No `connect-timeout` key; record uses default 5s; query `Environment`.** `Environment.getProperty(...)` may return null; record defaults do not automatically become properties.

## 27. Exercise 4 — Upgrading Units Without Changing Legacy Value Meaning

Legacy code:

~~~java
private long timeoutSeconds = 5;
~~~

Published:

~~~properties
acme.delivery.timeout-seconds=5
~~~

Goal: move to `Duration` while still supporting legacy input.

Steps:

1. Confirm legacy meaning: bare numbers are seconds.
2. Define the new key, how the old key is accepted, and the support window.
3. For a `Duration` target accepting bare numbers, apply `@DurationUnit(ChronoUnit.SECONDS)` if preserving semantics is needed.
4. New docs use `5s` instead of bare `5`.
5. Test `5`, `5s`, `500ms`, and missing cases.
6. Define the outcome when both old and new appear together.
7. Use deprecation metadata and a migration guide.
8. Never silently change `5` into 5ms in production.

Similarly, upgrading `bufferSizeMegabytes=2` to `DataSize` may require `@DataSizeUnit(MEGABYTES)` to avoid altering the meaning of legacy bare numbers.

## 28. Exercise 5 — Conditionally Required Secret

Given the contract:

~~~text
acme.delivery.enabled=false
acme.delivery.security.api-key-enabled=false
acme.delivery.security.api-key=<absent>
~~~

When must `api-key` be present?

Under the sample contract: when **delivery enabled=true** and **api-key-enabled=true**. If either is false, missing the secret is normal. Hence unconditional `@NotBlank` may be inappropriate; use a cross-field rule.

Error messages should state only that the required secret is missing, without printing the secret or the entire properties bean.

## 29. Pre-Release Checklist

- [ ] Every key has a canonical name and clear owner/prefix.
- [ ] Types reflect real quantities: Boolean, Duration, DataSize, URI, enum...
- [ ] Bare-number forms and default units are published.
- [ ] YAML examples use explicit suffixes for durations and data sizes.
- [ ] Required, optional, and conditionally required keys are distinguished.
- [ ] Defaults are safe and do not mask malformed inputs.
- [ ] Cross-field rules, min/max, and validation are actually enforced.
- [ ] Startup errors tell operators the key and violated rule.
- [ ] Env variable names follow Spring Boot relaxed binding rules.
- [ ] Precedence across files/profiles/OS env/CLI is documented.
- [ ] If List/Map is used, override semantics are documented.
- [ ] Secrets are never committed or logged; controlled injection sources exist.
- [ ] Configuration metadata is provided for IDEs/docs where needed.
- [ ] Deprecated keys have runtime migration, not just metadata.
- [ ] Type, unit, and default changes are evaluated as potential breaking changes.
- [ ] Tests cover missing, invalid, boundary, precedence, and legacy cases.
- [ ] Deployment manifests/Helm/Compose/CI match the new names.
- [ ] Whether changing config files requires a restart/reload is clearly stated.

## 30. Conclusion

**Stable configuration is part of software design, not an afterthought of deployment.** A key must be named, typed, and documented like an API:

~~~text
Canonical key + namespace
            |
            v
Type + unit conversion
            |
            v
Default / required / conditional required
            |
            v
Validation + cross-field invariants
            |
            v
PropertySource precedence + secrets policy
            |
            v
Metadata + examples + tests
            |
            v
Versioning + migration
~~~

Key takeaways:

1. `@ConfigurationProperties` provides a type-safe model.
2. `Duration` and `DataSize` require an explicit unit contract.
3. `@DurationUnit` and `@DataSizeUnit` **do not create default values**.
4. `@DefaultValue` or initializers supply defaults when a key is missing, but defaults do not automatically appear in `Environment`.
5. `@Validated` + Jakarta/custom Validators block invalid business configurations.
6. Canonical kebab-case and standard env var mapping reduce operator mistakes.
7. Changing keys, types, defaults, or units can be a breaking change.
8. Configuration metadata aids discovery and deprecation, and does not implement runtime aliases.
9. Secrets require dedicated delivery, logging, and rotation policies.
10. Contract tests must cover missing, invalid, override, and legacy cases.

### References

- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot — Converting Durations/Data Sizes: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion
- Spring Boot — Configuration Properties Validation: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation
- Spring Boot — Metadata Format: https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html
- Spring Boot — Annotation Processor: https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html
- Spring Boot — Additional Metadata: https://docs.spring.io/spring-boot/specification/configuration-metadata/manual-hints.html
- Spring Framework — Validation: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
