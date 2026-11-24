# Reading Values with Environment.getProperty and Specifying a Target Type

In Spring Boot, application configuration can come from `application.yml`, `application.properties`, environment variables, Java system properties, runtime arguments, or imported configuration sources. When you need to **read a configuration value directly at runtime**, Spring provides the `Environment` object with the `getProperty(...)` method.

The basic call `environment.getProperty("app.name")` returns the value as a **`String`** (or `null` if not found). However, Spring also provides overloads that let you **specify a target type**, such as `Integer.class` or `Boolean.class`, to request conversion to the desired Java type. Depending on the Spring Boot environment and active converters, types such as `Duration` and `URI` may also be supported.

This article walks through reading a simple property, choosing a target type, handling missing/invalid values, and deciding when to switch to `@ConfigurationProperties`.

## 1. Where does Environment sit in Spring Boot configuration?

An application typically has multiple configuration sources simultaneously:

~~~text
Command-line arguments
Java system properties
OS environment variables
SPRING_APPLICATION_JSON
Config Data: application.yml, application-prod.yml, config import...
Other registered property sources
                    |
                    v
        Spring Environment
        and its PropertySources
                    |
                    v
       getProperty("app.timeout")
                    |
                    v
           Resolved value
                    |
                    v
     Convert to target type
~~~

The diagram only illustrates **categories of sources**, not the complete precedence order. The effective order depends on Spring Boot's mechanisms and the sources the application has actually registered. For the same key, `Environment` looks up the value according to the precedence order of the property sources.

Example:

~~~yaml
# application.yml
app:
  display-name: "Order Service"
  retry-count: 3
  enabled: true
  request-timeout: 4s
~~~

If deployment does not override these keys, we can read:

~~~java
String name = environment.getProperty("app.display-name");
String retryText = environment.getProperty("app.retry-count");
String enabledText = environment.getProperty("app.enabled");
~~~

Expected values from Java's perspective:

~~~text
name         = "Order Service"
retryText    = "3"
enabledText  = "true"
~~~

Even though in YAML `retry-count` looks like a number and `enabled` looks like a boolean, the `Environment#getProperty` overload without a target type returns a `String` when a value is found.

This is why you need to distinguish **how configuration is represented at the source** from **the type Java code requires**.

## 2. Important overloads of getProperty

`Environment` inherits its property lookup contract from Spring's `PropertyResolver`. Commonly used calls include:

| Call | Return type | Meaning |
| --- | --- | --- |
| `getProperty(String key)` | `String` | Reads a value as a string; may return `null` |
| `getProperty(String key, String defaultValue)` | `String` | Uses default value when no value is found |
| `getProperty(String key, Class<T> targetType)` | `T` | Converts the found value to the target type |
| `getProperty(String key, Class<T> targetType, T defaultValue)` | `T` | Converts type; uses default when lookup yields no value |
| `getRequiredProperty(String key)` | `String` | Requires the property to have a value; throws an error if missing |
| `getRequiredProperty(String key, Class<T> targetType)` | `T` | Requires the property and converts to the specified type |
| `containsProperty(String key)` | `boolean` | Checks whether the key has a value visible to the resolver |

In Java, `Class<T>` is usually passed using a class literal, such as `Integer.class`, `Boolean.class`, `String.class`, or `Duration.class`.

Illustrative example:

~~~java
String name = environment.getProperty("app.display-name");

String nameWithFallback =
    environment.getProperty("app.display-name", "Unnamed App");

Integer attempts =
    environment.getProperty("app.retry-count", Integer.class);

int attemptsWithFallback =
    environment.getProperty("app.retry-count", Integer.class, 3);

Boolean enabled =
    environment.getProperty("app.enabled", Boolean.class);

String requiredName =
    environment.getRequiredProperty("app.display-name");
~~~

**Note:** `Integer` and `Boolean` are wrapper types and can be `null`. Do not automatically unbox them to `int`/`boolean` unless you are sure the property exists or has a valid default.

## 3. Reading String first: simple, but not always enough

The shortest usage:

~~~java
String value = environment.getProperty("app.display-name");
~~~

If the configuration is:

~~~yaml
app:
  display-name: "Inventory Service"
~~~

then `value` is the string `"Inventory Service"`.

When the key does not exist:

