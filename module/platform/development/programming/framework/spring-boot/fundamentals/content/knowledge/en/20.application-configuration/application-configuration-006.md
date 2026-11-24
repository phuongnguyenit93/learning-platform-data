# `@Value` for Single Values and Differences from SpEL Expressions

In Spring Boot, applications often need small configuration values such as service names, retry counts, feature flags, timeouts, or the current environment name. A direct way is using the `@Value` annotation to tell Spring to inject a value into a bean.

The easiest thing to confuse is the two syntaxes that frequently appear inside `@Value`:

- **Property placeholder `${...}`**: looks up a property in Spring's `Environment` and retrieves that property's value.
- **Spring Expression Language, abbreviated SpEL, `#{...}`**: evaluates an expression, such as arithmetic, a conditional expression, or accessing a Spring bean.

Both can be written inside `@Value`, yet they serve **two different purposes**. For single configuration values, property placeholders are usually clearer. SpEL is useful when you need to compute an expression at injection time, though it should not become a place for complex business logic.

## 1. What is @Value?

`@Value` belongs to Spring Framework:

```java
import org.springframework.beans.factory.annotation.Value;
```

This annotation can be placed on a field, constructor parameter, method parameter, or `@Bean` factory method parameter to specify the value to inject.

Suppose an application has configuration:

```yaml
# application.yml
app:
  display-name: Order Service
  retry-count: 3
  notifications-enabled: true
```

Each value can be injected using:

```java
@Component
public class ApplicationInfo {

    @Value("${app.display-name}")
    private String displayName;

    @Value("${app.retry-count}")
    private int retryCount;

    @Value("${app.notifications-enabled}")
    private boolean notificationsEnabled;

    public String describe() {
        return displayName
                + " (retry=" + retryCount
                + ", notifications=" + notificationsEnabled + ")";
    }
}
```

Spring looks up the corresponding properties, converts them to the appropriate types, and injects them into the `ApplicationInfo` instance.

This uses **field injection** to illustrate the syntax concisely. In application code, constructor injection is generally preferred because dependencies are explicit, easier to test, and can be stored in `final` fields.

`@Value` **does not create a bean by itself**. The class must already be managed by Spring via `@Component`, `@Service`, `@Configuration`, `@Bean`, or an equivalent registration mechanism. Calling `new ApplicationInfo()` directly will not cause Spring to inject values.

## 2. Property placeholder: `${property.name}` syntax

Full placeholder syntax:

```java
@Value("${app.display-name}")
private String displayName;
```

Where:

- `${` opens a property placeholder.
- `app.display-name` is the name of the property to look up.
- `}` closes the placeholder.

If configuration has:

```properties
app.display-name=Order Service
```

then the `displayName` field receives the string `Order Service`.

Visualize the process:

```text
@Value("${app.display-name}")
             │
             ▼
Spring Environment
             │
             ▼
Look up property "app.display-name"
             │
             ▼
"Order Service"
             │
             ▼
Convert type if needed
             │
             ▼
Inject into bean
```

This is a **configuration lookup**, not running a Java expression. For example, `@Value("${2 + 3}")` means "look up a property named `2 + 3`," not "add two numbers."

## 3. Default values with a colon

A placeholder can include a default value using this syntax:

```java
@Value("${app.display-name:Unnamed Service}")
private String displayName;
```

If `app.display-name` does not exist, Spring uses `Unnamed Service`. If the property exists, the configured value takes precedence.

A few examples:

```java
@Value("${app.max-retries:3}")
private int maxRetries;

@Value("${app.feature-enabled:false}")
private boolean featureEnabled;

@Value("${app.region:local}")
private String region;
```

Behavior table:

| Configuration | Annotation | Injected value |
|---|---|---|
| `app.region=ap-southeast-1` | `@Value("${app.region:local}")` | `ap-southeast-1` |
| Missing `app.region` | `@Value("${app.region:local}")` | `local` |
| `app.max-retries=5` | `@Value("${app.max-retries:3}")` | Integer `5` |
| Missing `app.max-retries` | `@Value("${app.max-retries:3}")` | Integer `3` |
| `app.feature-enabled=false` | `@Value("${app.feature-enabled:true}")` | Boolean `false` |

