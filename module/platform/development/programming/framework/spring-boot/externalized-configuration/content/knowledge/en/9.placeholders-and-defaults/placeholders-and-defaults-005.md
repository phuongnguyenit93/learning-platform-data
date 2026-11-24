# Distinguishing Missing Keys, Empty Strings, Zero, and False in Spring Boot 3.3

## 1. Why Do These Four States Matter?

When handling externalized configuration in Spring Boot 3.3, an application often needs to distinguish four cases:

1. **The key is not declared** in any effective configuration source.
2. **The key exists with an empty string value** `""`.
3. **The key exists with numeric value zero** `0`.
4. **The key exists with boolean value false** `false`.

They can look similar if a developer checks them with a "looks like no value" expression, yet Spring `Environment`, `${...}` placeholders, `@Value`, and `@ConfigurationProperties` treat them differently. In particular, **`0` and `false` are valid values**, not signals for "unconfigured."

Example in `application.properties`:

```properties
# app.name is omitted: missing key
app.alias=
app.max-retries=0
app.feature-enabled=false
```

Their business meanings might be:

- `app.name`: no name has been decided yet; using a default or rejecting startup is allowed.
- `app.alias`: an empty string was explicitly specified; it might mean "display no alias."
- `app.max-retries=0`: explicitly **do not retry** when an operation fails.
- `app.feature-enabled=false`: explicitly **disable** a feature.

If code applies a truthiness mental model like `if (!value)` from another language, or collapses all of them in Java to "absent," the application can easily overwrite valid configuration decisions.

**Core principle:** treat **property presence**, **raw input string**, and **post-conversion typed value** as three separate layers of information.

## 2. Quick Comparison Table

Suppose a key is provided from `application.properties`, with no higher-precedence source overriding it:

| State | File example | `Environment#getProperty("app.key")` | `getProperty("app.key", "fallback")` | Interpretation |
| --- | --- | --- | --- | --- |
| Missing key | No `app.key` line | `null` | `"fallback"` | No resolvable value found |
| Empty string | `app.key=` | `""` | `""` | Property exists, zero-length String value |
| String `0` | `app.key=0` | `"0"` | `"0"` | Property exists, value represents zero |
| String `false` | `app.key=false` | `"false"` | `"false"` | Property exists, value represents boolean false |

The table above applies to **reading as a String via `Environment`**. When reading with `getProperty(key, Integer.class)`, `getProperty(key, Boolean.class)`, or binding to corresponding Java types, Spring uses **type conversion**. When the value is an empty string and the target type cannot accept an empty string, the result may be `null` or a conversion/binding error depending on the API and target type. Do not assume an empty string automatically converts to `0` or `false`.

`environment.containsProperty("app.key")` checks whether the property **has a resolvable (non-null) value** in the current `PropertySource`s, not whether a line of text appears in some file. Thus, typically:

```text
missing -> containsProperty=false
""      -> containsProperty=true
"0"     -> containsProperty=true
"false" -> containsProperty=true
```

If a source has a key whose value is `null`, the notion of "key exists in a physical source" and "has a resolvable value in Environment" can differ. The section on JSON null below explains the classic case.

## 3. Declarations in .properties and YAML

### 3.1. .properties Files

```properties
# app.missing is not declared

app.empty=
app.zero=0
app.off=false
app.label=0
app.flag-as-text=false
```

In `.properties` files, the part to the right of `=` is read as property text and then converted to Java types as needed. Therefore:

- `app.empty=` is an **empty string**, not a zero value.
- `app.zero=0` has raw input `"0"`; the Binder can convert it to `int`/`Integer`.
- `app.off=false` has raw input `"false"`; the Binder can convert it to `boolean`/`Boolean`.
- `app.label=0` remains **String `"0"`** if the declared Java type is `String`.
- `app.flag-as-text=false` remains **String `"false"`** if the target type is `String`.

A value's meaning cannot be deduced solely from its textual form without **knowing the Java type and business intent**.

### 3.2. Equivalent YAML File

```yaml
# application.yaml
app:
  empty: ""
  zero: 0
  off: false
  label: "0"
  flag-as-text: "false"
```

YAML syntax uses quotes `""` to explicitly represent an **empty string**. When you need to preserve `0` or `false` as text data in YAML, wrap them in quotes to avoid confusing intent with YAML numeric/boolean scalars.

Do not treat the following forms as strictly equivalent:

```yaml
app:
  empty-string: ""
  no-explicit-value:
  explicit-null: null
  false-flag: false
  zero-count: 0
```

`empty-string: ""` expresses an empty String. In YAML, a node with nothing after `:` and the `null` scalar carry **YAML null semantics**; they are not explicit notation for an empty String. How null is flattened and converted also depends on the specific loading path. If an intentional empty string is needed, use `""`; if you need to indicate "property not supplied," it is best **not to declare the key**. Do not rely on YAML `null` as a universal mechanism to erase values from lower-precedence sources.

### 3.3. Whitespace-Only Strings Are Not Empty Strings

`" "` has one space, unlike `""`. Example:

```yaml
app:
  title: " "
```

When using String, decide whether the application should accept, preserve, or treat whitespace-only strings as invalid. Java checks also differ:

```java
String value = " ";
value.isEmpty(); // false
value.isBlank(); // true
```

File loaders and converters may trim or handle certain characters depending on format or converter, so if exact whitespace matters, specify and validate it explicitly. `@NotBlank` is useful when a string must contain non-whitespace characters.

## 4. Observing with `Environment`: Detecting "Missing" vs. "Set"

Spring Framework's `Environment` provides several ways to access properties. An example in Spring Boot:

```java
package com.example.demo;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class ConfigDiagnostics {

    @Bean
    ApplicationRunner inspectProperties(Environment env) {
        return args -> {
            for (String key : Arrays.asList(
                    "app.missing", "app.empty", "app.zero", "app.off")) {

                String value = env.getProperty(key);
                System.out.printf(
                        "%s present=%s value=%s length=%s%n",
                        key,
                        env.containsProperty(key),
                        value == null ? "<null>" : "[" + value + "]",
                        value == null ? "<null>" : value.length()
                );
            }
        };
    }
}
```

With the equivalent YAML or .properties above and no other sources overriding them:

```text
app.missing present=false value=<null> length=<null>
app.empty   present=true  value=[]     length=0
app.zero    present=true  value=[0]    length=1
app.off     present=true  value=[false] length=5
```

**Why print `[ ]` around the value?** If you only call `println(value)`, an empty string looks like a blank line, making it hard to distinguish from missing data. For properties that might contain secrets, do not print values to logs; only inspect non-sensitive keys or log masked status.

### `getProperty(key, defaultValue)` Does Not Replace Every "Falsy" Value

Example:

```java
String a = env.getProperty("app.missing", "fallback"); // fallback
String b = env.getProperty("app.empty", "fallback");   // ""
String c = env.getProperty("app.zero", "fallback");    // "0"
String d = env.getProperty("app.off", "fallback");     // "false"
```

The `defaultValue` parameter is used when **no property value can be resolved**, not when the value is empty, zero, or false.

Similarly, if you read typed values:

```java
Integer maxRetries = env.getProperty("app.zero", Integer.class);
Boolean enabled = env.getProperty("app.off", Boolean.class);
```

This typically produces `maxRetries=0` and `enabled=false`. Both values are valid. For a missing key, the wrapper object may be `null`; if an explicit fallback is needed, use the overload with a default:

```java
Integer retryCount = env.getProperty("app.max-retries",
        Integer.class, 3);
Boolean featureEnabled = env.getProperty("app.feature-enabled",
        Boolean.class, false);
```

The typed overload is still subject to type conversion requirements. If an empty string is declared for a numeric/boolean property, do not treat it as "missing" and default it to 0/false without an explicit application rule.

### `getRequiredProperty` Is a Different Concept

`env.getRequiredProperty("app.name")` is used when a property **must exist and have a resolvable value**. This does not mean "the String must contain characters."

An empty string can still be a **resolved value** of type String. If the business requirement is "must not be blank," check `isBlank()` or use Bean Validation at the `@ConfigurationProperties` layer instead of relying solely on `getRequiredProperty`.

## 5. Placeholder `${key:default}`: When Is the Default Used?

Spring Boot allows placeholder syntax in `application.properties`/YAML values and `@Value`:

```properties
app.display-name=${app.name:Guest}
app.retry-limit=${app.max-retries:3}
app.enabled-by-default=${app.feature-enabled:true}
```

The `:` separates the property name from the default value.

Suppose we check four scenarios for `app.name` alone:

| Effective `app.name` | Value of `${app.name:Guest}` | Interpretation |
| --- | --- | --- |
| Absent | `Guest` | Fallback applies |
| `app.name=` | `""` | Empty string counts as a present value |
| `app.name=0` | `0` | Fallback is not used |
| `app.name=false` | `false` | Fallback is not used |

**Conclusion:** placeholder defaults are not a "substitute if the value is meaningless" operator. They are a fallback triggered by **not finding the property**.

Usage example:

```java
@Component
class DisplayService {

    private final String displayName;

    DisplayService(@Value("${app.name:Guest}") String displayName) {
        this.displayName = displayName;
    }

    String displayName() {
        return displayName;
    }
}
```

If the file says `app.name=`, `displayName` receives an empty string; it does not automatically become `Guest`.

### Distinguishing a Default from an Empty Default

The following two expressions differ:

```properties
app.title=${app.name:Guest}
app.subtitle=${app.name:}
```

When `app.name` is **absent**:

- `app.title` uses `Guest`.
- `app.subtitle` uses an empty string.

When `app.name` **already exists and equals an empty string**, both take the empty string. The condition for triggering the default remains **property not found**, not the content of the default.

### Nested Placeholders

```properties
app.endpoint=${app.remote-url:${app.local-url:http://localhost:8080}}
```

Spring can use `app.remote-url` if resolved; otherwise it checks `app.local-url`; if both are missing, it uses the fixed URL. If `app.remote-url=` (empty), the outer default layer normally is not used because the property exists with an empty String value. This case calls for an application policy: is an empty string allowed to mean "disable endpoint," or should the configuration be rejected?

**Key naming style:** prefer canonical lowercase kebab-case inside placeholders, such as `${app.max-retries:3}`, to match Spring Boot's relaxed binding mechanism.

## 6. `@Value` with Java Types: Do Not Confuse Null, Empty, and Boolean

In code:

```java
@Component
class FeaturePolicy {

    FeaturePolicy(
            @Value("${app.feature-enabled:false}") boolean enabled,
            @Value("${app.max-retries:0}") int maxRetries,
            @Value("${app.label:}") String label) {

        System.out.println(enabled);
        System.out.println(maxRetries);
        System.out.println("[" + label + "]");
    }
}
```

If the properties are **absent**, the annotations supply the specified defaults: `false`, `0`, and `""` before converting to the Java types.

If the properties are present:

```properties
app.feature-enabled=false
app.max-retries=0
app.label=
```

then the three values are still `false`, `0`, and `""`, respectively, yet **they come from declared configuration**, not from fallbacks.

The danger is that two datasets can yield **the same Java value** while carrying different meanings:

- Omitting `app.max-retries` yields `0` in Java due to the annotation default.
- Explicitly declaring `app.max-retries=0` also yields `0` in Java.
- Omitting `app.feature-enabled` yields `false` in Java due to the annotation default.
- Explicitly declaring `app.feature-enabled=false` also yields `false` in Java.

If you need to know whether an operator **intentionally overrode** a setting, you cannot rely solely on the `int`/`boolean` field after binding; you must check property resolvability in `Environment` or use a dedicated state model.

### Avoid Using Empty Strings as Boolean/Int

Error-prone example:

```properties
app.max-retries=
app.feature-enabled=
```

If injected into `int` or `boolean` via `@Value`, an empty string may fail to convert to a valid primitive value. The result can be a conversion/binding exception or null at an intermediate layer; never assume "empty surely means 0/false."

If you want a default, **omit the key completely** so the fallback takes effect, or supply a properly typed value. If a tri-state is needed, use `Integer`/`Boolean` wrappers along with an explicit policy for empty values.

## 7. `@ConfigurationProperties` and Default Values

For multiple properties, Spring Boot recommends typed binding with `@ConfigurationProperties`. This differs from `@Value` in relaxed binding, nested structures, metadata, and constructor/record binding support.

### 7.1. Record with `@DefaultValue`

Spring Boot 3.3 supports `org.springframework.boot.context.properties.bind.DefaultValue` on constructor parameters/record components of immutable configuration.

