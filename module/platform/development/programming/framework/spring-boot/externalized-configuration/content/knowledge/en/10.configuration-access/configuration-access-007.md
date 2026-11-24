# Using SpEL in `@Value` and Its Limits When Reading Configuration Data

## 1. Context: from configuration properties to values injected into a bean

In Spring Boot, application configuration can be supplied via `application.properties`, `application.yml`, environment variables, Java system properties, command-line arguments, and other `PropertySource`s. A bean may need to read these values to determine timeouts, threshold limits, or feature behavior.

Spring Framework supports the `@Value` annotation to inject a value into a container-managed field, constructor parameter, method parameter, or setter. Two common syntaxes in `@Value` are:

~~~java
@Value("${app.name:demo}")
private String appName;

@Value("#{T(java.lang.Math).max(2, 5)}")
private int maximum;
~~~

They look similar, yet their mechanisms differ:

- **Property placeholder `${...}`**: queries a property name in the configuration system, optionally with a default value.
- **Spring Expression Language (SpEL) `#{...}`**: evaluates an expression that can perform calculations, conditionals, property access, method calls, or bean references within an evaluation context.

SpEL is useful when you need to **transform a small value at the injection point**. However, for a large, structured configuration group needing type conversion and validation, Spring Boot generally recommends `@ConfigurationProperties`. Understanding this boundary helps avoid turning configuration into a place holding hard-to-control business logic.

## 2. Two syntaxes: `${...}` is not synonymous with `#{...}`

### 2.1. Property placeholder: looking up configuration by key

~~~java
@Value("${app.retry.max-attempts:3}")
private int maxAttempts;
~~~

Here Spring looks up the property `app.retry.max-attempts`. If its value is `5`, the field is injected with `5`. If not found, default `3` is used. Conversion to `int` is handled through Spring's appropriate type conversion system.

Characteristics:

- The part inside the braces is a **property name**, not a Java statement.
- The `:` separates the key from the fallback value.
- A present but **invalid** value is not automatically replaced with the default.
- Placeholders generally take the final value after Spring evaluates precedence order among configuration sources.

### 2.2. SpEL: evaluating an expression

~~~java
@Value("#{6 * 7}")
private int answer;

@Value("#{'spring boot'.toUpperCase()}")
private String title;

@Value("#{T(java.lang.Math).max(10, 25)}")
private int limit;
~~~

The corresponding results are `42`, `SPRING BOOT`, and `25`. SpEL uses its own syntax, not full Java source code: you cannot write arbitrary Java statements inside a SpEL string.

Quick identification guide:

| Syntax | Example | Purpose |
| --- | --- | --- |
| `${key}` | `${server.port}` | Property reference |
| `${key:default}` | `${app.timeout:5s}` | Reference with fallback value |
| `#{expression}` | `#{2 + 3}` | Evaluate expression |
| Combined | `#{${app.workers:2} * 2}` | Read configuration then compute |

**Remember:** the opening delimiters `${` and `#{` are different. Writing `${2 + 3}` is not a way to compute `5`; Spring will treat `2 + 3` as a property name to look up.

## 3. Introductory example with `@Value` in a constructor

Suppose `src/main/resources/application.yml` has:

~~~yaml
app:
  retry:
    max-attempts: 4
  gateway:
    connect-timeout: 3s
  mode: development
~~~

Create the bean:

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GatewaySettings {

    private final int maxAttempts;
    private final int doubledAttempts;
    private final String normalizedMode;

    public GatewaySettings(
            @Value("${app.retry.max-attempts:3}") int maxAttempts,
            @Value("#{${app.retry.max-attempts:3} * 2}") int doubledAttempts,
            @Value("#{'${app.mode:local}'.toUpperCase()}") String normalizedMode) {

        this.maxAttempts = maxAttempts;
        this.doubledAttempts = doubledAttempts;
        this.normalizedMode = normalizedMode;
    }

    public int maxAttempts() {
        return maxAttempts;
    }

    public int doubledAttempts() {
        return doubledAttempts;
    }

    public String normalizedMode() {
        return normalizedMode;
    }
}
~~~

