# Type Conversion and Default Values When Using @Value

## 1. Why is reading configuration more than just fetching a string?

In Spring Boot, configuration values can originate from `application.yml`, `application.properties`, environment variables, or command-line arguments. These sources provide named properties such as `payment.retry-count`, `payment.enabled`, or `payment.timeout`. However, Java code typically needs **concrete data types**, not just text.

For example, a payment application needs:

- Retry count: type `int` to count attempts.
- Enable/disable state: type `boolean` to make branching decisions.
- Timeout: type `Duration` to pass to an HTTP client.
- Mode name: possibly an `enum` type instead of an arbitrary string.

If every bean calls `Integer.parseInt(...)` and handles missing values on its own, conversion logic gets duplicated in many places. Spring supports the `@Value` annotation to **resolve a configuration value and supply it to an injection point**, while converting it to the Java type of the receiving field, constructor parameter, or method.

Example:

```java
@Value("${payment.retry-count:3}")
private int retryCount;
```

When the bean is created, Spring processes the placeholder `${payment.retry-count:3}`, looks up key `payment.retry-count` in the configuration system, uses `3` if not found, and converts the resulting value to `int`.

Note: `3` inside the annotation string is the **textual representation of the default value**. It becomes an integer through Spring's type conversion mechanism. Those are two separate steps.

```text
Configuration sources (YAML / env / CLI / ...)
                  |
                  v
           Spring Environment
                  |
                  v
     Resolve placeholder ${key:default}
                  |
                  v
      Select effective string/value
                  |
                  v
      ConversionService / type conversion
                  |
                  v
    int / boolean / Duration / enum / ...
                  |
                  v
       Bean receives converted value
```

This article focuses on two questions: **How does Spring convert configuration values to Java types?** And **what happens when a key does not exist or a value is invalid?**

## 2. @Value syntax and the role of placeholders

`@Value` can be placed on a field, constructor parameter, or Spring-processed method. In modern applications, prefer **constructor injection** because dependencies are clearly declared at instantiation time and can be stored in `final` fields.

Common syntax:

```java
@Value("${ten.thuoc.tinh}")
```

Syntax with default:

```java
@Value("${ten.thuoc.tinh:gia-tri-mac-dinh}")
```

Where:

1. `ten.thuoc.tinh` is the key to look up.
2. The colon `:` inside the placeholder separates the key from the default value.
3. The default portion is used only when the resolver **cannot find** the property under the active mechanism.
4. The result is converted to the target Java type when Spring creates the bean.

For example, file `src/main/resources/application.yml`:

```yaml
payment:
  enabled: true
  retry-count: 5
  timeout: 4s
  label: Checkout
```

With class:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PaymentSettings {
    private final boolean enabled;
    private final int retryCount;
    private final String label;

    public PaymentSettings(
            @Value("${payment.enabled:false}") boolean enabled,
            @Value("${payment.retry-count:3}") int retryCount,
            @Value("${payment.label:Payment}") String label) {
        this.enabled = enabled;
        this.retryCount = retryCount;
        this.label = label;
    }

    public boolean enabled() {
        return enabled;
    }

    public int retryCount() {
        return retryCount;
    }

    public String label() {
        return label;
    }
}
```

When the properties in YAML are found and no higher-precedence source overrides them:

```text
enabled    = true
retryCount = 5
label      = Checkout
```

If `payment.retry-count` is removed from all sources, the constructor receives `3`. If `payment.enabled` is removed, the constructor receives `false`. If `payment.label` is removed, the constructor receives the string `Payment`. No Java class edits are needed.

**Point to remember:** `@Value` declares a value to inject into a Spring-managed bean. Instantiating an object with `new PaymentSettings(...)` in plain Java code does not cause Spring to process the annotations automatically.

## 3. Processing order: lookup first, type conversion second

You can observe the same property from two angles.

```yaml
inventory:
  max-items: 12
```

Reading through `Environment`:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class InventoryReader {

    private final Environment environment;

    public InventoryReader(Environment environment) {
        this.environment = environment;
    }

    public String asText() {
        return environment.getProperty("inventory.max-items");
    }

    public Integer asNumber() {
        return environment.getProperty(
                "inventory.max-items", Integer.class);
    }
}
```

