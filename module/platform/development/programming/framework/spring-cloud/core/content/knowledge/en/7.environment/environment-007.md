# Distinguishing Absent, Null, and Empty String Values

> **Chapter:** Environment  
> **Module:** SPRING_CLOUD_CORE

When a Spring Boot application receives configuration from `application.yml`, environment variables, command-line arguments, or Spring Cloud Config, a property can be in several distinct states: **not declared (absent)**, declared with a **null** value, or declared with an **empty string**. These three states are not equivalent. Confusing them can cause the application to use wrong defaults, fail to clear old settings, start with missing data, or send requests to an empty URL.

This lesson analyzes these states across YAML, Spring `Environment`, property sources, placeholders, and `@ConfigurationProperties`. The goal is to express configuration intent clearly, validate required values, and handle overrides when the application runs across multiple environments.

## 1. Three States to Distinguish

Suppose the application has a property `notification.sender`:

| State | Example | Meaning |
| --- | --- | --- |
| **Absent** | Key `notification.sender` not declared | This configuration source does not supply a value |
| **Null** | `sender: null` or `sender:` in YAML | Key is represented as a null value per source syntax |
| **Empty string** | `sender: ""` | Value is a string of length zero |
| **Literal string `null`** | `sender: "null"` | Value is the four characters `n`, `u`, `l`, `l` |
| **Whitespace-only string** | `sender: "   "` | String has characters but no meaningful content in the usual sense |

In Java, these cases are typically seen as follows:

- Absent or null values are usually represented as `null` when read into a reference type, if there is no default value or other configuration source.
- An empty string is represented as `""`; `value != null` yet `value.isEmpty()` is `true`.
- A whitespace-only string is not empty, yet `value.isBlank()` is `true`.
- The literal string `"null"` is an ordinary string value, not Java `null`.

For booleans and numbers, `false` and `0` are also **valid declared values**, not absent or empty. Do not use empty strings to express `false`, `0`, or a default value.

## 2. Representation in YAML

YAML has dedicated syntax for representing null and empty strings. Example:

~~~yaml
notification:
  # Key does not appear in document:
  # sender is not declared.

  sender-null: null
  sender-empty: ""
  sender-literal: "null"
  sender-whitespace: "   "
  sender-with-value: "alerts@example.com"
~~~

Common ways to represent null in YAML:

~~~yaml
first: null
second: ~
third:
~~~

All three are interpreted by the YAML parser as a null value. The line `third:` with no content after the colon also produces a null value, not an empty string.

To represent an empty string, use quotes:

~~~yaml
empty-a: ""
empty-b: ''
~~~

Both ways represent a zero-length string.

If you want a value consisting of the exact four characters `null`, you must enclose it in quotes:

~~~yaml
literal-null: "null"
~~~

### 2.1. Do Not Confuse Comments with Null Declarations

These two examples are different:

~~~yaml
# notification.sender:
~~~

~~~yaml
notification:
  sender:
~~~

The first example is just a comment, so the key does not exist in the YAML data. The second example declares `sender` with a null value.

When reading files, distinguish omitted keys, keys with null values, and keys with empty string values. This is foundational for understanding configuration merging across multiple files or property sources.

## 3. How Spring Environment and PropertySource Handle These States

Spring Boot feeds configuration sources into `Environment`. Each `PropertySource` supplies properties by key name; multiple sources may contain the same key, for instance:

- `application.yml` on the classpath.
- `application-production.yml`.
- External configuration files.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Configuration sources from Spring Cloud Config.
- Properties added in a test context.

When the same key appears in multiple sources, the higher-precedence source is normally checked first. However, a null value has a special meaning: **Spring's standard property resolver does not treat null as a returnable value that overrides lower-precedence values**. Upon encountering null, lookup can continue searching for a non-null value in lower-precedence sources.

For example, `application.yml`:

~~~yaml
service:
  endpoint: "https://api.default.example"
  label: "Order API"
  description: "Default description"
~~~

`application-production.yml`:

~~~yaml
service:
  endpoint: null
  label: ""
  description: "Production API"
~~~

When the `production` profile is active, the lookup results can be understood as:

| Key | Value in profile source | Typical lookup result |
| --- | --- | --- |
| `service.endpoint` | null | Null does not provide an overriding value; a lower-precedence value can be used |
| `service.label` | `""` | Empty string is a present value and can override `"Order API"` |
| `service.description` | `"Production API"` | Profile value overrides the common value |

This is a crucial point when you want to "delete" a default value. Setting a key to null in a configuration source is not a reliable way to remove a value in a lower-precedence source. If you need to represent an explicit state, design appropriate properties and processing rules, such as an `enabled` flag, a clearly defined sentinel value, or a separate configuration with explicit semantics.

**Limitation to remember:** `Environment.getProperty("service.endpoint")` returns a resolvable value, or `null` if no matching value exists. Looking at this result alone is not enough to tell whether the key was completely absent from all files or declared as null by a source. To investigate origins, inspect the property source/origin and the specific input configuration.

### 3.1. Example of Reading via Environment

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ServiceConfigurationReader {

    private final Environment environment;

    public ServiceConfigurationReader(Environment environment) {
        this.environment = environment;
    }

    public void inspect() {
        String endpoint = environment.getProperty("service.endpoint");
        String label = environment.getProperty("service.label");

        if (endpoint == null) {
            // No resolvable endpoint value.
            // Decide on fallback or throw an error.
        }

        if (label == null) {
            // No resolvable label value.
        } else if (label.isEmpty()) {
            // Has an empty string value.
        } else if (label.isBlank()) {
            // Has characters, but only whitespace.
        } else {
            // Has content.
        }
    }
}
~~~

`Environment` is useful when you need to read a dynamic property by name. For a structured configuration group, `@ConfigurationProperties` is usually clearer and easier to test.

## 4. Placeholders and Default Values

Spring supports placeholders in YAML and `@Value`. Common syntax:

~~~yaml
service:
  label: ${SERVICE_LABEL:Default label}
  endpoint: ${SERVICE_ENDPOINT:https://localhost:8443}
~~~

The `${NAME:default}` structure supplies a default value when the placeholder cannot find a matching value. Distinguish:

- Variable/property not provided: the fallback can be used.
- Property source has null: null is not treated as a resolved value; the resolver can continue searching lower-precedence sources or use the fallback if no value is found.
- Property supplied as an empty string: the empty string is a value; the fallback does not automatically replace it.
- Property supplied as the string `"null"`: this is a literal string, not null.

Example:

~~~yaml
service:
  label: ${SERVICE_LABEL:Default label}
~~~

If `SERVICE_LABEL` does not exist, the result is `Default label`. If the environment variable exists with an empty value, the result is an empty string. Therefore, placeholder fallbacks are **not** a mechanism for replacing empty values.

Placeholders can be used directly in `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ServiceLabel {

    private final String label;

    public ServiceLabel(
            @Value("${service.label:Default label}") String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
~~~

If business logic treats an empty string as invalid too, check separately with `isBlank()` or use Bean Validation. Do not expect placeholders to automatically infer business semantics for empty strings.

## 5. Binding into @ConfigurationProperties

For configuration with many properties, `@ConfigurationProperties` groups them into a Java type. Example:

~~~yaml
mail:
  sender: ""
  reply-to: "support@example.com"
  footer: null
  enabled: false
  retry-count: 0
~~~

Configuration type:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        String sender,
        String replyTo,
        String footer,
        Boolean enabled,
        Integer retryCount
) {}
~~~

Assuming the configuration type has been registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, the values reflect distinct states:

| Field | Input value | Expected Java value under normal binding |
| --- | --- | --- |
| `sender` | `""` | Empty string |
| `replyTo` | Address string | Address string |
| `footer` | YAML null | No bindable value; may be null if no other source exists |
| `enabled` | `false` | `Boolean.FALSE` |
| `retryCount` | `0` | `Integer.valueOf(0)` |

Use wrappers such as `Boolean` and `Integer` when you need to distinguish "not configured" from `false` or `0`. If using primitives `boolean` or `int`, Java cannot represent null; primitive defaults can obscure the fact that a property was omitted.

For `String` types, empty strings can be preserved as-is. For other target types such as numbers, booleans, enums, or URIs, an empty string may fail conversion or be handled depending on the converter and version. **Do not use empty strings as a universal convention across all data types.**

### 5.1. Distinguishing Null, Empty, and Blank Strings in Code

~~~java
public final class MailSenderPolicy {

    public boolean hasSender(String sender) {
        return sender != null && !sender.isBlank();
    }

    public String resolveSender(String configured, String fallback) {
        if (configured == null || configured.isBlank()) {
            return fallback;
        }
        return configured;
    }
}
~~~

`isBlank()` checks for an empty string or whitespace-only characters. `isEmpty()` only checks for zero length. Example:

| Java value | `value == null` | `value.isEmpty()` | `value.isBlank()` |
| --- | --- | --- | --- |
| `null` | true | Cannot be called | Cannot be called |
| `""` | false | true | true |
| `"   "` | false | false | true |
| `"mail"` | false | false | false |

Always check for null before calling `isEmpty()` or `isBlank()` to avoid `NullPointerException`.

### 5.2. Validation for Required Configuration

If `mail.sender` must have content, you can use `@NotBlank`:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        @NotBlank String sender,
        String replyTo
) {}
~~~

With the appropriate validation dependency, the application reports a binding/validation error when `sender` is null, an empty string, or whitespace-only.

Different annotations have different meanings:

| Annotation | Condition |
| --- | --- |
| `@NotNull` | Value cannot be null; empty string is still valid |
| `@NotEmpty` | Not null and not empty; whitespace-only string may still be valid |
| `@NotBlank` | Not null and must contain at least one non-whitespace character |
| `@Min(1)` | Numeric value must be greater than or equal to 1 |
| `@Positive` | Numeric value must be greater than 0 |

Validation should reflect business rules. An optional property may allow null; a required text property usually needs `@NotBlank`; a boolean flag may need an explicit value to avoid an indeterminate state.

## 6. Distinguishing Absent/Null/Empty from False, Zero, and Empty Collections

A common mistake is lumping together all values that "look like nothing" into a single state. In reality, data types have their own distinct valid values:

~~~yaml
feature:
  enabled: false
  max-connections: 0
  allowed-origins: []
  metadata: {}
  description: ""
  optional-endpoint: null
~~~

Meanings:

- `false`: explicitly configured that the feature is disabled.
- `0`: configured as zero; whether it is valid depends on business rules.
- `[]`: list declared with zero elements.
- `{}`: map declared with zero entries.
- `""`: string declared with empty content.
- `null`: null value per source format; during Spring resolution, it does not act as a normal overriding value.
- Key omitted: configuration source does not supply that property.

For lists and maps, binding/merging rules across multiple property sources can differ from scalars. Lists in a higher-precedence source usually replace lists in a lower-precedence source; do not assume elements are concatenated. If you need to clear an entire default list, use the appropriate empty collection syntax and write tests confirming your Spring Boot version's binder output.

## 7. Overrides Across Configuration Sources

Spring Boot can read the same key from multiple property sources. For example:

`application.yml`:

~~~yaml
feature:
  banner: "Welcome"
  endpoint: "https://default.example"
~~~

`application-production.yml`:

~~~yaml
feature:
  banner: ""
  endpoint: null
~~~

Environment variable:

~~~text
FEATURE_BANNER=Production
~~~

If the environment variable has higher precedence than configuration files, `feature.banner` can receive `Production`. Without the environment variable, the empty string in the profile file is a present value and can override `Welcome`. Meanwhile, `feature.endpoint: null` does not supply a usable override value; the value from the lower-precedence source can continue to be used.

This leads to three design rules:

1. **Want to use a default:** omit the key in the overriding source or use an intentional placeholder/default.
2. **Want to set an empty string:** use `""` and ensure code accepts empty strings as a valid state.
3. **Want to turn off a feature:** use boolean `false` or a dedicated status property, rather than null or an empty string.

Do not rely on null to "erase" values in a lower-precedence file. If you need to clear a configuration value, design properties with explicit semantics such as `feature.enabled: false`, `feature.endpoint: ""` if empty has a defined meaning, or a mode like `feature.mode: disabled`. For complex values, you may need to change the configuration source or structure rather than trying to express deletion via null.

## 8. Environment Variables and Command-Line Arguments

In deployment environments, an environment variable can be in three practical states:

- Unset.
- Set to an empty string.
- Set to a non-empty string.

PowerShell example:

~~~powershell
Remove-Item Env:FEATURE_LABEL -ErrorAction SilentlyContinue
$env:FEATURE_LABEL = ""
$env:FEATURE_LABEL = "Production"
~~~

These three operations respectively remove the variable from the process environment, set it to an empty string, and set it to a value with content. Inside the Spring Boot process, the provided variable state becomes a property source per Spring Boot's name-mapping rules.

Command-line arguments also distinguish:

~~~bash
java -jar app.jar
java -jar app.jar --feature.label=
java -jar app.jar --feature.label=Production
~~~

- The first command does not supply `feature.label` via the command line.
- The second command supplies the key with an empty value.
- The third command supplies the value `Production`.

When using Docker, Kubernetes, or CI/CD systems, check how the platform represents missing keys versus keys with `""`. Not every UI form displays these two states the same way. For secrets, avoid accidentally setting empty values; required configuration should be validated right at startup.

## 9. Interaction with Spring Cloud Config and Refresh

In a Spring Cloud system, configuration can come from Config Server instead of only local `application.yml`. A Config Server can return property sources for the requested application name, profile, and label.

Client example:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

If Config Server returns a key with an empty value, the empty string can become the effective configuration value and override lower-precedence values per property source order. If the payload contains null, Spring property resolution does not treat null as a normal overriding value. How null and specific property sources are represented can depend on the repository, serialization, and version; verify the actual outcome.

### 9.1. Refresh Does Not Change the Meaning of Null

Spring Cloud Context provides `@RefreshScope` and refresh mechanisms so certain beans can be recreated after the configuration environment is updated. Refresh does not alter the fundamental rules:

- An omitted key may cause the application to use a value from another source or fallback.
- A null value does not automatically erase a lower-precedence value in standard property resolution.
- An empty string is a present value and can be bound into beans.
- Beans must be designed to handle valid null/empty configurations or reject them via validation.

For example, a bean reading a label can distinguish null and empty:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class NotificationLabel {

    private final String label;

    public NotificationLabel(
            @Value("${notification.label:Default}") String label) {
        this.label = label;
    }

    public boolean isVisible() {
        return label != null && !label.isBlank();
    }
}
~~~

If the value is refreshed to an empty string, the new bean still receives the empty string; `isVisible()` returns false. If the key has no resolvable value, the placeholder can supply `Default`. Actual behavior also depends on the configuration source and whether refresh was triggered properly.

Do not treat `@RefreshScope` as an automatic file watcher. There must be an appropriate configuration source, event, or refresh action; also secure refresh endpoints and avoid logging secrets.

## 10. Testing Configuration States

A useful test should verify all three states: omitted property, empty property, and populated property. You can use `ApplicationContextRunner` to test binding in a lightweight context, or `@SpringBootTest` with overridden properties.

Example testing that an empty string is bound:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class BannerPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsEmptyStringAsAnExplicitValue() {
        runner.withPropertyValues("feature.banner=")
                .run(context -> {
                    FeatureProperties properties =
                            context.getBean(FeatureProperties.class);

                    assertThat(properties.banner()).isEmpty();
                });
    }

    @Test
    void leavesMissingStringUnconfigured() {
        runner.run(context -> {
            FeatureProperties properties =
                    context.getBean(FeatureProperties.class);

            assertThat(properties.banner()).isNull();
        });
    }

    @EnableConfigurationProperties(FeatureProperties.class)
    static class TestConfiguration {
    }

    @ConfigurationProperties(prefix = "feature")
    record FeatureProperties(String banner) {
    }
}
~~~

This example demonstrates a simple `String` property with constructor binding. The project needs Spring Boot's test dependency, JUnit 5, and AssertJ. When testing null values in YAML or JSON, add tests using the exact configuration source your application uses; `withPropertyValues` does not simulate all behavior of a YAML parser or Config Server.

### 10.1. Recommended Test Matrix

| Input | Outcome to verify |
| --- | --- |
| Key omitted in all sources | Binder sees missing state; fallback or validation works properly |
| YAML key has null value | Resolver does not use null as an override; check lower-precedence source |
| YAML key is `""` | String binding receives empty; placeholder fallback does not replace empty |
| Key is `"null"` | Value is the literal string `null` |
| Key is `"   "` | String is not empty yet `isBlank()` is true |
| Boolean key is `false` | False value is preserved, not treated as missing |
| Numeric key is `0` | Zero value is preserved; validation decides whether valid |
| List key is `[]` | Binder receives an empty collection per configuration and version in use |
| Higher-precedence source sets empty | Empty overrides populated value in lower source |
| Higher-precedence source sets null | Lower value can continue to be resolved |

Tests should run with profiles and Config Data close to real deployment if the application depends on multiple sources. Do not only check values in unit tests; include at least one smoke test starting the application with representative configuration.

## 11. Common Mistakes

1. **Writing `key:` and thinking it is an empty string.** In YAML, a key without a value is typically null; use `key: ""` if you want an empty string.
2. **Using `"null"` when wanting Java null.** Quotes turn `null` into a literal string.
3. **Expecting null to override a default value.** The standard property resolver skips null as a returnable value; a lower-precedence source may still supply a value.
4. **Thinking placeholder fallbacks handle empty strings too.** Fallbacks are for unresolved properties; an empty string is an already-supplied value.
5. **Using primitives when needing to distinguish missing from false/zero.** Use wrappers or an explicit state representation.
6. **Using `@NotNull` when requiring non-empty text content.** `@NotNull` still accepts `""`; use `@NotBlank` if you need to reject empty and whitespace.
7. **Calling `isBlank()` on a potentially null value.** Check null first or use validation to enforce the condition.
8. **Trying to clear a list with null.** Use an empty collection intentionally and test binding/merge behavior.
9. **Failing to check higher-precedence property sources.** An empty environment variable can override a populated string in a file.
10. **Assuming refresh turns empty into fallback automatically.** Refresh only loads and applies new configuration state; fallback logic is still governed by the resolver or application code.

## 12. Clear Configuration Design Rules

When defining a property, explicitly decide which states are allowed:

| Need | Recommended representation |
| --- | --- |
| Allow using default value | Omit key in overriding source or define clear fallback |
| Allow users to input empty string | Use `""` and handle empty in code |
| Require non-blank content | Use `@NotBlank` or equivalent validation |
| Allow optional value | Use reference types and clearly specify the meaning of null |
| Disable a feature | Use boolean `false` or a meaningful mode property |
| Empty list of elements | Use `[]` and verify merge rules |
| Remove default in lower source | Design explicit remove/disable semantics; do not rely on YAML null |
| Distinguish unconfigured from zero | Use wrappers like `Integer` instead of `int` when needed |

Before implementation, write a short table for every important property: whether it is required, whether empty is allowed, what null means, where defaults come from, which sources may override it, and whether the application fails fast or falls back when invalid.

**Key takeaway:** Absent means the source does not supply the property; null is a null value per source format yet does not act as a normal override in Spring property resolution; an empty string is an actual string value. `false`, `0`, and empty collections are also explicit values. Express intent accurately in YAML/environment variables, validate with `@ConfigurationProperties`, and test both precedence order and refresh behavior.