Example:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @DefaultValue("Guest") String name,
        @DefaultValue("3") int maxRetries,
        @DefaultValue("false") boolean featureEnabled,
        String alias) {
}
```

Enable configuration class scanning:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**When the corresponding keys are missing**, the Binder can use:

```text
name           = "Guest"
maxRetries     = 3
featureEnabled = false
alias          = null
```

**When the file contains:**

```properties
app.name=
app.max-retries=0
app.feature-enabled=false
app.alias=
```

then `@DefaultValue("Guest")` **does not replace the empty string with Guest**, because the `app.name` property was found. `maxRetries=0` and `featureEnabled=false` preserve the declared intent without using their respective defaults; `alias` is an empty String.

This is a point Spring Boot 3.3 explicitly states in the `@DefaultValue` Javadoc: **defaults are only used when the Binder does not find the property; even when the property exists with an empty value, the annotation default is not applied**.

**Limitation:** `@DefaultValue` does not support placeholder resolution for the value declared in the annotation; the annotation value must be constant and is converted to the target type by the conversion service.

### 7.2. JavaBean with Initial Field Values

Another approach is defining defaults on JavaBean fields:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppSettings {

    private String name = "Guest";
    private int maxRetries = 3;
    private boolean featureEnabled = true;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public boolean isFeatureEnabled() {
        return featureEnabled;
    }

    public void setFeatureEnabled(boolean featureEnabled) {
        this.featureEnabled = featureEnabled;
    }
}
```

In this setter-based bean:

- If `app.name` is absent, the field can retain its initial value `Guest`.
- If `app.name=`, the Binder can set it to `""`, replacing `Guest`.
- If `app.max-retries=0`, the field changes from `3` to `0`.
- If `app.feature-enabled=false`, the field changes from `true` to `false`.

An explicit `0`/`false` value can always override initial defaults in a JavaBean. For an empty property whose target type does not permit it, handle/validate explicitly rather than assuming it reverts to the old default.

### 7.3. Primitives and Wrappers

Consider two declarations:

```java
private int retryCount;
private Integer retryLimit;

private boolean enabled;
private Boolean overrideEnabled;
```

For a newly instantiated JavaBean, `int` has Java initial value `0` and `boolean` has `false`, whereas `Integer`/`Boolean` default to `null` when unassigned. Therefore:

- `retryCount==0` **does not prove** `app.retry-count` was configured.
- `enabled==false` **does not prove** `app.enabled` was configured.
- Wrappers can represent **unassigned** via `null`, but you should design the binding/validation semantics clearly rather than making absolute inferences from wrappers alone.
- When a property is required, use validation to enforce valid values; if a flag is purely two-state, a primitive boolean with an explicit default can be a simple design.

For a true tri-state configuration:

```text
null  → unspecified, use inherited policy
false → explicitly disabled
true  → explicitly enabled
```

you can use `Boolean`, **without automatically mapping empty strings to null** unless that policy is explicitly defined. If you also need to distinguish "declared empty," the model needs a separate state or must inspect the property source.

## 8. Should You Check "Presence" or "Value"?

Start from the business question:

| Requirement | What to check |
| --- | --- |
| Need to know if a key has a resolvable value | `Environment.containsProperty(key)` |
| Need to read a string, with fallback when missing | `Environment.getProperty(key, defaultValue)` |
| Need to know if it is an empty string | `value != null && value.isEmpty()` |
| Need to know if it is a whitespace-only string | `value != null && value.isBlank()` |
| Need a real boolean | `getProperty(key, Boolean.class)` or `@ConfigurationProperties` |
| Need to distinguish unconfigured / false / true | `Boolean` and explicit binding rules |
| Need zero to be a valid value | `int`/`Integer` with appropriate validation |
| Need a non-empty, non-blank String | `@NotBlank` or `isBlank()` check |
| Need a number greater than 0 | `@Positive` or `@Min(1)` |
| Need to ensure a key is supplied in appropriate config | Validation, property source/origin inspection, startup checks |

Example of a function classifying state from `Environment`:

```java
static String describe(Environment env, String key) {
    String raw = env.getProperty(key);

    if (raw == null) {
        return "MISSING";
    }
    if (raw.isEmpty()) {
        return "EMPTY";
    }
    if (raw.equalsIgnoreCase("false")) {
        return "BOOLEAN_FALSE_TEXT";
    }
    if (raw.equals("0")) {
        return "ZERO_TEXT";
    }
    return "PRESENT_VALUE";
}
```

This function only classifies **the effective string after Environment resolution**, not a full parser. For example, `"00"` might still convert to zero depending on conversion, yet it will not match the `raw.equals("0")` branch. If numeric semantics are needed, use the conversion service and handle invalid values. If you need to know which higher-precedence source contributed the value, inspect the `PropertySource`/origin.