`getProperty(key)` returns a `String` per the method signature. The version taking `Integer.class` requests conversion to the target type. With `@Value`, the target type is normally inferred from the field or constructor parameter.

```java
public InventoryService(
        @Value("${inventory.max-items:10}") int maxItems) {
    this.maxItems = maxItems;
}
```

The default value `10` is supplied **before the conversion step**. If the key is missing, Spring takes the text `"10"` and converts it to `int`. If the key has the value `"12"`, Spring converts `"12"` to `12`.

Important distinction:

| Condition | Resolution step | Conversion step |
| --- | --- | --- |
| Key has `12` | Selects `12` | Converts to `int` as 12 |
| Key absent, fallback `10` | Selects `10` | Converts to `int` as 10 |
| Key has `abc` | Selects `abc` | Cannot convert to `int`; can cause bean initialization to fail |
| Key absent, no fallback | No value found | May fail with unresolved placeholder during bean creation |
| Key has empty string | Empty value may still count as declared | Depending on target type and converter, may fail or become `null` |

Do not confuse **selecting a value** with **validating a value**. A placeholder default is neither a validator nor a fixer for every bad string.

## 4. Converting to String, integers, and floating-point numbers

`String` is the most direct case:

```java
@Value("${store.name:My Store}")
private String storeName;
```

If `store.name` exists, the field receives the value from configuration; otherwise, it receives `"My Store"`.

For numeric types:

```java
@Value("${store.max-orders:100}")
private int maxOrders;

@Value("${store.tax-rate:0.08}")
private double taxRate;
```

Spring uses an appropriate type conversion mechanism to convert from the configuration value to `int` or `double`. In the example:

```yaml
store:
  max-orders: 250
  tax-rate: 0.10
```

The results are `maxOrders=250` and `taxRate=0.10`.

### 4.1. Primitive types and wrapper types

`int`, `long`, and `double` are Java primitive types; `Integer`, `Long`, and `Double` are wrapper objects. Key difference when encountering `null`:

- Primitive types cannot accept `null` as a valid value.
- Wrapper types can represent the absence of a value, but that **does not mean** `@Value` automatically handles every missing property safely.
- A non-numeric string such as `"many"` still cannot be converted into a valid `Integer`.

```java
@Value("${store.max-orders:100}")
private Integer maxOrders;
```

Here the default is 100, not `null`. If you want to express "no value" as a business state, design the representation and checks explicitly rather than relying on a converter handling empty strings.

### 4.2. Syntactically invalid values do not trigger fallbacks

Example:

```yaml
store:
  max-orders: many
```

With:

```java
@Value("${store.max-orders:100}")
private int maxOrders;
```

Spring **did find** the key `store.max-orders`. Therefore, the fallback `100` is not used just because `"many"` is not a number. Type conversion fails and the bean may fail to initialize. To fix it, supply a valid value or build explicit checking/recovery logic.

This is an operational advantage: the application can fail early when critical configuration has the wrong type, rather than silently running with a value unintended by deployment.

## 5. Converting to boolean

An enable/disable field is typically configured with `true` or `false`:

```yaml
audit:
  enabled: true
```

And injected into:

```java
@Value("${audit.enabled:false}")
private boolean auditEnabled;
```

If `audit.enabled=true` is present, the field is `true`. If the key is missing, fallback `false` converts to `boolean false`.

A constructor injection example:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    private final boolean enabled;

    public AuditService(
            @Value("${audit.enabled:false}") boolean enabled) {
        this.enabled = enabled;
    }

    public boolean shouldRecord() {
        return enabled;
    }
}
```

This lets behavior vary across environments without modifying `AuditService`. For example:

```bash
java -jar app.jar --audit.enabled=true
```

Command-line arguments can override YAML configuration following standard source precedence.

Spring has converters for booleans, yet you should stick to readable, consistent `true`/`false` values instead of depending on every textual variant a converter might accept. If configuration has `audit.enabled=maybe`, do not expect fallback `false` to handle the invalid value automatically.

## 6. Converting to Duration and specialized types

Durations are commonly configured as `2s`, `500ms`, or `1m`. In Spring Boot, configuration converters can turn duration expressions into `java.time.Duration` when the appropriate `ConversionService` is registered.

Example:

```yaml
gateway:
  connect-timeout: 2s
  read-timeout: 1500ms