**Note:** default values primarily handle the case where **the property is not found**. A property that exists with an empty value is not necessarily replaced by the default. For example, `app.region=` can inject an empty string into `String` even though the annotation specifies `:local`.

If the application needs to treat null, empty strings, and whitespace-only strings as invalid, validate the value after binding instead of relying solely on placeholder defaults.

### 3.1. Defaults can contain special characters

Example of a default URL:

```java
@Value("${app.callback-url:http://localhost:8080/callback}")
private String callbackUrl;
```

Spring treats the colon after the property name as the separator for the default. The `http://...` portion remains part of the default value content.

However, if a default has complex syntax or requires escaping placeholder characters, consider moving that value into `application.yml` or binding with `@ConfigurationProperties`. Keeping `@Value` expressions simple makes them easier to read and less error-prone when refactoring.

## 4. Where can source properties come from?

Spring Boot prepares `Environment` with multiple `PropertySource`s. Common sources include:

- `application.properties` or `application.yml`.
- Profile-specific files, such as `application-dev.yml`.
- Operating system environment variables.
- Java system properties.
- Command-line arguments `--key=value`.
- Property sources added by the application or tests.

Example in `application.yml`:

```yaml
app:
  payment:
    provider: mock
    max-attempts: 4
```

Code:

```java
@Value("${app.payment.provider}")
private String provider;

@Value("${app.payment.max-attempts:3}")
private int maxAttempts;
```

When launched with the argument:

```bash
java -jar app.jar --app.payment.provider=remote
```

the effective value can be `remote` because command-line properties normally have higher precedence than `application.yml` in a default Boot setup.

For environment variables, Spring Boot supports equivalent naming rules under relaxed binding. For instance, a property canonically named `app.payment.max-attempts` is commonly represented in an environment variable as `APP_PAYMENT_MAXATTEMPTS`. Use **canonical kebab-case property names** in `@Value` so Spring Boot can apply consistent name lookup rules.

Actual precedence and resolution behavior depend on the property sources loaded. If a value differs from expectations, inspect the effective value in `Environment`, active profiles, and launch arguments rather than opening just a YAML file.

## 5. Constructor injection with @Value

Constructor injection makes dependencies and configuration values part of the object construction contract:

```java
package com.example.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class RetryService {

    private final int maxAttempts;
    private final boolean enabled;

    public RetryService(
            @Value("${app.retry.max-attempts:3}") int maxAttempts,
            @Value("${app.retry.enabled:true}") boolean enabled) {
        this.maxAttempts = maxAttempts;
        this.enabled = enabled;
    }

    public boolean mayRetry(int attempt) {
        return enabled && attempt < maxAttempts;
    }
}
```

Benefits over field injection:

1. Both required values are visible on the constructor.
2. Fields can be declared `final`.
3. Unit tests can instantiate the object directly with `new RetryService(3, true)` without a Spring context.
4. The object cannot exist in a state missing the values the constructor requires.
5. Matches the style used to inject other service/repository dependencies.

`@Value` here does not decide where retry logic lives. It only supplies configuration values; business logic remains in the service's methods.

### 5.1. Combining bean dependencies and property values

```java
@Service
public class ReportService {

    private final ReportRepository repository;
    private final int pageSize;

    public ReportService(
            ReportRepository repository,
            @Value("${app.reports.page-size:50}") int pageSize) {
        this.repository = repository;
        this.pageSize = pageSize;
    }
}
```

Spring resolves `ReportRepository` as a dependency by type; the `pageSize` parameter is resolved via placeholder. Both injection styles can coexist in the same constructor.

## 6. @Value on @Bean method parameters

You can use `@Value` when creating beans through Java configuration.