~~~java
String unknown = environment.getProperty("app.unknown");
// unknown can be null.
~~~

This case must be handled:

~~~java
String label = environment.getProperty("app.label");
if (label == null) {
    label = "Default label";
}
~~~

Or more concisely:

~~~java
String label =
    environment.getProperty("app.label", "Default label");
~~~

Reading as `String` fits when the value is genuinely a string such as an application name, identifier, label, or endpoint requiring further processing. But if the key represents a retry count, boolean flag, or duration, keeping everything as strings forces the code to convert types manually:

~~~java
String text = environment.getProperty("app.retry-count");
int retryCount = Integer.parseInt(text);
~~~

This snippet has two risks: `text` can be null causing `parseInt` to fail, and you have to manage conversion yourself. When a suitable converter exists, calling `getProperty(key, Integer.class)` directly is usually clearer in intent.

## 4. Specifying the target type with Class<T>

This is the focus of the article. Instead of receiving a `String`, the developer supplies a class literal so Spring converts the value:

~~~java
Integer retryCount =
    environment.getProperty("app.retry-count", Integer.class);

Boolean enabled =
    environment.getProperty("app.enabled", Boolean.class);
~~~

With YAML:

~~~yaml
app:
  retry-count: 5
  enabled: false
~~~

Expected result:

~~~text
retryCount -> Integer with value 5
enabled    -> Boolean.FALSE
~~~

This style aligns the variable name and target type with the meaning of the data. It also avoids having every service parse strings in its own way.

Some common types:

| Configuration meaning | Property example | Suggested target type |
| --- | --- | --- |
| Name or code | `app.name`, `app.code` | `String.class` |
| Maximum count | `worker.max-threads` | `Integer.class` |
| Large retry count | `job.retry-limit` | `Long.class` or `Integer.class` depending on range |
| Enable/disable flag | `feature.enabled` | `Boolean.class` |
| Floating-point ratio | `client.backoff-factor` | `Double.class` or appropriate numeric type |
| Duration | `client.timeout` | `Duration.class` if ConversionService supports it |
| URI | `client.base-uri` | `URI.class` if ConversionService supports it |

There is no rule that every Java type is automatically convertible. `Environment#getProperty` relies on the Spring environment's **conversion service**. Spring Boot typically registers convenient converters for application configuration; a plain `Environment` created in a unit test may have a different set of converters. For complex types or custom formats, an appropriate converter is required.

### Complete example with configuration

~~~yaml
inventory:
  max-items: 120
  enabled: true
  display-code: "0012"
  timeout: 2500ms
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.core.env.Environment;

public final class InventoryReader {

    private final Environment environment;

    public InventoryReader(Environment environment) {
        this.environment = environment;
    }

    public void read() {
        Integer maxItems =
            environment.getProperty(
                "inventory.max-items", Integer.class);

        Boolean enabled =
            environment.getProperty(
                "inventory.enabled", Boolean.class);

        String displayCode =
            environment.getProperty("inventory.display-code");

        Duration timeout =
            environment.getProperty(
                "inventory.timeout", Duration.class);

        // Use values after handling missing/validation checks.
    }
}
~~~

In a Spring Boot application with a duration converter, `2500ms` can be converted to a `Duration` of 2.5 seconds. If your environment does not support the corresponding converter, another conversion approach will be needed.

In particular, `display-code` must be `String` if the string `"0012"` needs to be preserved. If read with `Integer.class`, the result is the number 12 and the leading-zero formatting is lost.

## 5. Default values: getProperty(key, type, default)

Reading a retry count with a default:

~~~java
int retryCount =
    environment.getProperty(
        "batch.retry-count", Integer.class, 3);
~~~

If no property source provides a usable value for `batch.retry-count`, the program receives the default `3`.

Reading a boolean:

~~~java
boolean enabled =
    environment.getProperty(
        "batch.enabled", Boolean.class, false);
~~~

Reading a string:

~~~java
String serviceName =
    environment.getProperty(
        "app.service-name", String.class, "order-service");
~~~

Direct comparison:

~~~java
Integer a =
    environment.getProperty("batch.retry-count", Integer.class);

Integer b =
    environment.getProperty(
        "batch.retry-count", Integer.class, 3);
~~~