## 9. PropertySource Precedence: Can Empty Strings, 0, and False Override?

**Yes.** Spring Boot 3.3 uses multiple configuration sources with a clear precedence order. For the same key, the value from the higher-precedence source wins. Values `""`, `"0"`, or `"false"` are still resolvable values and **can override** a normal value in a lower-precedence source.

Example packaged file:

```properties
# classpath:/application.properties
app.name=Catalog
app.max-retries=5
app.feature-enabled=true
```

Launch:

```bash
java -jar myapp.jar \
  --app.name= \
  --app.max-retries=0 \
  --app.feature-enabled=false
```

Under default precedence, command-line properties rank higher than application files. Effective String values:

```text
app.name           = ""
app.max-retries    = "0"
app.feature-enabled = "false"
```

That means:

- `--app.name=` **overrides with an empty string**; it does not fall back to `Catalog`.
- `--app.max-retries=0` **overrides with 0**; it does not fall back to `5`.
- `--app.feature-enabled=false` **overrides with false**; it does not fall back to `true`.

The same can be supplied via JVM system properties:

```bash
java -Dapp.name= -Dapp.max-retries=0 \
  -Dapp.feature-enabled=false -jar myapp.jar
```

And the corresponding environment variables:

```bash
APP_NAME='' APP_MAXRETRIES=0 APP_FEATUREENABLED=false \
  java -jar myapp.jar
```

The example above follows Boot's mapping from canonical property names to environment variables: dots become `_`, `-` are removed, uppercase. If the key is not passed in a higher source, Spring continues looking in lower sources following `PropertySource` order.

### Higher Priority = Empty Differs from "No Higher Priority"

Do not infer: "If a higher source has an empty value, Spring will skip it and read the lower source." For an empty String property, Spring usually treats it as a present value, so it **shadows** any meaningful value in a lower source.

If the application requirement is "treat empty as undeclared," implement that explicitly in the binding model or business layer:

```java
String configured = env.getProperty("app.name");
String effective = (configured == null || configured.isBlank())
        ? "Catalog"
        : configured;
```

This is a **custom business rule**, not automatic behavior of `${app.name:Catalog}`.

## 10. Can JSON Null Be Used to Erase Lower-Source Values?

Spring Boot allows loading JSON configuration from `SPRING_APPLICATION_JSON`, JVM `spring.application.json`, or the corresponding command-line argument:

```bash
SPRING_APPLICATION_JSON='{"app":{"name":null,"maxRetries":0,"enabled":false}}' \
  java -jar myapp.jar
```

An important behavior confirmed by Spring Boot 3.3 documentation: **JSON null cannot be used to override a value from a lower-precedence PropertySource**, because `PropertySourcesPropertyResolver` treats a `null` value as absent.

Suppose the packaged file has:

```properties
app.name=Catalog
```

And higher-precedence JSON contains:

```json
{"app":{"name":null}}
```

The result can still be `app.name=Catalog` from the lower source. This **differs** from:

```json
{"app":{"name":""}}
```

In this case, the empty string is a **real String value** and can shadow `Catalog`.

JSON `0` and `false` elements are also real values; after resolution/conversion they carry the meaning numeric zero and boolean false, not a command to skip the source.

Do not overgeneralize the JSON null mechanism into a uniform rule for every data source, every converter, or every Java API. When the source is YAML, a config tree, or a custom `PropertySource`, check how that source represents and exposes key values to Spring.

## 11. `@ConditionalOnProperty`: Checking False vs. Merely Absent?

A very common pitfall in Spring Boot auto-configuration is thinking `@ConditionalOnProperty` checks for boolean true by default. **Not quite.** Under Spring Boot's semantics, when `havingValue` is not specified, the condition typically matches if the property **exists and is not equal to the string `"false"`**.

Example:

```java
@Configuration
@ConditionalOnProperty(
    prefix = "app",
    name = "feature-enabled"
)
class FeatureConfiguration {
}
```

With the default `matchIfMissing=false`:

| Effective `app.feature-enabled` value | Can default condition match? | Reason |
| --- | --- | --- |
| Absent | No | `matchIfMissing` defaults to false |
| `false` | No | Value equals `"false"` |
| `true` | Yes | Value is present and not `"false"` |
| `0` | **Yes** | String `"0"` is not `"false"` |
| Empty string `""` | **Yes** | Value is present and not `"false"` |
| `custom` | Yes | Value is present and not `"false"` |