```java
import java.time.Clock;
import java.time.ZoneId;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock applicationClock(
            @Value("${app.clock.zone:UTC}") String zoneId) {
        return Clock.system(ZoneId.of(zoneId));
    }
}
```

Here:

- `@Bean` declares a factory method creating a `Clock`.
- `@Value` supplies the configuration value into the `zoneId` parameter.
- The factory method converts the timezone name into a `ZoneId`.
- Spring manages the returned `Clock` instance.

This pattern is especially useful when instantiating classes from the JDK or third-party libraries that do not carry Spring annotations.

If `app.clock.zone` is an invalid string, `ZoneId.of(...)` throws an exception and the bean fails to initialize. `@Value` does not automatically validate domain rules for every value.

## 7. Type conversion from String to Java values

`Environment` supplies property values and Spring uses its type conversion infrastructure during injection. For common scalar types, you rarely need to parse manually.

For example:

```java
@Value("${app.name:Demo}")
private String name;

@Value("${app.worker-count:4}")
private int workerCount;

@Value("${app.audit-enabled:false}")
private boolean auditEnabled;

@Value("${app.failure-rate:0.05}")
private double failureRate;
```

If configured:

```properties
app.worker-count=8
app.audit-enabled=true
app.failure-rate=0.12
```

Spring attempts to convert the corresponding strings into `int`, `boolean`, and `double`.

**When type conversion fails:** for example, `app.worker-count=many` on an `int` field, the application can fail during bean creation because the value is invalid. The default `:4` does not save a property that exists but holds unconvertible content.

Do not use untrusted configuration values without bounds. For example, `workerCount` could parse to a huge or negative number; both are valid `int` values yet invalid for business logic. If you need validations like min/max, consider `@ConfigurationProperties` with Bean Validation.

### 7.1. Duration, DataSize, and complex types

Spring Boot supports binding duration/size values in many ways, especially via `@ConfigurationProperties`. With `@Value`, conversion behavior also depends on field type, the conversion service, and version-specific supporting annotations/infrastructure.

For example, instead of assuming a string like `10s` always converts automatically into every time type you want, you can inject a String and parse it explicitly:

```java
@Bean
public ClientSettings clientSettings(
        @Value("${app.client.timeout:PT10S}") String timeout) {
    return new ClientSettings(
            java.time.Duration.parse(timeout)
    );
}
```

This example standardizes durations on ISO-8601 format such as `PT10S`. If you want friendlier syntax like `10s` alongside validation and metadata, `@ConfigurationProperties` is usually a better fit.

## 8. Missing property: what happens?

Suppose you declare:

```java
@Value("${payment.api-endpoint}")
private String apiEndpoint;
```

but `payment.api-endpoint` is absent from all `Environment` sources. In a standard Spring Boot application with placeholder resolution, bean creation fails with a message like:

```text
Could not resolve placeholder 'payment.api-endpoint'
```

This is a **startup configuration error**, which is usually far better than discovering a missing endpoint while handling a live request.

There are three ways to handle this, depending on intent:

1. **Required property:** keep the placeholder without a default so startup fails if it is missing.
2. **Optional property with a valid default:** use `${payment.api-endpoint:http://localhost:8080}`.
3. **Constrained configuration group:** use `@ConfigurationProperties` and validation to express required fields and relationships among them.

Do not add dummy defaults for every secret or endpoint just to make the application start. An incorrect default can send requests to the wrong system and be harder to diagnose than a fail-fast error.

### 8.1. Empty value differs from non-existent property

For example:

```properties
app.label=
```

and:

```java
@Value("${app.label:My Application}")
private String label;
```

The property can resolve to an empty string instead of using the default. If an empty string is unacceptable, validate after injection or bind via a validatable mechanism.

## 9. Literal values in @Value

`@Value` does not have to contain a placeholder or SpEL. You can inject a literal:

```java
@Value("Local Mode")
private String label;

@Value("5")
private int retryCount;
```

In the second example, the literal `"5"` is converted to an integer matching the field.