If the key is completely absent, `a` can be null while `b` is 3.

**A default value is not a mechanism to swallow conversion errors.** If configuration has:

~~~yaml
batch:
  retry-count: "three-times"
~~~

and Java requests `Integer.class`, the converter can report an error because `"three-times"` is not an integer. Do not expect the overload with `defaultValue` to silently ignore invalid data and return 3. Defaults only apply when the lookup finds no value; mistyped data must be detected and fixed.

### Choosing defaults responsibly

A default value should be:

- Safe in the application's context.
- Clear in business/operational meaning.
- Usable without guessing units or intent.
- Unable to mask missing secrets or required endpoints.

For example, a default of 3 for `batch.retry-count` can be reasonable if agreed upon. Conversely, `payment.api-key` should not have a dummy default that lets production start up and fail later or send requests to the wrong place.

## 6. Required properties: getRequiredProperty

If a key must be present, use:

~~~java
String endpoint =
    environment.getRequiredProperty("gateway.base-url");
~~~

When no value is found for the key, `getRequiredProperty` throws an error, typically `IllegalStateException`. This fits parameters that have no valid default.

There is also an overload taking a target type:

~~~java
Integer maxConnections =
    environment.getRequiredProperty(
        "gateway.max-connections", Integer.class);
~~~

Two kinds of errors should be separated:

1. **No value present:** `getRequiredProperty` reports that the required property was not found.
2. **Present but malformed/unconvertible:** the converter throws an error during type conversion.

Requiring **a value to exist** does not mean the value is **valid for business logic**. For example:

~~~yaml
gateway:
  base-url: ""
  max-connections: -5
~~~

An empty string can still be treated as a present value for a `String` query. A negative number can be converted into an `Integer` yet fail to meet the minimum connection count requirement.

Additional checks are needed:

~~~java
String baseUrl =
    environment.getRequiredProperty("gateway.base-url");

if (baseUrl.isBlank()) {
    throw new IllegalStateException(
        "gateway.base-url must not be blank");
}

int maxConnections =
    environment.getRequiredProperty(
        "gateway.max-connections", Integer.class);

if (maxConnections <= 0) {
    throw new IllegalStateException(
        "gateway.max-connections must be positive");
}
~~~

When there are many required properties or interrelated constraints, a `@ConfigurationProperties` model combined with validation is usually easier to maintain than repeated `if` blocks.

## 7. Missing property, null, empty string, and invalid value

These situations are distinct:

| Situation | Example | What to handle |
| --- | --- | --- |
| Key does not exist | No `app.name` in any source | `getProperty` typically returns null or default |
| Key has an empty value | `app.name: ""` | For `String`, may receive empty string; needs validation if invalid |
| Key has JSON null from `SPRING_APPLICATION_JSON` | `{"app":{"name":null}}` | Null does not mask values from lower-precedence property sources |
| Key has a value of the wrong type | `app.retry-count: "many"` | Conversion may fail; this is not a missing key |
| Key has the right type but violates a constraint | `app.retry-count: -2` | Requires domain/config validation checks |

Example:

~~~java
String name =
    environment.getProperty("app.name", "default");

Integer retryCount =
    environment.getProperty(
        "app.retry-count", Integer.class, 3);
~~~

If `app.name` is absent, `name` uses `"default"`. However, if `app.name` is an empty string, do not assume `"default"` is always used; an empty string can count as a present value.

An important example in Spring Boot:

~~~yaml
# application.yml
app:
  mode: "normal"
~~~

~~~json
{
  "app": {
    "mode": null
  }
}
~~~

If the JSON is supplied via `SPRING_APPLICATION_JSON`, `null` is not a command to erase `"normal"`; the property resolver can continue looking in `application.yml`. Therefore, `getProperty("app.mode")` can still return `"normal"`. To turn off a feature, use a meaningful flag such as `app.feature.enabled=false` instead of relying on null to mask a property.

## 8. Be careful with wrappers and unboxing

The typed overload returns a value of type `T`, and if the property is not found, `T` can be null:

~~~java
Integer count =
    environment.getProperty("workers.count", Integer.class);
~~~

The following carries a risk:

~~~java
int count =
    environment.getProperty("workers.count", Integer.class);
~~~