Under the loaded properties above, the values are:

~~~text
maxAttempts     = 4
doubledAttempts = 8
normalizedMode  = DEVELOPMENT
~~~

Explanation:

1. `${app.retry.max-attempts:3}` is processed as a property reference.
2. In `#{${app.retry.max-attempts:3} * 2}`, the placeholder result forms the numeric expression `4 * 2`.
3. SpEL evaluates the multiplication and passes the result as `int` to the constructor parameter.
4. The string example wraps the value in single quotes so it becomes a SpEL string literal.

**Important limitation:** embedding a configuration string directly inside a SpEL expression can be dangerous or break syntax if the value contains single quotes, special characters, or untrusted text. The uppercasing example above should only be used to illustrate syntax; for external data, prefer receiving a string via placeholder or Binder and transforming the string in regular Java.

## 4. Processing order when combining placeholders and SpEL

When a `@Value` expression contains both a placeholder and SpEL, conceptually picture this sequence of steps:

~~~text
Spring Boot configuration sources
       ↓
Look up property name / resolve placeholder
       ↓
Substitute resolved value into expression
       ↓
Evaluate SpEL in the bean's context
       ↓
Convert result to injection point's target type
       ↓
Create bean with injected value
~~~

Example:

~~~java
@Value("#{${app.pool.size:8} + 2}")
private int poolSizeWithBuffer;
~~~

If `app.pool.size=10`, Spring can evaluate `10 + 2` and inject `12`.

But if the configuration is:

~~~yaml
app:
  pool:
    size: many
~~~

then the expression formed from the placeholder is no longer a valid arithmetic operation. Default `8` does not help because key `app.pool.size` still **exists**. An error can occur during SpEL evaluation or type conversion, leading to bean creation failure.

When an expression has important business effects, **move the calculation into Java code** for easier testing, debugging, and validation. SpEL is not a substitute for input data validation.

## 5. Common SpEL operations in `@Value`

### 5.1. Arithmetic operations

~~~java
@Value("#{2 + 5}")
private int sum;

@Value("#{10 * 3}")
private int total;

@Value("#{100 / 4}")
private int quotient;

@Value("#{10 % 3}")
private int remainder;
~~~

SpEL supports addition, subtraction, multiplication, division, modulo, and other appropriate operators. Division, numeric promotion, and target type conversion must be understood according to expression semantics; do not assume it always behaves like integer division in every case.

Example using a configuration value:

~~~yaml
app:
  worker:
    base-count: 4
~~~

~~~java
@Value("#{${app.worker.base-count:2} * 3}")
private int calculatedWorkers;
~~~

In this example, the result can be `12`. To enforce min/max thresholds, use method calls or Java code instead of increasing expression complexity.

### 5.2. Comparisons and conditionals

~~~java
@Value("#{10 > 5}")
private boolean enabled;

@Value("#{${app.retry.max-attempts:3} > 5 ? 'aggressive' : 'normal'}")
private String retryMode;
~~~

Comparisons produce booleans; the ternary operator `condition ? trueValue : falseValue` picks one of two branches.

Suppose `app.retry.max-attempts=8`, `retryMode` is `aggressive`. If the value is `2`, the result is `normal`.

This can suit a simple display flag. If the retry mode affects complex behavior, model it with a tested Java policy or class rather than scattering the same conditional across many `@Value` annotations.

### 5.3. String operations

~~~java
@Value("#{'hello'.toUpperCase()}")
private String upper;

@Value("#{'  demo  '.trim()}")
private String trimmed;
~~~

SpEL can invoke methods on eligible objects. These operations execute when the expression is evaluated; not every operation Java supports belongs inside configuration annotations.

### 5.4. Referencing static methods or Java types

~~~java
@Value("#{T(java.lang.Math).max(4, 9)}")
private int safeMin;

@Value("#{T(java.lang.Integer).parseInt('42')}")
private int parsed;
~~~