However, literals are not external configuration. If a value is always fixed in code, a Java constant or normal constructor argument is usually clearer:

```java
private static final int DEFAULT_PAGE_SIZE = 50;
```

Using `@Value` is specifically meaningful when values need to come from `Environment` or an expression evaluated by Spring.

## 10. What is SpEL?

**Spring Expression Language (SpEL)** is Spring Framework's expression language. Inside `@Value`, a SpEL expression has the form:

```java
@Value("#{2 + 3}")
private int result;
```

Instead of looking up a property named `2 + 3`, Spring evaluates the arithmetic expression and injects `5`.

Common examples:

```java
@Value("#{10 * 4}")
private int capacity;

@Value("#{'spring'.toUpperCase()}")
private String platform;

@Value("#{T(java.lang.Math).max(3, 8)}")
private int maxValue;

@Value("#{true ? 'enabled' : 'disabled'}")
private String status;
```

SpEL supports features such as arithmetic and logical operators, property/method access, bean references, conditional operators, and calling static methods permitted by the expression evaluation context.

Crucially: **SpEL is not full Java syntax**. It has its own grammar and evaluation context. Do not assume any snippet of Java code placed inside `#{...}` will run.

## 11. Core differences between `${...}` and `#{...}`

| Criterion | Property placeholder `${...}` | SpEL `#{...}` |
|---|---|---|
| Purpose | Property lookup | Expression evaluation |
| Data source | Spring `Environment` and property sources | Expression evaluation context, literals, bean references, objects |
| Example | `${app.max-retries:3}` | `#{2 * 3}` |
| Default | Uses `:default` inside the placeholder | Uses SpEL logic such as ternary or Elvis operators |
| Type conversion | Converts property text to target type | Expression result is typed and can be further converted |
| Appropriate complexity | Scalar configuration | Small computations or expression references |
| Primary risks | Missing property, wrong type, overriding source | Unreadable expressions, evaluation errors, danger if untrusted data enters the expression |

These two examples are very different:

```java
@Value("${app.max-retries:3}")
private int maxRetries;
```

Spring looks up property `app.max-retries`; if missing, it uses `3`.

```java
@Value("#{3 * 2}")
private int maxRetries;
```

Spring evaluates `3 * 2`, unrelated to any property name.

The following syntax does not perform addition:

```java
@Value("${3 + 2}")
private int number;
```

Spring tries to find a property named `3 + 2`. If it does not exist and has no default, placeholder resolution normally fails.

## 12. SpEL referencing system properties

SpEL can access objects provided by the expression context. A common example is `systemProperties`:

```java
@Value("#{systemProperties['user.home']}")
private String userHome;
```

This is SpEL retrieving the Java system property `user.home`, not a property placeholder from `application.yml`.

You can supply a fallback using the Elvis operator:

```java
@Value("#{systemProperties['app.region'] ?: 'local'}")
private String region;
```

If the left-hand expression is null or considered empty under corresponding SpEL semantics, the expression returns `local`.

Although this example is useful for learning SpEL, for Spring Boot configuration properties the syntax:

```java
@Value("${app.region:local}")
private String region;
```

usually matches your intent better because it leverages `Environment` and all Spring Boot-managed configuration sources.

## 13. SpEL referencing beans and invoking methods

SpEL can reference a Spring bean using `@beanName` syntax.

Suppose:

```java
@Component
public class TaxRules {

    public double defaultRate() {
        return 0.08;
    }
}
```

Another bean can declare:

```java
@Component
public class InvoiceSettings {

    @Value("#{@taxRules.defaultRate()}")
    private double taxRate;

    public double getTaxRate() {
        return taxRate;
    }
}
```

In the expression `#{@taxRules.defaultRate()}`:

- `@taxRules` references the bean named `taxRules`.
- `defaultRate()` is the method invoked when the expression is evaluated.
- The result `0.08` is injected into the field.

This example demonstrates SpEL's capability. In real applications, **injecting `TaxRules` directly via the constructor and calling its method when needed** is usually easier to test and less tied to string expressions:

```java
@Service
public class InvoiceService {

    private final TaxRules taxRules;

    public InvoiceService(TaxRules taxRules) {
        this.taxRules = taxRules;
    }

    public double calculateTax(double subtotal) {
        return subtotal * taxRules.defaultRate();
    }
}
```

If a SpEL expression calls a method on a bean during dependency creation, it can also trigger early bean initialization or expose circular dependencies. Use SpEL when there is a clear reason, not to replace standard dependency injection.

## 14. Combining placeholders and SpEL

Spring can resolve a property placeholder first and then evaluate a SpEL expression containing the substituted result.

For example:

```java
@Value("#{${app.base-limit:10} * 2}")
private int effectiveLimit;
```

If:

```properties
app.base-limit=15
```

then visualize:

```text
#{${app.base-limit:10} * 2}
          │
          ▼
Resolve app.base-limit = 15
          │
          ▼
#{15 * 2}
          │
          ▼
Evaluate SpEL
          │
          ▼
30
```

Without the property, the default `10` is substituted, and the expression `10 * 2` yields `20`.

This works well when the source value is guaranteed to be a trusted integer. If an operator enters `app.base-limit=large`, the expression becomes invalid and the bean may fail to initialize.

**Warning:** never embed untrusted strings directly into SpEL. SpEL can evaluate expressions and invoke methods; placing external input inside expression syntax can alter what gets evaluated. Treat expressions as trusted configuration code, and treat user input as data that must be validated and handled separately.

### 14.1. A SpEL pattern for null

In some cases you may write:

```java
@Value("${app.optional-label:#{null}}")
private String optionalLabel;
```

If the property does not exist, the placeholder default is the SpEL expression `#{null}`, which can yield null. However, this complicates the code compared to a standard placeholder and is incompatible with primitives such as `int` where null cannot be injected.

For configuration with multiple optional fields and constraints, a `@ConfigurationProperties` class is usually a clearer choice.

## 15. When @Value is processed

`@Value` is typically resolved when Spring creates and injects the bean. That means:

1. Spring has prepared the required property sources for the application context.
2. Dependency injection processes annotations and resolves placeholders/expressions.
3. Values are converted to the type required by the injection point.
4. The bean uses the injected value for the rest of its lifecycle.

If you edit `application.yml` after the application has started, a field injected with `@Value` **does not change automatically**. `@Value` is not a reactive subscription or configuration hot-reload mechanism.

If you need runtime configuration updates, use a dynamic configuration design or a supported refresh mechanism in your stack; consider consistency, lifecycle, and thread safety. Do not expect `@Value` to watch files and update itself.

## 16. How do @Value and @ConfigurationProperties differ?

`@Value` fits when a bean needs **a few standalone values**. When configuration is larger, structured, or needs validation, `@ConfigurationProperties` is usually better.

Suppose configuration:

```yaml
mail:
  host: smtp.example.test
  port: 587
  security:
    start-tls: true
  retry:
    max-attempts: 3
    delay: 5s
```

Approach using multiple `@Value` fields:

```java
@Value("${mail.host}")
private String host;

@Value("${mail.port:587}")
private int port;

@Value("${mail.security.start-tls:true}")
private boolean startTls;

@Value("${mail.retry.max-attempts:3}")
private int maxAttempts;
```

For a couple of fields, this works. As configuration grows, however, property names scatter across classes, group metadata is missing, and unified validation becomes awkward.

Another approach is a properties class:

```java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        String host,
        int port,
        Security security,
        Retry retry) {

    public record Security(boolean startTls) {}

    public record Retry(int maxAttempts, Duration delay) {}
}
```