Therefore, if you want an **explicit true feature flag**, declare:

```java
@Configuration
@ConditionalOnProperty(
    prefix = "app",
    name = "feature-enabled",
    havingValue = "true",
    matchIfMissing = false
)
class FeatureConfiguration {
}
```

With `havingValue="true"`, the condition only matches values recognized as `"true"` by the annotation's matching rules. `false`, `0`, and `""` do not match; a missing key also does not match.

If you want a feature **enabled by default when the key is missing**, define an explicit policy:

```java
@Configuration
@ConditionalOnProperty(
    prefix = "app",
    name = "feature-enabled",
    havingValue = "true",
    matchIfMissing = true
)
class DefaultOnFeatureConfiguration {
}
```

Now **absent** matches due to `matchIfMissing=true`, while **explicit false** still does not match. `matchIfMissing` does not mean "treat empty or 0 as missing."

Be especially careful with `@ConditionalOnProperty` for collections; this annotation is not guaranteed to match indexed `[0]` keys if only checking the collection prefix.

## 12. Validation to Distinguish Valid from Invalid Values

Setting defaults helps an application start when configuration is missing, but defaults **do not replace validation**. If a property must not be blank or must not be zero, express that explicitly in the model.

Example with Spring Boot 3.3, Jakarta Bean Validation:

```java
package com.example.demo.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record StrictSettings(
        @NotBlank String name,
        @Min(0) int maxRetries,
        @NotNull Boolean enabled) {
}
```

Explanation:

- `@NotBlank`: `name` must be non-null, non-empty, and not whitespace-only.
- `@Min(0)`: `maxRetries=0` is **valid**; negative numbers are invalid. If it must be positive, use `@Min(1)` or `@Positive`.
- `@NotNull Boolean enabled`: when no value exists and the Binder leaves the field null, validation fails; however, `false` is **non-null and valid**.

If the target type must truly be provided, primitive `boolean` cannot distinguish missing from false since both can result in false; `Boolean` with `@NotNull` is better suited when you need to detect an undeclared state.

For `@ConfigurationProperties` validation to work, the project needs a compatible Bean Validation implementation (typically adding `spring-boot-starter-validation` if not already on the classpath) and proper registration via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

### Do Not Use `@NotNull` When You Want to Forbid Empty Strings

`@NotNull String name` only requires non-null. The value `""` is not null, so use `@NotBlank` (or `@NotEmpty` if whitespace-only strings are allowed) when business rules require a display name.

### Do Not Use `@Positive` When 0 Is a Meaningful Decision

For retry counts, `0` often means "do not retry," which is completely valid. Use `@Min(0)` instead of `@Positive` if you want to allow disabling retries by setting 0.

Do not pick annotations by the gut feeling that "zero means unconfigured"; choose based on the field's meaning.

## 13. Three- or Four-State Models

A configuration API sometimes needs to distinguish:

```text
MISSING  = not configured
EMPTY    = intentionally provided empty string
ZERO     = intentionally set to 0 (for numbers)
FALSE    = intentionally disabled (for booleans)
VALUE    = other value
```

If these states all have distinct meanings, represent them explicitly instead of rushing to collapse them into a single primitive.

Example API for reading an effective String:

```java
public enum InputKind {
    MISSING, EMPTY, VALUE
}

public record RawSetting(InputKind kind, String value) {
}

public static RawSetting readStringSetting(Environment env, String key) {
    String value = env.getProperty(key);
    if (value == null) {
        return new RawSetting(InputKind.MISSING, null);
    }
    if (value.isEmpty()) {
        return new RawSetting(InputKind.EMPTY, "");
    }
    return new RawSetting(InputKind.VALUE, value);
}
```

The application can decide:

- `MISSING`: inherit system behavior or use a default.
- `EMPTY`: clear the displayed portion of a label, or reject if disallowed.
- `VALUE`: parse as String, number, boolean, or enum as appropriate.

For booleans:

```java
Boolean override = env.getProperty("app.feature-enabled",
        Boolean.class);

if (override == null) {
    // fallback policy when no typed value exists
} else if (override) {
    // explicitly enabled
} else {
    // explicitly disabled
}
```

This example is convenient for tri-state cases, though it **does not automatically distinguish missing from raw empty** across every conversion path. If recognizing empty is mandatory, inspect the String value (or underlying source) before converting.