If the property is absent, Java attempts to unbox `null` to `int` and throws a `NullPointerException`. This error originates in the calling code, not necessarily in Spring.

Choose one of three approaches:

**With an explicit default:**

~~~java
int count =
    environment.getProperty("workers.count", Integer.class, 4);
~~~

**Required:**

~~~java
int count =
    environment.getRequiredProperty(
        "workers.count", Integer.class);
~~~

**Allowed to be missing:**

~~~java
Integer count =
    environment.getProperty("workers.count", Integer.class);

if (count != null) {
    // Use count when configured.
}
~~~

For booleans, avoid interpreting `null` as `false` when you actually need to distinguish the "not configured" state:

~~~java
Boolean flag =
    environment.getProperty("feature.enabled", Boolean.class);

if (Boolean.TRUE.equals(flag)) {
    // Execute only when the property is true.
}
~~~

If your model only has two states, using an explicit boolean default is easier to read.

## 9. Reading Duration, URI, and non-String types

Spring Boot supports binding more value types than just numbers and booleans. However, conversion capabilities depend on the `ConversionService` configured on `Environment`. In a standard Spring Boot application, typed reads like this are often useful:

~~~yaml
integration:
  base-uri: "https://gateway.example.invalid/api"
  timeout: 3s
  max-connections: 20
~~~

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.core.env.Environment;

URI uri =
    environment.getProperty(
        "integration.base-uri", URI.class);

Duration timeout =
    environment.getProperty(
        "integration.timeout", Duration.class);

Integer limit =
    environment.getProperty(
        "integration.max-connections", Integer.class);
~~~

Cases to check:

- A syntactically valid `URI` does not guarantee the endpoint is reachable or uses an allowed protocol.
- `Duration` should have explicit units whenever possible; bare values like `30` may be interpreted according to conversion/target-type conventions.
- `Integer` converts negative numbers, yet the application may require a positive number.
- Complex types, enums with custom rules, collections, or nested objects should not be assumed to bind everything automatically through a single `getProperty` call.

If a format is not supported by the converter, Spring may throw a conversion error. In that case, check the target type, converter, and property representation. Do not work around it by adding `String.valueOf(...)` or swallowing generic exceptions.

### Enums and fixed sets of choices

Mode configuration example:

~~~yaml
export:
  mode: "BATCH"
~~~

Java type:

~~~java
enum ExportMode {
    BATCH,
    STREAMING
}
~~~

With suitable conversion, you can request:

~~~java
ExportMode mode =
    environment.getProperty(
        "export.mode", ExportMode.class, ExportMode.BATCH);
~~~

However, an enum only accepts values that the converter can map. Keep spelling consistent and test against the Spring Boot version in use, especially if values contain hyphens, spaces, or aliases.

## 10. Reading configuration from Environment in a Spring component

A Java configuration or component can inject `Environment` via constructor. Example of a service with just a few parameters:

~~~java
package example.inventory;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class InventoryLimitService {

    private final int maxItems;
    private final boolean enabled;

    public InventoryLimitService(Environment environment) {
        this.maxItems = environment.getProperty(
            "inventory.max-items", Integer.class, 100);

        this.enabled = environment.getProperty(
            "inventory.enabled", Boolean.class, true);
    }

    public boolean mayAccept(int currentItems) {
        return enabled && currentItems < maxItems;
    }
}
~~~

File `application.yml`:

~~~yaml
inventory:
  enabled: true
  max-items: 120
~~~

When the bean is initialized, the fields receive converted values from `Environment`. This is a small example to illustrate `getProperty`; for a large configuration group, it is usually better to gather properties into a strongly typed object instead of letting every service know the key names directly.

**Lifecycle note:** The fields `maxItems` and `enabled` in the example are assigned when the constructor runs. If the YAML file or deployment environment variables change later, the bean does not automatically update its fields. Spring Boot by default does not watch all configuration files and update all beans automatically; dynamic refresh requirements need an explicit design.

## 11. How do Environment, @Value, and @ConfigurationProperties differ?

All three mechanisms relate to externalized configuration, but they fit different purposes:

| Mechanism | Typical purpose | Limitations/considerations |
| --- | --- | --- |
| `Environment#getProperty` | Dynamic lookup of a key, specifying type/default directly in code | Easy to scatter key literals and validation across many places |
| `@Value` | Inject a property/placeholder expression into a field or constructor | Less convenient when many properties need grouping |
| `@ConfigurationProperties` | Bind a group of properties into a structured, typed, validatable object | Requires registering the configuration class and organizing groups clearly |

`@Value` example:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class HealthBanner {

    private final String label;

    HealthBanner(
        @Value("${app.banner.label:Ready}") String label
    ) {
        this.label = label;
    }
}
~~~

In the expression `${app.banner.label:Ready}`, `Ready` is the placeholder's fallback, not an independent property source.

`@ConfigurationProperties` example:

~~~java
package example.inventory;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory")
public record InventoryProperties(
        boolean enabled,
        int maxItems,
        Duration timeout
) {}
~~~

Register via `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(InventoryProperties.class)` in an appropriate configuration class.

~~~java
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final InventoryProperties properties;

    InventoryService(InventoryProperties properties) {
        this.properties = properties;
    }

    boolean isEnabled() {
        return properties.enabled();
    }
}
~~~

If the application has many related properties, `@ConfigurationProperties` helps centralize types, sensible defaults, constraints, and documentation. Spring Boot Binder also supports **relaxed binding**, nested objects, and collections better than calling `getProperty` manually for each key.

A practical rule: use `Environment#getProperty` when you genuinely need to **look up one or a few keys** or need dynamic handling for a known key; use `@ConfigurationProperties` to represent the **long-term configuration contract** of a component.

## 12. Why shouldn't you use getProperty to bind an entire nested object?

Suppose YAML has:

~~~yaml
gateway:
  enabled: true
  endpoints:
    - "https://one.example.invalid"
    - "https://two.example.invalid"
  retry:
    attempts: 3
    delay: 2s
~~~

Calling:

~~~java
String endpoints =
    environment.getProperty("gateway.endpoints");
~~~

is not a reliable contract for retrieving an entire YAML sequence. After being loaded by Spring Boot, collections are typically represented via indexed properties and corresponding binding rules. Code relying on a comma-separated string may not match the source structure.

For nested/list configuration, use the Binder via `@ConfigurationProperties`:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        boolean enabled,
        List<String> endpoints,
        Retry retry
) {
    public record Retry(int attempts, Duration delay) {}
}
~~~

This accurately reflects the data structure and creates a valid checkpoint. `Environment#getProperty` is not a replacement API for all capabilities of the Spring Boot Binder.

In addition, Spring Boot supports certain property name normalization rules in configuration binding, but you should not assume all camelCase, underscore, and hyphen spellings are equivalent across every `PropertySource` when looking up keys with `Environment`.

## 13. Property names and OS environment variables

Suppose you want to configure:

~~~yaml
app:
  order:
    max-items: 40
~~~

From Java code, you should consistently use dot/kebab-case key names:

~~~java
Integer limit =
    environment.getProperty(
        "app.order.max-items", Integer.class);
~~~

When deploying via environment variables, uppercase and underscores are typically used following Spring Boot conventions, such as `APP_ORDER_MAXITEMS` for the canonical property `app.order.max-items` in relaxed binding. Some system property sources have their own equivalent-name lookup mechanisms, but you should not rely on name guessing for every case.

Things to remember:

- `getProperty("app.order.max-items")` is a query for a key name recognized by the resolver.
- `@ConfigurationProperties(prefix = "app.order")` uses binding rules that are more convenient for Java structures.
- Environment variables have different syntax and normalization rules than YAML; choose names following Spring Boot conventions and verify on the actual runtime.
- Avoid creating multiple environment variables with slightly different punctuation at the same time to "bet" on which one gets picked up.

If the value is not what you expect, check **which source is winning**, whether the key name is right, and whether the `targetType` is appropriate.

## 14. Spring Environment is not System.getenv

These two approaches are different:

~~~java
String direct =
    System.getenv("APP_ORDER_MAXITEMS");

Integer resolved =
    environment.getProperty(
        "app.order.max-items", Integer.class);
~~~

`System.getenv` only reads the process's environment variables by the requested name. It does not combine values from `application.yml`, system properties, command-line arguments, config imports, or other Spring-registered sources.

`Environment` looks across Spring's set of `PropertySource`s, evaluates precedence order, and can convert types for the application.