This example illustrates the record structure; the `@ConfigurationProperties` class must be registered via `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or an appropriate mechanism, with the required imports. For real binding, verify property names, constructors, defaults, and validation against your Boot version.

Comparison:

| Need | @Value | @ConfigurationProperties |
|---|---|---|
| A single string or boolean | Very suitable | Can be unnecessarily heavy |
| Multiple properties sharing a prefix | Easily scattered | Grouped cleanly in one object |
| Validation `@NotBlank`, `@Min`, ... | Needs another solution | Integrates well with Bean Validation |
| Binding nested objects | Inconvenient | Well suited |
| Complex lists/maps | Hard to maintain | Better suited |
| Defaults/documented configuration | Defaults at each injection point | Centrally managed |
| SpEL expressions | Supported | Properties binder is not intended for arbitrary SpEL evaluation |

Practical guideline: **one to a few scalar values use `@Value`; a configuration group with cohesive business meaning uses `@ConfigurationProperties`**.

## 17. Property placeholders are not full collection binding

`@Value` can inject a comma-separated string:

```properties
app.allowed-regions=vn,sg,jp
```

and read it verbatim:

```java
@Value("${app.allowed-regions:vn}")
private String allowedRegions;
```

Then the application can parse it by its own convention if the list is tiny. In some contexts, Spring's conversion service can convert a String to a collection, but do not treat `@Value` as a full list/map binding mechanism with all the rules of `@ConfigurationProperties`.

With a YAML list:

```yaml
app:
  allowed-regions:
    - vn
    - sg
    - jp
```

prefer `@ConfigurationProperties` to bind into `List<String>`, especially when per-element validation or nested structures are needed.

Avoid using SpEL to manually assemble complex lists or maps when the data is actually structured configuration.

## 18. @Value on static fields and manually instantiated objects

`@Value` is processed by Spring during a bean instance's lifecycle, not by the Java compiler assigning values automatically.

Example to avoid:

```java
@Component
public class BadSettings {

    @Value("${app.mode:local}")
    private static String mode;
}
```

Static fields are not injected like instance fields under normal `@Value` processing. The result can be null or unexpected.

Similarly:

```java
public class Client {
    @Value("${app.endpoint}")
    private String endpoint;
}

Client client = new Client();
```

`client` is constructed with `new` outside the Spring container, so the annotation has no effect.

Instead of static fields, inject values into a bean's constructor and let other consumers receive that bean via DI. If static code genuinely needs configuration, redesign the boundaries to avoid global mutable state.

## 19. @Value does not replace @ConditionalOnProperty

Both annotations relate to `Environment`, yet they serve different purposes.

```java
@Value("${feature.export.enabled:false}")
private boolean exportEnabled;
```

The bean is still created, and the field merely receives the on/off flag.

Meanwhile:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "feature.export",
        name = "enabled",
        havingValue = "true")
public class ExportConfiguration {

    @Bean
    ExportClient exportClient() {
        return new ExportClient();
    }
}
```

`ExportConfiguration` is applied only when the property satisfies the condition. If it does not match, Spring does not register `exportClient` through this factory method.

Use `@Value` when the bean always exists and its behavior depends on the value. Use `@ConditionalOnProperty` when you want **bean registration itself** to depend on configuration.

Do not default to conditional configuration for every boolean: if both branches rely on the same service, checking a boolean inside the service can be simpler.

## 20. @Value and common mistakes

| Symptom | Possible cause | Solution |
|---|---|---|
| `Could not resolve placeholder` | Property does not exist and has no default | Check key, profile, and property sources; use defaults only when truly optional |
| Bean fails to create due to invalid `int` | Property contains text like `abc`, unconvertible to target type | Fix configuration data, add appropriate validation |
| Value differs from `application.yml` | A higher-precedence property source exists, e.g., command line/environment | Check `Environment` and profiles |
| Default is ignored when property is empty | Property exists with an empty string | Validate or normalize the value |
| Field stays null | Object created with `new`, class is not a bean, or static field used | Register as a bean, use constructor injection |
| `@Value("${1 + 2}")` does not add numbers | `${...}` looks up a property, does not evaluate arithmetic | Use `#{1 + 2}` |
| SpEL parse/evaluation exception | `#{...}` expression has invalid syntax or calls an invalid method | Keep expressions simple, verify bean/method names |
| Configuration does not auto-update | `@Value` is resolved during bean initialization | Use an appropriate refresh/dynamic configuration mechanism if needed |
| List/map bound incorrectly | Using scalar placeholder for nested/collection config | Use `@ConfigurationProperties` |
| Wrong bean injected when multiple beans exist | Expression references wrong bean name or bean does not exist | Prefer type/qualifier DI instead of SpEL strings |
| Secret leaked in logs | Printed full configuration or exception containing secrets | Never log secrets; use proper secret management |