```

With a Spring Boot application supporting `Duration` conversion:

```java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GatewayTimeouts {

    private final Duration connectTimeout;
    private final Duration readTimeout;

    public GatewayTimeouts(
            @Value("${gateway.connect-timeout:3s}")
            Duration connectTimeout,
            @Value("${gateway.read-timeout:2s}")
            Duration readTimeout) {
        this.connectTimeout = connectTimeout;
        this.readTimeout = readTimeout;
    }

    public Duration connectTimeout() {
        return connectTimeout;
    }

    public Duration readTimeout() {
        return readTimeout;
    }
}
```

Expected values in the example are two seconds and 1500 milliseconds. When a matching converter is present, the bean receives two typed `Duration` objects; consuming code does not need to parse `s` or `ms` suffixes manually.

**Environment note:** Type and unit support depends on the active `ConversionService`, framework version, and binding mechanism. Spring Boot provides additional converters for configuration; a plain Spring Framework application should not be assumed to support notations like `3s` by default. If a configuration group contains multiple `Duration` fields or needs explicit unit/validation rules, `@ConfigurationProperties` is usually more suitable.

For duration values, write units explicitly instead of bare numbers:

```yaml
gateway:
  connect-timeout: 3s
```

This is easier to understand than `gateway.connect-timeout=3000`, because readers do not have to guess whether 3000 means milliseconds, seconds, or an application-specific unit.

## 7. Converting to enum

Suppose an application has two processing modes:

```java
public enum DispatchMode {
    SAFE,
    FAST
}
```

Values can be received with `@Value` if a converter suitable for the enum type is active:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DispatchSettings {
    private final DispatchMode mode;

    public DispatchSettings(
            @Value("${dispatch.mode:SAFE}") DispatchMode mode) {
        this.mode = mode;
    }

    public DispatchMode mode() {
        return mode;
    }
}
```

Configuration file:

```yaml
dispatch:
  mode: FAST
```

When the converter maps enum name strings, the bean receives `DispatchMode.FAST`. When the key is absent, `SAFE` is the default value.

This approach has an advantage over free-form strings because the allowed set of values is represented by the enum. However, a value outside the declared set—such as `dispatch.mode=UNKNOWN`—still causes a conversion error rather than falling back to `SAFE`.

To minimize converter differences, write example configurations using the exact declared enum names. For property groups requiring strict control over conversion rules and input errors, using `@ConfigurationProperties` with validation helps centralize the configuration contract.

## 8. Missing keys: with and without defaults

Consider two constructor parameters:

```java
public WorkerSettings(
        @Value("${worker.batch-size}") int batchSize,
        @Value("${worker.max-retries:3}") int maxRetries) {
    // ...
}
```

If `worker.batch-size` does not exist, the placeholder has no fallback. In typical Spring configurations using strict placeholder resolution for bean injection, bean creation can fail because the key cannot be resolved.

Conversely, if `worker.max-retries` is absent, `3` is used. These two forms communicate **two different intents**:

- Without a default: the property may be mandatory in the runtime environment.
- With a default: the application has a designed fallback value.

Do not add fallbacks to every key merely so the application always starts. For instance, a production payment URL or production data warehouse address may need to be provided explicitly. A bad fallback could cause the application to connect to the wrong service.

### 8.1. Defaults belong to the injection expression

`${worker.max-retries:3}` does not add key `worker.max-retries` into `application.yml`. It only states that **this injection point** accepts `3` if the key is not found.

If another bean reads the key via:

```java
environment.getProperty("worker.max-retries")
```

and no configuration source provides the property, the result can be `null`. It has no knowledge of a fallback embedded in the first bean's annotation.

If you need a default value **shared across all lookup sites**, place that value in `application.yml` or a shared configuration source, then reference it without repeating the default in multiple annotations.

## 9. Missing keys vs. empty values

This is one of the easiest traps when using `@Value`.

Suppose:

```java
@Value("${notice.title:Untitled}")
private String title;
```

If `notice.title` is not declared anywhere, `title` receives `Untitled`. But if configuration has:

```properties
notice.title=
```

then the property exists with an **empty value**. Standard placeholder resolution does not treat every empty string as "key absent". The result can be an empty string, not `Untitled`.

With an integer:

```java
@Value("${notice.retry-count:3}")
private int retryCount;
```

and:

```properties
notice.retry-count=
```

the empty value may fail to convert to `int`; during injection, the bean may fail. Do not assume `:3` is a mechanism that fixes all empty or invalid values.

Comparison table:

| Key state | `@Value("${notice.title:Untitled}")` | `@Value("${notice.retry-count:3}") int` |
| --- | --- | --- |
| Does not exist | `Untitled` | 3 |
| Has valid value | Found value | Converted integer |
| Has empty value | May be empty string | May fail type conversion |
| Has wrong-type value | Remains string | May fail type conversion |

A useful design rule: **defaults handle absence; validation handles presence with invalid content**.

## 10. Canonical key names and environment variables

Consistent property naming helps Spring Boot resolve placeholders across multiple sources.

YAML example:

```yaml
orders:
  max-retries: 4
```

Write placeholders in canonical lowercase form, using hyphens for multi-word names:

```java
@Value("${orders.max-retries:3}")
private int maxRetries;
```

This helps Spring Boot apply lookup rules compatible with its property naming; the same property can be supplied from config files or environment variables by convention.

Example on Linux/macOS:

```bash
ORDERS_MAXRETRIES=8 java -jar app.jar
```

In Spring Boot's standard mapping, dots become underscores, hyphens in property names are removed, and names are uppercased when expressed as environment variables. Thus `orders.max-retries` corresponds to `ORDERS_MAXRETRIES`.

Do not assume `ORDERS_MAX_RETRIES` is always equivalent to `orders.max-retries` across every lookup mechanism. A consistent key naming convention is especially important with `@Value` because it differs from whole-object binding with `@ConfigurationProperties`.

Additionally, values can come from higher-precedence sources:

```bash
java -jar app.jar --orders.max-retries=9
```

When both YAML value `4` and CLI argument `9` exist in a standard setup, the injection point uses `9`. Fallback `3` is not used because the property is already present.

## 11. Default values can also reference other properties

A fallback does not have to be a constant. Spring allows nested placeholders:

```java
@Value("${orders.max-retries:${defaults.retry-count:3}}")
private int maxRetries;
```

Expected behavior:

1. If `orders.max-retries` exists, use that value.
2. If `orders.max-retries` is absent but `defaults.retry-count` exists, use the default taken from `defaults.retry-count`.
3. If both are absent, use `3`.
4. Convert the result to `int`.

Example configuration file:

```properties
defaults.retry-count=5
```

Without `orders.max-retries`, the result is 5. Adding `orders.max-retries=7` makes the result 7. Removing both gives 3.

This expression style is useful if multiple properties share defaults from a common setting. However, deeply nested defaults are hard to read and hard to trace during deployment. If configuration has complex dependency relationships, consider `@ConfigurationProperties` and explicit computation in Java.

### 11.1. Defaults containing colons

A default value can be a URL:

```java
@Value("${service.endpoint:http://localhost:8080/api}")
private String endpoint;
```

In standard placeholder mechanics, the **first** colon separates the key name from the default; `http://localhost:8080/api` is the default value used when `service.endpoint` is missing. Do not read colons inside the URL as another placeholder.

If the default string contains special syntax or complex nested expressions, check escaping and how intermediate configuration layers process it; do not assume every string containing `$` or `:` passes unchanged through every deployment tool.

## 12. Distinguishing placeholders and SpEL in @Value

`@Value` can use `${...}` placeholder syntax or Spring Expression Language (SpEL) `#{...}` syntax.

```java
@Value("${pool.size:8}")
private int poolSize;

@Value("#{2 * 3}")
private int six;
```

The first field uses **configuration lookup**. The second requests **expression evaluation**. Both can yield `int`, yet their mechanisms and meanings differ.

In some cases, placeholders resolve first and the result participates in SpEL:

```java
@Value("#{${pool.workers:4} * 2}")
private int maxConnections;
```

With `pool.workers=5`, the expected result is `10`. But if `pool.workers=fast`, the expression is no longer a valid numeric multiplication. This is not an appropriate way to "fix" mistyped configuration.

Do not overuse SpEL to build complex configuration logic, especially when values might come from untrusted sources. For business calculations or multi-branch rules, a Java class with clear tests and validation is usually easier to maintain.

**Another distinction to remember:** values declared in `application.yml` are not automatically evaluated as SpEL in the same way a `@Value("#{...}")` annotation is evaluated. Do not treat every configuration string as expression code.

## 13. Lists, maps, and complex structures: limits of @Value

Previous examples are scalars: strings, numbers, booleans, durations, or enums. Yet complex configuration can contain lists and nested objects:

```yaml
mail:
  retries: 3
  recipients:
    - ops@example.invalid
    - audit@example.invalid
  smtp:
    host: smtp.example.invalid
    port: 2525
```

If each property is injected individually via `@Value`, the class ends up holding many annotations, string key names, and type conversion rules coupled to the source format. For lists, conversion behavior can differ between comma-separated strings and indexed entries coming from YAML; do not treat `@Value("${mail.recipients}")` as a guaranteed solution for every list type across every source.

A more appropriate approach is `@ConfigurationProperties`:

```java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        int retries,
        List<String> recipients,
        Smtp smtp
) {
    public record Smtp(String host, int port) {}
}
```

After registering `MailProperties` via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, the Spring Boot binder binds each property and element structurally. For input checking requirements, suitable Bean Validation can be added.

You can keep this division of roles in mind:

- `@Value`: suits a few individual values that need to be injected where used.
- `@ConfigurationProperties`: suits a structured configuration group with multiple fields, centralized type conversion, and validation.
- `Environment`: suits selective single-key lookups or diagnosing configuration values.

There is no need to replace all `@Value` usages with `@ConfigurationProperties` in every case; choose based on the size and cohesion of the configuration group.

## 14. Complete experiment: type conversion and fallback configuration

Let's build a small application to observe both value selection and type conversion steps.

Create `src/main/resources/application.yml`:

```yaml
demo:
  name: SampleService
  enabled: true
  max-retries: 4
  batch-size: 20
```

Create `DemoConfigurationApplication.java`:

```java
package com.example.valueconversion;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoConfigurationApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoConfigurationApplication.class, args);
    }

    @Bean
    ApplicationRunner printDemo(DemoSettings settings) {
        return args -> {
            System.out.println("=== VALUE CONVERSION ===");
            System.out.println("name        = " + settings.name());
            System.out.println("enabled     = " + settings.enabled());
            System.out.println("maxRetries  = " + settings.maxRetries());
            System.out.println("batchSize   = " + settings.batchSize());
            System.out.println("========================");
        };
    }
}
```

Create `DemoSettings.java`:

```java
package com.example.valueconversion;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DemoSettings {

    private final String name;
    private final boolean enabled;
    private final int maxRetries;
    private final long batchSize;

    public DemoSettings(
            @Value("${demo.name:Unnamed}") String name,
            @Value("${demo.enabled:false}") boolean enabled,
            @Value("${demo.max-retries:3}") int maxRetries,
            @Value("${demo.batch-size:10}") long batchSize) {
        this.name = name;
        this.enabled = enabled;
        this.maxRetries = maxRetries;
        this.batchSize = batchSize;
    }

    public String name() {
        return name;
    }

    public boolean enabled() {
        return enabled;
    }

    public int maxRetries() {
        return maxRetries;
    }

    public long batchSize() {
        return batchSize;
    }
}
```

Package the application using Gradle `bootJar` or Maven according to the project structure, then use the path to the executable JAR. `app.jar` below is an illustrative name.

### Run A: YAML only

```bash
java -jar app.jar
```

Expected output:

```text
name        = SampleService
enabled     = true
maxRetries  = 4
batchSize   = 20
```

All keys exist. Spring does not need to use any fallback in the constructor.

### Run B: override via command-line arguments