Do not overuse `Optional` as a field type in `@ConfigurationProperties`: Spring Boot documentation explicitly notes that `Optional` is not recommended for property binding; for a missing property, the Binder may bind `null` instead of an expected `Optional.empty()`.

## 14. Typical Configuration Mistakes

### Mistake 1 — Using a Placeholder Default Yet Still Receiving an Empty String

```properties
app.name=
app.display-name=${app.name:Guest}
```

**Cause:** `app.name` exists with an empty string, so the placeholder does not pick `Guest`.

**Requirement-based fix:** remove `app.name` if you want the default to take effect, or accept that empty is real data and handle empty in business logic.

### Mistake 2 — Setting Retry Count to 0 Yet Code Replaces It with 3

```java
// WRONG if 0 means intentionally no retries
int retries = configuredRetries == 0 ? 3 : configuredRetries;
```

This fails to distinguish **undeclared** from **explicitly set to 0**. If 0 is valid, apply the default for missing during binding rather than using 0 as a sentinel.

### Mistake 3 — Feature Is False Yet Condition Still Matches Because `0` Was Passed

```properties
app.feature-enabled=0
```

`@ConditionalOnProperty(name="app.feature-enabled")` does not guarantee `0` is treated as boolean false; by default it checks "property is present and not `false`." Write booleans explicitly as `true`/`false` and use `havingValue="true"` if the feature should only enable on true.

### Mistake 4 — Reading Typed Boolean and Assuming Null Means False

```java
Boolean enabled = env.getProperty("app.feature-enabled",
        Boolean.class);
```

A missing key can produce `null`. Do not call `enabled.booleanValue()` without a null check. If the feature defaults to off, use the typed overload with a default or design explicit binding.

### Mistake 5 — Expecting YAML Null to "Erase" the Base File Value

```yaml
app:
  name: null
```

Do not assume a null value overrides a string from another source the same way an empty string does. JSON null is documented by Spring Boot as **unable to override** a lower-precedence property. With YAML or custom loaders, verify their specific null resolution behavior; use `""` if an empty string is genuinely intended.

### Mistake 6 — Using `@NotNull` for String and Letting Empty Names Slip Through

```java
@NotNull
private String displayName;
```

An empty string is still non-null. If the name must have content, use `@NotBlank`.

### Mistake 7 — Reading Configuration via APIs with Different Semantics

One place calls `env.getProperty(key)`; another uses `@Value` with a placeholder default; another uses Binder `@DefaultValue`. They may return the same value in normal cases yet differ on missing/empty/typed conversion. Pick one consistent configuration model for a component, especially when testability and validation matter.

### Mistake 8 — Deleting a Key in a Higher File and Thinking It Was Removed from the Application

If the property still exists in a lower-precedence file or source, removing a line in a higher source can **re-expose** the old value. A key's absence from one file does not prove it is absent from `Environment`.

### Mistake 9 — Primitive Defaults Hiding Missing Configuration

A `boolean enabled` field defaults to false, and `int timeout` defaults to 0. If a zero timeout is invalid or the flag is mandatory, use wrappers and validation; do not rely on Java primitives to prove a value was declared.

### Mistake 10 — Printing the Entire Configuration to Debug Missing/Empty

Dumping the entire `Environment` or exposing an unprotected `/actuator/env` endpoint can leak secrets. Inspect only the necessary keys; if using Actuator, configure exposure and secure the endpoint, respecting masking/sanitization mechanisms.

## 15. Testing Behavior Deliberately

When a feature must have deterministic behavior across all four states, write tests based on **inputs and expected outputs** rather than testing only the "happy path."

Example pure Java function:

```java
public static String chooseDisplayName(String configured) {
    if (configured == null) {
        return "Guest";
    }
    return configured;  // empty is preserved if business logic allows it
}
```

Input cases:

| Input | Result | Meaning |
| --- | --- | --- |
| `null` | `"Guest"` | No value provided |
| `""` | `""` | Empty explicitly provided |
| `"0"` | `"0"` | Zero text is still a value |
| `"false"` | `"false"` | Boolean text is still a value |

If business logic instead requires "empty also uses default," the deliberate implementation is:

```java
public static String chooseDisplayName(String configured) {
    return configured == null || configured.isBlank()
            ? "Guest"
            : configured;
}
```

Both functions are valid, yet they **have different contracts**. What matters is specifying the empty case explicitly rather than letting behavior emerge accidentally from conversion or an under-informed comparison.