`T(java.lang.Math)` is a type reference in SpEL. This example demonstrates access to types and static methods, not a suggestion to embed complex parsing logic in annotations.

## 6. Elvis operator and fallback values in SpEL

Besides placeholder default syntax `${key:default}`, SpEL has the **Elvis operator `?:`**:

~~~java
@Value("#{systemProperties['user.region'] ?: 'local'}")
private String region;
~~~

This expression retrieves `user.region` from Java system properties in the SpEL evaluation context. If the value is null or empty per Spring's Elvis semantics, it can fall back to `local`.

Distinction:

- `${app.region:local}`: fallback value of a **property placeholder**, used when the configuration key cannot be resolved.
- `#{someExpression ?: 'local'}`: fallback value **inside SpEL** after evaluating the left-hand operand.

Do not assume the two are always equivalent, because the target being queried and empty-string handling can differ. In particular, `systemProperties['user.region']` accesses a **Java system property**, which is not automatically equivalent to looking up `app.region` across the entire `Environment`.

When the goal is simply "read a Spring Boot property, or use a default if missing", the clearer and safer approach is usually:

~~~java
@Value("${app.region:local}")
private String region;
~~~

## 7. Accessing Java system properties with SpEL

A traditional example of `@Value` with SpEL is accessing the `systemProperties` map:

~~~java
@Value("#{systemProperties['user.home']}")
private String userHome;

@Value("#{systemProperties['java.version']}")
private String javaVersion;

@Value("#{systemProperties['user.region'] ?: 'unknown'}")
private String userRegion;
~~~

`systemProperties` exposes Java system properties in the default Spring bean expression evaluation context. Values such as `user.home` and `java.version` are provided by the JVM.

You can supply a Java system property at launch:

~~~bash
java -Duser.region=asia -jar app.jar
~~~

Then the expression reading `user.region` can receive `asia`.

**Scope warning:** accessing a system property directly **differs** from looking up a Spring configuration name through `Environment`. If a property can come from environment variables, `application.yml`, and CLI arguments, consider using `${canonical-key}` or `@ConfigurationProperties` to respect Spring Boot's configuration source mechanisms.

## 8. Accessing another bean with SpEL

SpEL has syntax to reference a bean via the `@` symbol:

~~~java
@Value("#{@featurePolicy.isEnabled()}")
private boolean featureEnabled;
~~~

Bean example:

~~~java
import org.springframework.stereotype.Component;

@Component("featurePolicy")
public class FeaturePolicy {
    public boolean isEnabled() {
        return true;
    }
}
~~~

When Spring evaluates the expression, it looks up the `featurePolicy` bean and calls `isEnabled()`.

This looks dynamic syntactically, yet **the injected value is still typically computed when the bean is created**, not on every field access. If `featurePolicy`'s state changes afterward, the injected boolean field does not update automatically.

That leads to a practical rule:

- Need a **stable configuration value** at bean initialization: `@Value` may fit.
- Need **business state that changes over time**: inject the `FeaturePolicy` bean itself and call its method at use time, instead of snapshotting the result with `@Value`.

Example to use when state can change:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final FeaturePolicy featurePolicy;

    public CheckoutService(FeaturePolicy featurePolicy) {
        this.featurePolicy = featurePolicy;
    }

    public boolean canUseFeatureNow() {
        return featurePolicy.isEnabled();
    }
}
~~~

## 9. SpEL with lists: representations and limits

SpEL has inline list syntax:

~~~java
@Value("#{{'dev', 'test', 'prod'}}")
private java.util.List<String> environments;
~~~

The expression `{'dev', 'test', 'prod'}` is a list literal in SpEL syntax, not Java array initializer syntax. `#{...}` wraps the entire expression; hence two adjacent pairs of braces are visible.

Another case is configuration containing a comma-separated string:

~~~properties
app.notification.channels=email,sms,log
~~~

Which can be illustrated as:

~~~java
@Value("#{'${app.notification.channels:email,log}'.split(',')}")
private String[] channels;
~~~