```bash
java -jar app.jar \
  --demo.enabled=false \
  --demo.max-retries=9 \
  --demo.batch-size=35
```

Expected output:

```text
name        = SampleService
enabled     = false
maxRetries  = 9
batchSize   = 35
```

All numbers and booleans are converted to the declared Java types. `name` still comes from YAML because the command line did not override this key.

### Run C: testing fallbacks

Create a test configuration where `demo.enabled`, `demo.max-retries`, and `demo.batch-size` do not appear in any active source. You can temporarily remove those lines from YAML, repackage, and run without passing overrides:

```bash
java -jar app.jar
```

Expected output using fallbacks:

```text
name        = SampleService
enabled     = false
maxRetries  = 3
batchSize   = 10
```

Note that if the values still remain in YAML or shell environment variables, fallbacks will not be used. This experiment demonstrates that default values live on each injection point annotation.

### Run D: value cannot convert to int

Run:

```bash
java -jar app.jar --demo.max-retries=many
```

Expectation: while Spring creates `DemoSettings`, the value `many` cannot convert to `int` and bean startup fails with a message related to type conversion or bean creation errors. **It does not receive `3`** even though the annotation has a fallback.

### Run E: key declared as empty

Run:

```bash
java -jar app.jar --demo.max-retries=
```

The provided value is an empty string, unlike omitting the key. For an `int` constructor parameter, this configuration cannot be treated as a valid integer and can cause bean creation to fail. Do not rely on fallback `3` to fix the empty-value case.

## 15. Prediction table before running

The following table assumes the initial YAML file contains `demo.max-retries=4` and the injection point is:

```java
@Value("${demo.max-retries:3}") int maxRetries
```

| Providing source | Effective string/value | Expected result |
| --- | --- | --- |
| YAML only | `4` | `maxRetries = 4` |
| Argument `--demo.max-retries=9` | `9` | `maxRetries = 9` |
| Key absent from all sources | Fallback `3` | `maxRetries = 3` |
| Argument `--demo.max-retries=abc` | `abc` | Error converting to `int` |
| Argument `--demo.max-retries=` | Empty string | May fail when injecting into `int` |

Similar prediction for:

```java
@Value("${demo.enabled:false}") boolean enabled
```

With valid `true` or `false`, the bean receives the corresponding boolean. When the key is absent, it receives `false`. A value that cannot convert to boolean does not turn into the fallback just because a fallback was declared.

When practicing, always change **one factor at a time**: YAML value, environment variable, command-line argument, or key presence. Doing so makes it easy to distinguish source precedence errors, placeholder errors, and type conversion errors.

## 16. Common mistakes when using @Value

### 16.1. Forgetting the $ sign in a placeholder

Incorrect:

```java
@Value("{demo.max-retries:3}")
private int maxRetries;
```

The string inside the annotation is now literal text `{demo.max-retries:3}`, not a valid placeholder. If Spring attempts to convert this literal string to `int`, conversion will fail.

Correct:

```java
@Value("${demo.max-retries:3}")
private int maxRetries;
```

### 16.2. Using inconsistent key names

If YAML declares `demo.max-retries` but the annotation writes `${demo.maxretry:3}`, Spring may fail to find the value and use fallback `3`. The application still starts, yet the result does not match intent. For critical keys, use clear names and verify against the source.

### 16.3. Calling an invalid value "missing"

`demo.max-retries=xyz` is a **present** key with a **wrong-type** value. Fallbacks are not designed to hide this type mismatch. You must fix the value or design appropriate error handling.

### 16.4. Using an empty string to request a default

Writing `demo.max-retries=` is not the same as removing the key from sources. An empty string can cause conversion to fail for primitive types. When you want a fallback to apply, omit the key declaration rather than supplying an empty string.

### 16.5. Trying to inject into an object manually created with new

`@Value` is only processed properly within the lifecycle of a Spring-managed object or an object handled by the corresponding framework mechanism. An object created manually with `new` does not automatically receive annotation values.

### 16.6. Relying on values changing after startup

Normally, `@Value` values are supplied to a bean during bean creation. When a config file changes while the application is running, injected fields do not automatically update just because the new file has different values. To observe new configuration, restart the process or use a specifically designed configuration refresh mechanism.