### 20.1. Note on configuration errors

Do not "fix" every error by slapping on arbitrary defaults. A critical value such as a payment system URL, credentials, or mandatory output path that is missing should cause a clear startup failure rather than silently falling back to a potentially wrong endpoint.

For configuration data requiring interrelated validations, creating a configuration properties object expresses a tighter contract.

## 21. Testing injected values

A straightforward approach is `@SpringBootTest` with test-specific properties.

Bean example:

```java
@Component
public class GreetingSettings {

    private final String prefix;
    private final int times;

    public GreetingSettings(
            @Value("${greeting.prefix:Hello}") String prefix,
            @Value("${greeting.times:1}") int times) {
        this.prefix = prefix;
        this.times = times;
    }

    public String prefix() {
        return prefix;
    }

    public int times() {
        return times;
    }
}
```

Integration test:

```java
@SpringBootTest(properties = {
        "greeting.prefix=Welcome",
        "greeting.times=3"
})
class GreetingSettingsTest {

    @Autowired
    private GreetingSettings settings;

    @Test
    void injectsConfiguredValues() {
        assertEquals("Welcome", settings.prefix());
        assertEquals(3, settings.times());
    }
}
```

This test assumes Spring Boot Test, JUnit Jupiter, and corresponding imports. The goal is to prove that test properties override values and Spring converts `"3"` into `int`.

You can write a second test omitting `greeting.times` to verify the default `1`, or passing an invalid value to observe context creation failure.

### 21.1. Unit testing without a Spring context

Because `GreetingSettings` uses constructor injection, regular logic can be tested with:

```java
@Test
void createsSettingsWithoutSpring() {
    GreetingSettings settings = new GreetingSettings("Hi", 2);
    assertEquals("Hi", settings.prefix());
    assertEquals(2, settings.times());
}
```

This is a practical benefit of constructor injection: unit tests do not depend on annotation processing or a Spring application context just to instantiate the object.

## 22. Combined example: one configuration value and one expression

Suppose an application configures a base record limit, yet needs double that limit for administrative tasks.

Configuration:

```properties
reports.base-limit=100
```

Approach 1 — inject single value, compute in Java:

```java
@Service
public class ReportLimits {

    private final int baseLimit;

    public ReportLimits(
            @Value("${reports.base-limit:100}") int baseLimit) {
        this.baseLimit = baseLimit;
    }

    public int adminLimit() {
        return baseLimit * 2;
    }
}
```

Approach 2 — use SpEL to compute at injection time:

```java
@Service
public class ReportLimits {

    private final int adminLimit;

    public ReportLimits(
            @Value("#{${reports.base-limit:100} * 2}")
            int adminLimit) {
        this.adminLimit = adminLimit;
    }

    public int adminLimit() {
        return adminLimit;
    }
}
```

Both approaches illustrate the relationship between the property and the derived value. When business logic may change, needs dedicated tests, or must handle overflow/bounds, Approach 1 is usually easier to read and control. Reserve SpEL for simple expressions with a clear purpose.

Do not register both `ReportLimits` classes in the same package under the same bean name in a real application; these are two alternative versions for comparison.

## 23. Choosing between placeholders, SpEL, and config objects

Use the following table when designing:

| Need | Preferred mechanism | Reason |
|---|---|---|
| Reading application name | `@Value("${app.name}")` | Single scalar from `Environment` |
| Boolean with default | `@Value("${feature.enabled:false}")` | Clear default and type |
| Computing a simple expression only at injection | SpEL `@Value("#{2 * 5}")` | Evaluates value from expression |
| Value derived from a property | Read property then compute in Java; SpEL when truly needed | Separating logic is usually easier to test |
| Multiple related properties | `@ConfigurationProperties` | Typed object and configuration grouping |
| Nested lists/maps | `@ConfigurationProperties` | Better structured binding |
| Registering a bean only when a flag is enabled | `@ConditionalOnProperty` | Conditional bean creation |
| Changing values at runtime | Dynamic configuration mechanism | `@Value` does not auto-refresh |
| Accessing a Spring service | Constructor injection | No need for SpEL `@beanName` |
| Missing required config must fail | Placeholder without default or validated properties | Fail-fast, avoids dummy values |

## 24. Practice exercises

### Exercise A — Reading scalar values

Create properties `app.title`, `app.max-connections`, and `app.debug-enabled` in `application.yml`. Inject them via `@Value` constructor injection into a bean. Print the results using a `CommandLineRunner` or test endpoint.

### Exercise B — Testing defaults

Delete `app.max-connections` while keeping `@Value("${app.max-connections:10}")`. Observe the number 10. Next, set `app.max-connections=20` and verify the value is overridden.

### Exercise C — Distinguishing empty strings from missing properties

Set `app.title=` and try `@Value("${app.title:Untitled}")`. Compare when the key exists as empty versus when the key is completely removed. Propose validation if an empty title is unacceptable.

### Exercise D — Arithmetic SpEL

Create a field receiving `@Value("#{4 * 5}")`. Compare it with `@Value("${4 * 5}")` and explain why one expression is computed while the other searches for a property.

### Exercise E — Combining placeholders and SpEL

Test `@Value("#{${app.base-limit:10} * 2}")` with `base-limit` equal to 5, 20, and absent. Then try a non-numeric value to observe the error.

### Exercise F — Constructor injection and testing

Write a service accepting `@Value("${app.retry-count:3}")` via constructor. Write a unit test calling the constructor directly, then write an integration test with `@SpringBootTest(properties = ...)`.

### Exercise G — Migrating to @ConfigurationProperties

Start with four `@Value` fields sharing the `mail` prefix. Convert them into a properties object with a nested object and validation. Compare organization, testing, and default management.

### Exercise H — Avoiding expressions with untrusted data

Explain why you should never concatenate input from an HTTP request into a SpEL expression to evaluate it. Rewrite it to accept input as data, validate types, and process it via normal Java methods.

## 25. Principles to follow

1. **`@Value` injects a value into a Spring bean**; it does not create beans itself and has no effect on objects instantiated with `new`.
2. **`${...}` is a property placeholder**: it retrieves values from Spring `Environment`.
3. **`${key:default}`** supplies a default when the key is not found; it does not replace validation.
4. **`#{...}` is SpEL**: it evaluates an expression rather than simply looking up a property.
5. Both syntaxes can be combined, such as `#{${app.limit:10} * 2}`, provided you understand resolution order and ensure data entering the expression is trusted.
6. For scalar types like String, int, and boolean, Spring usually performs type conversion automatically.
7. **Constructor injection** is usually better than field injection because dependencies are explicit, fields can be final, and unit testing is easy.
8. `@Value` is not a mechanism for auto-updating configuration after startup.
9. **`@ConfigurationProperties`** fits better for multiple values sharing a prefix, nested objects, lists/maps, and validation.
10. **`@ConditionalOnProperty`** decides whether to register a bean; `@Value` only injects a value into a bean.
11. Do not use SpEL to execute complex business logic or evaluate expressions built from untrusted input.
12. For required and sensitive configuration, prioritize fail-fast behavior, validation, and proper secret management.

Whenever you need a configuration value, ask: **"Am I reading a property, evaluating an expression, or binding an entire configuration group?"** The answers lead respectively to a property placeholder `${...}`, SpEL `#{...}`, or a typed configuration object.