When the property is `email,sms,log`, `split(',')` produces an array of the corresponding elements.

However, this approach has many limitations:

1. String splitting does not automatically trim extra whitespace per business policy.
2. Values containing commas as data require escaping or a different format.
3. Empty values can produce unexpected element arrays.
4. Values interpolated directly into a SpEL string literal can break syntax when containing quotes.
5. Complex types like lists of objects should not be built from a simple CSV string.

For real configuration lists, prefer YAML sequences and `@ConfigurationProperties`:

~~~yaml
app:
  notification:
    channels:
      - email
      - sms
      - log
~~~

Then bind into `List<String>`. This supports clearer structure, easier validation, and avoids confusing string parsing with configuration data binding.

## 10. SpEL with Maps and structured data

SpEL has an inline map literal:

~~~java
@Value("#{{'timeout': 5000, 'retries': 3}}")
private java.util.Map<String, Integer> options;
~~~

This example represents a static map inside an expression. In application configuration, however, maps are usually loaded from YAML:

~~~yaml
app:
  clients:
    catalog:
      base-url: "https://catalog.example.org"
      timeout: 5s
    inventory:
      base-url: "https://inventory.example.org"
      timeout: 8s
~~~

Do not try to turn this YAML into a long `@Value` string with SpEL map literals. Instead, use `@ConfigurationProperties` to bind into `Map<String, ClientConfig>`.

Example:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(Map<String, ClientConfig> clients) {
    public record ClientConfig(String baseUrl, Duration timeout) {}
}
~~~

That way, `catalog` and `inventory` become map keys, while `base-url` and `timeout` become fields of `ClientConfig`. The Binder has dedicated rules for property names, lists, map keys, and type conversion—far better suited to configuration data than hand-written SpEL map expressions.

## 11. Safe navigation when a value may be null

SpEL supports the **safe navigation operator** `?.` to avoid errors when accessing properties/methods on a null object:

~~~java
@Value("#{systemProperties['user.region']?.toUpperCase() ?: 'LOCAL'}")
private String upperRegion;
~~~

If `systemProperties['user.region']` has no value, `?.toUpperCase()` returns null instead of attempting to call a method on null; the Elvis operator can fall back to `LOCAL`.

However, safe navigation **does not turn every configuration error into a valid value**. For example:

- A string that exists with an invalid format may still fail to parse.
- A non-existent bean in the context can still cause a bean reference to fail.
- Calling methods with side effects carries its own risks.
- Subsequent operations in the expression must each be evaluated independently for nullability.

In configuration, prefer explicit defaults and concrete validation over building very long chains of null-safe operators.

## 12. Does `@Value` support reading an entire configuration tree?

`@Value` is very convenient when a bean needs **one or a few scalars**, for example:

~~~java
@Value("${server.port:8080}")
private int port;

@Value("${app.region:local}")
private String region;
~~~

But `@Value` is not the best API for reading an entire nested configuration tree. For example:

~~~yaml
app:
  upstreams:
    - name: primary
      url: "https://primary.example.org"
      retries: 2
    - name: backup
      url: "https://backup.example.org"
      retries: 1
~~~

The flattened property names for this configuration look like:

~~~properties
app.upstreams[0].name=primary
app.upstreams[0].url=https://primary.example.org
app.upstreams[0].retries=2
app.upstreams[1].name=backup
app.upstreams[1].url=https://backup.example.org
app.upstreams[1].retries=1
~~~

Do not expect a simple expression:

~~~java
@Value("${app.upstreams}")
private Object upstreams;
~~~

to automatically construct a full `List<Upstream>`. Looking up a single property is not the same as the **structured binding** capability of `@ConfigurationProperties`.

For configurations with lists, maps, nested objects, and unit-annotated values, use the Binder. Besides being cleaner, it creates a typed configuration contract that code readers can follow easily.

## 13. The structured alternative: `@ConfigurationProperties`

Suppose configuration has:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
    connect-timeout: 3s
    read-timeout: 10s
    max-attempts: 4