### 16.7. Assuming all complex types convert identically

Simple numbers and booleans rarely cause surprises. Types such as `Duration`, `DataSize`, lists, maps, URIs, or custom types may require appropriate converters, binders, or extra configuration. If your application has structured multi-field configuration, choose `@ConfigurationProperties` instead of attaching scattered `@Value` annotations.

### 16.8. Setting unsafe fallbacks for mandatory data

`@Value("${payment.gateway-url:http://localhost:8080}")` can cause production environments to mistakenly connect to a local test address when configuration is missing. For critical endpoints, it may be better to **omit the fallback** and let the application fail startup rather than choosing a risky default.

## 17. Organizing configuration for easier operations

Some helpful conventions:

1. **Use safe default values.** Low retry counts, optional features disabled, or sensible timeouts can make good defaults, depending on application goals.
2. **State units explicitly.** For durations, prefer `2s` or `500ms` over ambiguous bare numbers.
3. **Use canonical key names.** This makes YAML sources, environment variables, and placeholders easy to trace.
4. **Place shared values in configuration sources.** If three beans need the same fallback, put it in `application.yml` instead of repeating `:3` in three places.
5. **Let beans hold proper types.** Retry counts should be `int`, flags should be `boolean`, and durations should be `Duration` when appropriate converters are ready.
6. **Distinguish missing from invalid.** Missing keys can be resolved by fallbacks; invalid keys need validation or configuration fixes.
7. **Do not print sensitive configuration.** When debugging, print only harmless keys; never accidentally log passwords, tokens, or URLs containing credentials.
8. **Centralize configuration groups as complexity grows.** For multiple related fields, consider `@ConfigurationProperties` and validation rules.

## 18. Comprehension exercises

**Exercise 1.** Given:

```java
@Value("${cache.capacity:128}")
private int capacity;
```

Predict `capacity` when: (a) the key is not declared; (b) `cache.capacity=256`; (c) `cache.capacity=large`. Explain which case uses the fallback and which fails conversion.

**Exercise 2.** Given:

```java
@Value("${jobs.enabled:false}")
private boolean enabled;
```

With YAML `jobs.enabled=true` and command-line `--jobs.enabled=false`, which value is effective? Why is source selection different from converting to `boolean`?

**Exercise 3.** Given:

```java
@Value("${jobs.retry-count:${defaults.retry-count:2}}")
private int retryCount;
```

Predict the result under three states: only `defaults.retry-count=6`; also adding `jobs.retry-count=8`; or neither key exists. The results are 6, 8, and 2, respectively, under standard placeholder resolution.

**Exercise 4.** An application has `@Value("${server.label:App}") String label`, yet the properties file declares `server.label=`. Why might the result be an empty string instead of `App`? Distinguish an absent key from a key with an empty value.

**Exercise 5.** Given `@Value("${gateway.timeout:3s}") Duration timeout`. Why do you need to pay attention to the active `ConversionService`? When should you move durations into a validated `@ConfigurationProperties` class instead of a single annotation?

**Exercise 6.** Write a bean receiving two values—`orders.max-retries` of type `int` and `orders.enabled` of type `boolean`—via constructor, with fallbacks 3 and false respectively. Then try changing each value on the command line and observe the results.

## 19. Key takeaways

When using `@Value`, clearly separate the steps:

```text
@Value("${orders.max-retries:3}")
             |
             v
   Look up orders.max-retries in Environment
             |
       +-----+------+
       |            |
     Found      Not found
       |            |
   Use value     Use "3"
       |            |
       +-----+------+
             |
             v
       Convert to int
             |
       +-----+------+
       |            |
    Valid       Wrong type
       |            |
       v            v
   Inject into  Bean creation
   constructor      error
```

**Placeholders decide where a value comes from and which default to use when missing; type conversion decides whether that value can become the target Java type.** Mistyped values and empty values do not automatically turn into fallbacks.

Use `@Value` when you need a small number of standalone properties, especially via constructor injection. When configuration becomes a structured set with multiple validation rules or converters, switch to a `@ConfigurationProperties` design for clarity and maintainability.

References: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties), [Spring Framework — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html).