Advantages of `Environment` in Spring Boot:

1. The same Java code can receive values from many different sources.
2. Deployment can override properties without modifying program logic.
3. Fallbacks or target types can be declared right at the read site.
4. Tests can supply properties via Spring's mechanisms without altering the machine's real environment variables.

However, do not inject `Environment` into every class merely for convenience. If properties are a stable dependency of a service, injecting a structured `@ConfigurationProperties` object usually reduces coupling to key names.

## 15. Checking precedence order when getProperty returns an unexpected value

Example:

~~~yaml
# application.yml
app:
  retry-count: 3
~~~

~~~yaml
# application-prod.yml
app:
  retry-count: 5
~~~

And deployment passes the argument:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.retry-count=7
~~~

With Spring Boot's default source precedence configuration, command-line arguments can win over both the base file and the profile file; `environment.getProperty("app.retry-count", Integer.class)` returns `7`.

This behavior is not caused by `Integer.class`, but by **property resolution** prior to conversion.

When the value differs from expectations:

- Check active profiles and which config files are being loaded.
- Check command-line arguments, system properties, environment variables, and imported sources.
- Look for duplicate keys; remember that a higher-precedence source can override a lower one.
- Check key spelling and naming conventions.
- Distinguish a value that is present with the wrong type from a value that was not found.
- Verify whether the application was restarted or has a dedicated refresh mechanism after the latest config change.

If you need to read active profiles, `Environment` also provides `getActiveProfiles()` and `getDefaultProfiles()`. They reflect profile state already processed by the environment, which is better than trying to guess the active profile from a single property string.

~~~java
import java.util.Arrays;

String[] activeProfiles = environment.getActiveProfiles();
System.out.println(Arrays.toString(activeProfiles));
~~~

In production, log only enough information for diagnostics; do not print secrets or the entire configuration to stdout.

## 16. Testing getProperty and type conversion

A small unit test can use `MockEnvironment` from Spring Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class PropertyReadTest {

    @Test
    void readsTypedProperties() {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("batch.retry-count", "4")
            .withProperty("batch.enabled", "false");

        assertEquals(
            Integer.valueOf(4),
            environment.getProperty(
                "batch.retry-count", Integer.class));

        assertEquals(
            Boolean.FALSE,
            environment.getProperty(
                "batch.enabled", Boolean.class));

        assertNull(
            environment.getProperty(
                "batch.unknown", Integer.class));

        assertEquals(
            Integer.valueOf(2),
            environment.getProperty(
                "batch.unknown", Integer.class, 2));
    }
}
~~~

This test demonstrates the purpose of the overloads: when the key exists, convert to the corresponding type; when missing, receive null or the default.

For types relying on Spring Boot conversions such as `Duration`, test inside a Spring Boot context configured with the appropriate converters. A simple `MockEnvironment` does not necessarily have the same conversion service as a Spring Boot application.

Example test inside a Spring Boot application:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
    "inventory.max-items=25",
    "inventory.enabled=false"
})
class InventoryEnvironmentTest {

    @Autowired
    private Environment environment;

    @Test
    void readsValuesFromTestPropertySource() {
        assertEquals(
            Integer.valueOf(25),
            environment.getProperty(
                "inventory.max-items", Integer.class));

        assertEquals(
            Boolean.FALSE,
            environment.getProperty(
                "inventory.enabled", Boolean.class));
    }
}
~~~

Here `@SpringBootTest` assumes the project has a valid Spring Boot application context. Test properties are supplied directly into the context, helping verify code that reads properties by target type.

You can add cases for **wrong type** or **missing required property** if those are critical parts of the configuration contract. There is no need to add tests just to prove all framework overloads work; test the rules your application actually depends on.

## 17. Error handling: missing, conversion, and validation

Suppose the application needs:

~~~yaml
jobs:
  max-attempts: 5
~~~

Several distinct errors can occur:

**Missing key:**

~~~java
Integer attempts =
    environment.getProperty("jobs.max-attempts", Integer.class);
// Can be null.
~~~

**Malformed key value:**

~~~yaml
jobs:
  max-attempts: "many"
~~~

~~~java
Integer attempts =
    environment.getProperty("jobs.max-attempts", Integer.class);
// Can throw a conversion error.
~~~

**Correct type but invalid value:**