In Spring Boot tests, you can pass fixed properties:

```java
@SpringBootTest(properties = {
    "app.max-retries=0",
    "app.feature-enabled=false",
    "app.name="
})
class EmptyZeroFalseConfigTest {
    // Test bound beans within the same test context
}
```

To test the **truly absent key** scenario, the test must ensure no value for that key exists in any other `PropertySource` of the context. Simply omitting a line from `@SpringBootTest(properties = ...)` does not prove the entire `Environment` lacks the key, because application config files or the OS environment may still provide it.

## 16. Workflow When Values Do Not Match Expectations

1. **Identify the canonical key** (e.g., `app.max-retries`) and expected data type: `String`, `int`, `boolean`, `Integer`, or `Boolean`.
2. **Find the effective String value** using `env.getProperty(key)`. Distinguish `null`, `""`, `"0"`, and `"false"`; wrap in brackets or log length for non-sensitive keys.
3. **Check resolvability** with `containsProperty(key)`. Remember this reflects the entire `Environment`, not just one file.
4. **Check PropertySource precedence**: a higher source with empty/0/false can shadow a lower source; if the higher source lacks the key, the lower source may be used.
5. **Identify the consuming API**: `${key:default}`, `@Value`, `getProperty(key, type)`, `@ConfigurationProperties`, or `@ConditionalOnProperty`.
6. **Check type conversion and defaults**: placeholder/`@DefaultValue` defaults apply only on missing semantics; do not treat `0`/`false` as missing.
7. **Apply business validation** for empty, invalid, or required values; use `@NotBlank`, `@Min`, `@NotNull` according to intent.
8. **Document the null/empty policy** in configuration docs so operators know how to disable a feature or omit a value.

## 17. Quick Reference Rules Table

| Question | Answer in typical cases |
| --- | --- |
| Are missing and `""` the same? | **No.** Missing usually resolves to `null`; empty is a zero-length String. |
| Does `${key:default}` use the default when `key=`? | **No**, because an empty String is still a supplied value. |
| Can `0` override a numeric value of 5? | **Yes**, if the source containing `0` has higher precedence. |
| Can `false` override `true`? | **Yes**, when the source has higher precedence. |
| Does `@DefaultValue("3")` beat `key=0`? | **No.** The key already has the value 0. |
| Does `@DefaultValue("Guest")` beat `key=`? | **No**, when the Binder sees an empty property. |
| Does Java's `boolean` default of false prove the property was set to false? | **No.** Primitives have Java language default values. |
| Does `@NotNull String` block `""`? | **No.** Use `@NotBlank` if real content is needed. |
| Does `@ConditionalOnProperty` treat `0` as false by default? | **No.** By default the condition compares strings against `false`. |
| Can JSON `null` shadow a property from a lower source? | **No**, per how `PropertySourcesPropertyResolver` handles JSON null in Spring Boot. |
| How do you distinguish missing/false/true? | Use the `Boolean` wrapper and explicit conversion/validation policies, or inspect sources. |
| How do you accept zero as a configuration decision? | Keep `0`, avoid using zero as a missing sentinel, and pick suitable validation. |

## 18. References

- **Spring Boot 3.3 Reference – Externalized Configuration:** PropertySource order, JSON Application Properties, Property Placeholders, Type-safe Configuration Properties, Binding, `@ConfigurationProperties` vs. `@Value`. https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 API – `@DefaultValue`:** defaults are only used when the property is not found; a property present with an empty string does not activate the annotation default. https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/DefaultValue.html
- **Spring Boot 3.3 API – `@ConditionalOnProperty`:** `havingValue` and `matchIfMissing` semantics. https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- **Spring Framework – Environment Abstraction / PropertyResolver:** `containsProperty`, `getProperty`, default values, and property sources. https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- **Spring Framework – Using `@Value`:** defaults in placeholders and conversion of injected values. https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html
- **Jakarta Bean Validation:** `@NotNull`, `@NotBlank`, `@Min`, and related constraints; used with `@Validated` to validate application configuration.

**Key takeaway:** **MISSING** means "no value can be resolved"; **EMPTY** is a present empty String; **0** and **false** are explicit values. They behave differently when selecting defaults, overriding configuration sources, converting types, enabling/disabling features, and validating configuration. In Spring Boot 3.3, distinguishing them properly requires examining **presence, raw value, target type, default policy, and PropertySource precedence**.