~~~

Instead of:

~~~java
@Value("${app.client.base-url}") private String baseUrl;
@Value("${app.client.connect-timeout:3s}") private String connectTimeout;
@Value("${app.client.read-timeout:10s}") private String readTimeout;
@Value("${app.client.max-attempts:4}") private int maxAttempts;
~~~

you can create a configuration record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        Duration connectTimeout,
        Duration readTimeout,
        int maxAttempts
) {}
~~~

Enable scanning:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientApplication.class, args);
    }
}
~~~

Use in a service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ApiClient {
    private final ClientProperties properties;

    public ApiClient(ClientProperties properties) {
        this.properties = properties;
    }

    public int totalAllowedAttempts() {
        return properties.maxAttempts();
    }
}
~~~

Benefits:

- **Centralized:** all client settings live in one dedicated type.
- **Typed:** `3s` and `10s` bind to `Duration`, avoiding unitless strings.
- **Testable:** tests can instantiate the record directly and verify behavior of configuration-using code.
- **Validatable:** can be combined with Bean Validation when needed.
- **Consistent with relaxed binding:** `base-url` maps to the Java component `baseUrl`.
- **No SpEL needed for logic:** most computation stays in Java instead of being scattered in annotations.

Spring Boot Binder does not evaluate SpEL as an application expression inside arbitrary configuration property values. Do not take `@Value("#{...}")` examples and assume `@ConfigurationProperties` automatically executes those expressions inside every string property the same way.

## 14. Defaults and validation when dropping complex SpEL

There are two separate needs:

1. **Valid defaults:** if a property is absent, we want a safe value.
2. **Validation:** if a property is present yet invalid for business rules, we want the application to report an error.

With `@Value`:

~~~java
@Value("${app.worker-count:4}")
private int workerCount;
~~~

If `app.worker-count=-2`, default `4` is not used: the key already exists. Depending on usage, a negative value can slip through without validation.

With `@ConfigurationProperties`, you can use `@DefaultValue` and Bean Validation:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;
import jakarta.validation.constraints.Min;

@Validated
@ConfigurationProperties(prefix = "app")
public record WorkerProperties(
        @DefaultValue("4") @Min(1) int workerCount
) {}
~~~

This example requires an appropriate validation dependency, typically `spring-boot-starter-validation`. Default `4` applies at the binding layer when no value is supplied, while `@Min(1)` rejects values less than `1` when validation is active.

SpEL could still write `#{T(java.lang.Math).max(1, ...)}` to clamp a number to a floor, but silently fixing bad configuration differs from **failing fast**. For required or sensitive settings, explicit validation is usually better.

## 15. Environment variables and configuration source precedence

Suppose `application.yml` has:

~~~yaml
app:
  retry:
    max-attempts: 3
  client:
    timeout: 5s
~~~

When running:

~~~bash
export APP_RETRY_MAXATTEMPTS=6
export APP_CLIENT_TIMEOUT=12s
java -jar demo.jar
~~~

Spring Boot can use environment variables to override the corresponding Config Data via relaxed binding.

If a bean has:

~~~java
@Value("${app.retry.max-attempts:3}")
private int maxAttempts;
~~~

the value can be `6`, not `3` from YAML or the annotation default `3`.

If run again with:

~~~bash
java -jar demo.jar --app.retry.max-attempts=9
~~~

CLI arguments generally have higher precedence than environment variables and Config Data. With no other overriding source, the value is `9`.

SpEL is also affected by configuration sources when embedding placeholders:

~~~java
@Value("#{${app.retry.max-attempts:3} * 2}")
private int doubledAttempts;
~~~

If the final key value is `9`, the expression evaluates `9 * 2` and the result is `18`.

**Important distinction:** `@Value` does not alter property source precedence. It simply resolves values from the sources Spring has organized, then converts/evaluates the result at the injection point.

## 16. First limit: no automatic updates to running configuration

A bean is created at application startup, for example:

~~~java
@Component
public class FixedThreshold {
    @Value("${app.threshold:10}")
    private int threshold;

    public int currentThreshold() {
        return threshold;
    }
}
~~~

The `threshold` value is normally injected once when the bean is initialized. If someone edits `application.yml` after the process is already running, this field **does not change automatically**.

Similarly, the expression:

~~~java
@Value("#{@featurePolicy.isEnabled()}")
private boolean featureAtStartup;
~~~

does not mean every call to the getter re-evaluates `featurePolicy.isEnabled()`. The result was typically computed once at bean injection time.

If the system needs dynamic configuration refresh, you must design a dedicated mechanism such as intentional bean recreation, replacing config sources via a refresh-capable platform, or reading dynamic state through a service. Do not assume SpEL or `@Value` provides hot reload out of the box.

## 17. Second limit: errors occur during bean creation

There are three common error groups:

### 17.1. Missing required property

~~~java
@Value("${payment.api-key}")
private String paymentApiKey;
~~~

If `payment.api-key` is absent and has no default, placeholder resolution can fail during bean creation. This can be the desired behavior for critical values.

### 17.2. Wrong type or invalid value

~~~java
@Value("${app.max-connections:10}")
private int maxConnections;
~~~

If the environment supplies `APP_MAXCONNECTIONS=abc`, Spring still finds the key, yet converting it to `int` can fail. Defaults do not hide parse errors.

### 17.3. Invalid or incompatible SpEL expression

~~~java
@Value("#{${app.workers:2} * 2}")
private int workerSlots;
~~~

If `app.workers` is the string `two`, the arithmetic expression is no longer valid as expected. Errors can arise during SpEL parsing/evaluation, not just during conversion.

These errors happen when the bean containing the injection point is instantiated—either at startup or later depending on scope/lazy initialization. Successful Java compilation does not guarantee that SpEL expressions or runtime configuration data are valid.

## 18. Third limit: security and untrusted data

SpEL can access beans, properties, methods, and Java types within the granted evaluation context. It is an expression language **far more powerful than reading a configuration key**.

Security principles:

- **Never** take a SpEL expression submitted by an external user and evaluate it directly with a permissive evaluation context.
- **Never** build expressions by concatenating untrusted configuration values into SpEL syntax, because data can break or alter the expression's meaning.
- Do not use SpEL to obscure or enforce critical authorization logic inside hard-to-audit configuration strings when explicit checks can be written in code.
- Never place secrets into logged values, exception messages, or diagnostic endpoints casually.

Example illustrating string concatenation risk:

~~~java
@Value("#{'${app.display-name:guest}'.toUpperCase()}")
private String upperDisplayName;
~~~

If `app.display-name` contains a single quote or text shaped like part of an expression, this direct text embedding can break the SpEL string literal. For external input, instead do:

~~~java
@Value("${app.display-name:guest}")
private String displayName;
~~~

Then process in Java:

~~~java
public String normalizedDisplayName() {
    return displayName.toUpperCase(java.util.Locale.ROOT);
}
~~~

This treats the configuration value as **data**, not expression code.

## 19. Fourth limit: testability and maintainability

Suppose an application contains multiple annotations:

~~~java
@Value("#{${app.workers:4} * ${app.slots-per-worker:2}}")
private int totalSlots;

@Value("#{${app.retry.max-attempts:3} > 5 ? 20 : 10}")
private int retryBudget;

@Value("#{'${app.region:local}'.toUpperCase()}")
private String region;
~~~

Expressions remain readable while simple, but as a project grows:

- Property names are repeated across classes, making renames easy to miss.
- Defaults are scattered rather than centrally documented.
- Validation and value bounds are unclear.
- Testing exact injection point results often requires spinning up a Spring context.
- Dependencies between properties are hidden inside annotation strings.
- A configuration change can break SpEL at runtime without the Java compiler catching it.

A clearer design:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record CapacityProperties(int workers, int slotsPerWorker) {
    public int totalSlots() {
        return workers * slotsPerWorker;
    }
}
~~~