~~~yaml
jobs:
  max-attempts: -10
~~~

~~~java
Integer attempts =
    environment.getProperty("jobs.max-attempts", Integer.class);

if (attempts != null && attempts < 0) {
    throw new IllegalArgumentException(
        "jobs.max-attempts must be non-negative");
}
~~~

Do not lump all three cases into `catch (Exception e) { return 3; }`. That approach can hide deployment errors and cause the application to run with unintended parameters.

A clear handling strategy:

| Issue | Solution |
| --- | --- |
| Property is genuinely optional | Use `getProperty` and handle null or use a sensible default |
| Property is required | Use `getRequiredProperty` and/or validation |
| Value has wrong type | Fix the config source or converter; do not silently substitute a default |
| Value has right type but violates constraints | Check/validate explicitly in the configuration layer |
| Many properties share a prefix | Use `@ConfigurationProperties` and centralized validation |
| Value comes from an unexpected source | Check precedence order and active profiles/sources |

An important boundary: **conversion** does not automatically prove **business validity**. Zero, negative numbers, syntactically valid URIs, or boolean `false` can all be converted successfully yet still violate a component's requirements.

## 18. Common usage mistakes

### 18.1. Thinking getProperty always returns the YAML type

~~~yaml
server:
  port: 8080
~~~

~~~java
String port = environment.getProperty("server.port");
~~~

`port` here is a `String`. To get a number, call:

~~~java
Integer port =
    environment.getProperty("server.port", Integer.class);
~~~

### 18.2. Querying without a default and unboxing directly

~~~java
int maxAttempts =
    environment.getProperty("job.max-attempts", Integer.class);
~~~

If the key is missing, a `NullPointerException` can occur during unboxing. Use an appropriate default or required property call.

### 18.3. Believing a default rescues a mistyped value

~~~yaml
job:
  max-attempts: "unlimited"
~~~

~~~java
int maxAttempts =
    environment.getProperty(
        "job.max-attempts", Integer.class, 3);
~~~

Default `3` is not designed to accept the string `"unlimited"` as a valid number. If you want to support `"unlimited"`, design a configuration type that represents that state—such as an enum, `Optional`, or dedicated rule—instead of forcing it into `int`.

### 18.4. Using getProperty instead of validation

~~~java
String endpoint =
    environment.getRequiredProperty("payment.endpoint");
~~~

Having an endpoint does not mean the endpoint is safe or authorized. You need to validate the URI, scheme, business/config constraints, and the component's security policy.

### 18.5. Using Environment as a per-request data store

`Environment` represents the application's externalized configuration, not a place to store order state, the current user, or transaction results. Business data should flow through requests/commands, services, and proper persistence.

### 18.6. Reading System.getenv directly because it feels "simpler"

Once an application uses Spring Boot, `System.getenv("...")` can bypass other sources and make tests harder to configure. Use `Environment` or `@ConfigurationProperties` if the value is part of the application's configuration contract.

### 18.7. Changing configuration and expecting injected fields to update automatically

A bean that reads a value in its constructor keeps that value until it is updated explicitly. There is no guarantee that all property sources update dynamically or that all beans are recreated when you edit YAML. Refresh design is a separate requirement.

### 18.8. Reading secrets to log them for verification

~~~java
String token =
    environment.getProperty("payment.api-token");
~~~

Reading a token can be valid for an authorized client, but do not print its value to logs, pass it into exception messages, or expose the entire `Environment` through a public endpoint. When debugging, only check the presence/safe status of configuration without revealing sensitive data.

## 19. Practical example: an HTTP client needing three properties

Suppose an adapter calling a logistics system has:

~~~yaml
logistics:
  client:
    base-url: "https://logistics.example.invalid/api"
    connect-timeout: 2s
    max-attempts: 3
    enabled: true
~~~

A small factory can read the configuration like this:

~~~java
package example.logistics;

import java.net.URI;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class LogisticsClientConfiguration {

    @Bean
    LogisticsClient logisticsClient(Environment environment) {
        String urlText = environment.getRequiredProperty(
            "logistics.client.base-url");

        URI url = URI.create(urlText);

        Duration timeout = environment.getProperty(
            "logistics.client.connect-timeout",
            Duration.class,
            Duration.ofSeconds(2));

        int maxAttempts = environment.getProperty(
            "logistics.client.max-attempts",
            Integer.class,
            3);

        boolean enabled = environment.getProperty(
            "logistics.client.enabled",
            Boolean.class,
            false);

        if (urlText.isBlank()
                || timeout.isZero()
                || timeout.isNegative()
                || maxAttempts < 1) {
            throw new IllegalStateException(
                "Invalid logistics client configuration");
        }

        return new LogisticsClient(
            url, timeout, maxAttempts, enabled);
    }
}
~~~

`LogisticsClient` is an illustrative class with a constructor taking the corresponding values. The snippet shows:

1. `base-url` must be present; the value is read as a string before converting to `URI`.
2. `connect-timeout` is requested as `Duration` and defaults to 2 seconds.
3. `max-attempts` is requested as `Integer` and defaults to 3.
4. `enabled` is requested as `Boolean` and defaults to `false`.
5. Constraints such as a positive timeout and at least 1 attempt still require checking.

In a larger project, these three or four properties should be moved into a `LogisticsClientProperties` class using `@ConfigurationProperties` so services and factories do not repeat key strings. The example above aims to illustrate using `Environment#getProperty` and `getRequiredProperty` with target types.

## 20. When should you still use Environment directly?

Reasonable cases:

- A framework/infrastructure component needs to look up a key during initialization.
- A small adapter has only one or two properties and needs little validation.
- An internal utility wants to observe the **effective value** of a non-sensitive key.
- Logic needs to choose among known keys rather than binding an entire configuration object.
- A test needs to confirm property source precedence and conversion to a requested type.

Cases where `@ConfigurationProperties` should be used:

- A prefix has multiple related fields.
- There are nested objects, lists, maps, or complex configuration structures.
- Centralized validation and clear startup error messages are needed.
- Multiple beans share a configuration contract.
- You want to reduce coupling to scattered key names in source code.

Using `Environment` is not wrong; the good choice is the one that expresses **the configuration's meaning** and helps the development team understand each value's default, source, type, and constraints.

## 21. Self-practice with four property types

Given YAML:

~~~yaml
demo:
  application-name: "Receipt Service"
  max-users: 50
  enabled: false
  customer-code: "0019"
~~~

Read using both string and typed forms:

~~~java
String name =
    environment.getProperty("demo.application-name");

Integer maxUsers =
    environment.getProperty("demo.max-users", Integer.class);

Boolean enabled =
    environment.getProperty("demo.enabled", Boolean.class);

String code =
    environment.getProperty("demo.customer-code");

Integer unknownWithDefault =
    environment.getProperty("demo.unknown", Integer.class, 10);
~~~

Expected values:

| Java variable | Value |
| --- | --- |
| `name` | `"Receipt Service"` |
| `maxUsers` | `Integer(50)` |
| `enabled` | `Boolean.FALSE` |
| `code` | `"0019"`, preserving leading zeros |
| `unknownWithDefault` | `Integer(10)` |

Next, try changing `demo.max-users` to `"fifty"`. While Java still requests `Integer.class`, observe the conversion error. Try removing the key: `getProperty(key, Integer.class)` may return null, whereas the overload with a default may return the default value. Try `getRequiredProperty(key, Integer.class)` to distinguish a missing-key error from a wrong-type value error.

## 22. Key takeaways

`Environment#getProperty` lets you read a property from the configuration sources Spring has combined. Beyond `String getProperty(key)`, you can pass **`Class<T>`** to request a target type, or supply a **default value** when the key is not found. For required properties, use `getRequiredProperty`, while keeping in mind that this method does not replace business validation.

Three easy rules to apply:

1. **When you want a number, boolean, or specialized type, specify the target type explicitly**, rather than reading a string and parsing manually in multiple places.
2. **Missing values, empty values, and unconvertible values are different situations.** Defaults handle missing keys, converters handle types, and validation handles constraints.
3. **For structured configuration or multiple related keys, prefer `@ConfigurationProperties`.** `Environment#getProperty` fits deliberate per-property lookups.

When reading a line of code like `environment.getProperty("app.retry-count", Integer.class, 3)`, understand it completely: **look up the key following configuration source precedence, convert the found value to Integer, and use 3 only when no suitable value can be looked up**.