Naturally, provide suitable defaults or validation per the configuration contract. Yet the multiplication has become **plain Java code**, verifiable by unit tests:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CapacityPropertiesTest {
    @Test
    void computesTotalSlots() {
        CapacityProperties props = new CapacityProperties(4, 2);
        assertEquals(8, props.totalSlots());
    }
}
~~~

SpEL remains useful for short, presentational, or framework-integration expressions; do not abuse it as a second business language.

## 20. Fifth limit: behavior inside vs. outside the Spring container

`@Value` is not an annotation processed by the JVM itself. It requires Spring container infrastructure—typically the appropriate BeanPostProcessors/BeanFactory—to resolve and inject values.

Example:

~~~java
@Component
public class AppInfo {
    @Value("${app.name:demo}")
    private String name;

    public String name() {
        return name;
    }
}
~~~

If you instantiate the object directly with `new AppInfo()` outside the Spring container, the `name` field **is not injected** by `@Value`. In a plain Java unit test, creating such an object directly without DI will not yield the same result as when Spring initializes the bean.

With a constructor-injection design:

~~~java
public class AppInfo {
    private final String name;

    public AppInfo(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

testing becomes much simpler. If Spring needs to resolve placeholders, put `@Value` on the constructor parameter of a managed bean:

~~~java
@Component
public class ManagedAppInfo {
    private final String name;

    public ManagedAppInfo(@Value("${app.name:demo}") String name) {
        this.name = name;
    }
}
~~~

Choose the approach matching your goal: for classes with multiple dependencies and configuration values, constructor injection usually expresses bean requirements more clearly than field injection.

## 21. SpEL vs. reading configuration via `Environment`

When you want to retrieve a property without needing SpEL, you can use Spring `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RegionReader {
    private final Environment environment;

    public RegionReader(Environment environment) {
        this.environment = environment;
    }

    public String region() {
        return environment.getProperty("app.region", "local");
    }

    public int retryCount() {
        return environment.getProperty("app.retry.max-attempts", Integer.class, 3);
    }
}
~~~

Advantages:

- Property name and default are explicit parameters.
- Results can be used in Java for complex logic.
- Can be called on demand if designed to read from `Environment` at execution time.

However, `Environment#getProperty` is not a full structural Binder for lists/maps/nested objects. Moreover, calling `Environment` again does not automatically reload Config Data files from disk. For systems with dynamic configuration updates, corresponding sources and refresh mechanisms must be present.

Comparison table:

| Need | Typically suitable tool |
| --- | --- |
| A scalar with a default | `@Value("${key:default}")` |
| A short calculation/condition at the injection point | `@Value("#{...}")` |
| Multiple structured keys, lists/maps, validation | `@ConfigurationProperties` |
| Looking up a key in Java at runtime | `Environment#getProperty(...)` |
| Business logic, complex calculations, isolated testing | Java methods or services |
| Reading data that changes after startup | Dedicated configuration source/refresh mechanism or service |

## 22. Common confusion and mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `${2+3}` does not yield `5` | Confusing placeholders with SpEL | Use `#{2+3}` |
| `@Value` reports missing key | Placeholder has no default and property is not found | Provide configuration or a valid default |
| SpEL expression fails when a variable holds a quoted string | Interpolating value into a SpEL string literal | Inject the string separately and process in Java |
| Field value does not change after editing YAML | Field is injected at bean creation, no auto-refresh | Restart or design a refresh mechanism |
| `systemProperties['x']` misses values in `application.yml` | Reading JVM system properties, not full `Environment` | Use `${x}` or `Environment` |
| SpEL inside config strings is not evaluated as expected by Binder | `@ConfigurationProperties` does not share `@Value`'s SpEL semantics | Bind plain data, move logic to Java |
| `@Value` intended for a list of objects only gets a string | Property placeholder is not a structured binder | Use `@ConfigurationProperties` |
| Has a default yet still fails to parse | Key exists with wrong-type value | Add validation and fix configuration |
| `@Value` on an object created via `new` does not run | Object is not managed by Spring | Use Spring DI or pass explicit parameters |
| Sensitive data appears in logs | Printing configuration values or expressions directly | Mask/redact; never log secrets |

## 23. Practice exercises

### Exercise 1 — Distinguish syntax

Three annotations:

~~~java
@Value("${app.count:4}")
private int a;

@Value("#{2 * 3}")
private int b;

@Value("#{${app.count:4} * 3}")
private int c;
~~~

Suppose `app.count=5` with no higher-precedence source. Compute `a`, `b`, `c`.

**Answer:** `a=5`, `b=6`, `c=15`. Placeholders retrieve `5`, while SpEL evaluates multiplication.

### Exercise 2 — Mistyped value

Configuration:

~~~yaml
app:
  count: invalid
~~~

Bean:

~~~java
@Value("#{${app.count:4} * 3}")
private int total;
~~~

Question: will `total` default to `12`?

**Answer:** no. Key `app.count` exists, so default `4` is not used. Expression evaluation can fail because string `invalid` is not a number.

### Exercise 3 — Does SpEL update automatically?

A bean has:

~~~java
@Value("#{@featurePolicy.isEnabled()}")
private boolean featureEnabled;
~~~

After the bean is created, `featurePolicy` changes state. Does `featureEnabled` update automatically?

**Answer:** normally no. It is a snapshot value injected when the bean was created. To observe the new state, inject the `featurePolicy` bean and call `isEnabled()` at use time.

### Exercise 4 — Choose the config reading API

Given YAML:

~~~yaml
app:
  clients:
    - name: primary
      timeout: 3s
    - name: backup
      timeout: 7s
~~~

Choose among `@Value`, SpEL, and `@ConfigurationProperties` if you want a `List<Client>`.

**Answer:** `@ConfigurationProperties` is the appropriate choice to bind a typed list of objects; do not cram the entire structure into a SpEL expression.

### Exercise 5 — Elvis and placeholder defaults

Compare:

~~~java
@Value("${app.region:local}")
private String regionA;

@Value("#{systemProperties['app.region'] ?: 'local'}")
private String regionB;
~~~

If `app.region=asia` is declared only in `application.yml`, are both values guaranteed to be identical?

**Answer:** not guaranteed. `regionA` uses Spring property source lookup, whereas `regionB` in the example only reads Java system properties through the `systemProperties` map. The same key name does not imply the same source scope.

### Exercise 6 — Moving an expression to Java

Currently:

~~~java
@Value("#{${app.workers:2} * ${app.slots:4}}")
private int totalSlots;
~~~

If you need to enforce `workers >= 1` and `slots >= 1`, how should it be organized?

**Suggested answer:** bind both properties into a validated `@ConfigurationProperties` class/record, then compute `workers * slots` in a unit-tested Java method. This separates validation and calculation responsibilities, avoiding hiding invalid values behind an annotation calculation.

## 24. Key takeaways

- **`${...}`** retrieves a configuration value; **`#{...}`** evaluates a SpEL expression.
- They can be combined, e.g., `#{${app.count:2} * 2}`, but evaluation requires valid values and can fail at runtime.
- `@Value` is good for **a few simple properties or short expressions**; it is not the default choice for every configuration structure.
- SpEL supports arithmetic, conditionals, static methods, bean references, and safe navigation; this power also demands input control and security awareness.
- **Never embed untrusted strings directly into SpEL syntax.** Inject plain data and process it in Java if needed.
- `@Value` values are normally evaluated **when the bean is created**, and do not update automatically when config files or other bean states change.
- `systemProperties` in SpEL is one specific data source, **not synonymous** with querying all Spring Boot property sources.
- `@ConfigurationProperties` fits nested properties, lists, maps, conversions, typed defaults, and validation.
- Placeholder defaults do not fix a wrong-type or business-invalid value; critical configuration errors should fail early.

## References

- [Spring Framework — Expressions (SpEL)](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Annotation-based Container Configuration: Using `@Value`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)