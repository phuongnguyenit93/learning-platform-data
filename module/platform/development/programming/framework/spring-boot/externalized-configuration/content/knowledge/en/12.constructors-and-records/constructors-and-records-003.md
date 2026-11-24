# Selecting a Constructor with `@ConstructorBinding` When Multiple Constructors Exist — Spring Boot 3.3

## 1. The Problem to Solve

When using externalized configuration in Spring Boot, we often group related keys into a `@ConfigurationProperties` class and let Spring Boot bind values from `application.properties`, YAML, environment variables, or command-line arguments into a Java object.

For a class with only **one parameterized constructor**, Spring Boot 3.3 can usually infer that this constructor should be used for binding. However, when the same class has **multiple constructors**—for example, a full constructor and a convenience constructor for instantiating the object in unit tests—Spring Boot needs to know **which constructor represents the configuration data schema**.

In that case, use the annotation:

```java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
```

and place `@ConstructorBinding` **on the chosen constructor**.

This lesson explains the selection mechanism, distinguishes constructor binding from JavaBean binding and regular Dependency Injection (DI), builds a runnable example, applies it to `record`, `@DefaultValue`, nested objects, and validation, and presents common mistakes in Spring Boot 3.3.

**Scope:** Spring Boot 3.3.x, Java 17 and above. The API syntax and imports in this lesson are for Spring Boot 3.x; do not mechanically copy examples that use the annotation placement from older versions.

## 2. Understanding Constructor Binding Properly

Suppose we have the configuration:

```yaml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 4
```

An immutable configuration class:

```java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final URI baseUrl;
    private final Duration connectTimeout;
    private final int maxRetries;

    public ClientProperties(
            URI baseUrl,
            Duration connectTimeout,
            int maxRetries
    ) {
        this.baseUrl = baseUrl;
        this.connectTimeout = connectTimeout;
        this.maxRetries = maxRetries;
    }

    public URI getBaseUrl() {
        return baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
```

Required Java and Spring Boot imports:

```java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
```

When the bean is registered via the `@ConfigurationProperties` mechanism, the Spring Boot Binder uses constructor parameter names to locate the matching keys:

```text
app.client.base-url        -> baseUrl: URI
app.client.connect-timeout -> connectTimeout: Duration
app.client.max-retries     -> maxRetries: int
```

It converts the string values to the corresponding Java types and then invokes the constructor with the bound arguments.

```text
External configuration sources
          |
          v
 Spring Boot Binder
  - locates prefix app.client
  - identifies constructor parameters
  - relaxed binding of key names
  - converts URI / Duration / int types
          |
          v
new ClientProperties(baseUrl, connectTimeout, maxRetries)
          |
          v
Immutable configuration bean used by other beans
```

Key point: these parameters come from **configuration properties**, not from other beans in the Spring context. Constructor binding is **binding configuration data into an object**, not the mechanism for automatically injecting business dependencies.

## 3. Single Parameterized Constructor: No Annotation Needed

Spring Boot 3.3 has an inference rule: when a configuration type has only **one eligible parameterized constructor**, constructor binding is chosen implicitly.

Example:

```java
package example.binding;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.cache")
public final class CacheProperties {

    private final boolean enabled;
    private final int maxEntries;

    public CacheProperties(boolean enabled, int maxEntries) {
        this.enabled = enabled;
        this.maxEntries = maxEntries;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public int getMaxEntries() {
        return maxEntries;
    }
}
```

`application.properties` file:

```properties
app.cache.enabled=true
app.cache.max-entries=500
```

There is no need to add `@ConstructorBinding` to the constructor above.

**Why?** There are no other choices to cause ambiguity; the Binder has one eligible constructor to instantiate the object. Writing the annotation in this case is not wrong in intent, but it is not required.

However, the prerequisites for constructor binding must still be satisfied: the configuration type must be registered properly, parameter names must be available at compile time, and the constructor must not be marked in a way that tells Spring to skip constructor binding.

### Does Not Mean Every Constructor Is Automatically Bound

If you have:

```java
public CacheProperties() { ... }

public CacheProperties(boolean enabled, int maxEntries) { ... }
```

then the class already has **multiple constructors**. Do not assume Spring Boot automatically picks the two-parameter constructor. When you want to use the parameterized constructor, specify it explicitly with `@ConstructorBinding`.

## 4. Multiple Constructors: Mark the Binding Constructor

For example, a `ClientProperties` class has two ways to create an object:

- A full constructor used when the application loads configuration.
- A convenience constructor with just a URL, used in application code or tests.

```java
package example.binding;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public final class ClientProperties {

    private final URI baseUrl;
    private final Duration connectTimeout;
    private final int maxRetries;

    @ConstructorBinding
    public ClientProperties(
            URI baseUrl,
            @DefaultValue("3s") Duration connectTimeout,
            @DefaultValue("3") int maxRetries
    ) {
        this.baseUrl = baseUrl;
        this.connectTimeout = connectTimeout;
        this.maxRetries = maxRetries;
    }

    public ClientProperties(URI baseUrl) {
        this(baseUrl, Duration.ofSeconds(3), 3);
    }

    public URI getBaseUrl() {
        return baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
```

`application.yaml` file:

```yaml
app:
  client:
    base-url: https://api.example.test
    max-retries: 5
```

In this scenario:

1. The Binder recognizes the `ClientProperties` type.
2. It sees the **full constructor** marked with `@ConstructorBinding`.
3. It looks up values for `baseUrl`, `connectTimeout`, and `maxRetries` under `app.client`.
4. `connect-timeout` is not provided, so `@DefaultValue("3s")` supplies the value for the `Duration` parameter.
5. `max-retries=5` from YAML is converted to `int`.
6. The three-parameter constructor is invoked to create the configuration bean.

Resulting values:

```text
baseUrl        = https://api.example.test
connectTimeout = PT3S
maxRetries     = 5
```

The single-parameter constructor **is not the one the Binder picks**, though it can still be called when you explicitly write `new ClientProperties(uri)` in Java code.

### Why Is the Annotation Placed on the Constructor, Not the Class?

In Spring Boot 3.3, the `org.springframework.boot.context.properties.bind.ConstructorBinding` API has targets `CONSTRUCTOR` and `ANNOTATION_TYPE`. It serves to **designate a constructor**. Therefore:

```java
@ConfigurationProperties(prefix = "app.client")
public final class ClientProperties {
    @ConstructorBinding
    public ClientProperties(URI baseUrl, Duration timeout) {
        // ...
    }
}
```

is the correct placement in this version.

Do not use the old style:

```java
@ConstructorBinding
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    // ...
}
```

because the annotation in Spring Boot 3.3's package/targets is not intended to be placed directly on the type in that manner.

## 5. What Does Selecting One Among Multiple Constructors Avoid?

If a class has multiple constructors with the same general purpose but different parameters, such as:

```java
public ClientProperties(URI baseUrl) { ... }

public ClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxRetries
) { ... }
```

Spring Boot cannot rely on **parameter count** to guess which constructor you intended. The constructor with fewer parameters might be for tests, or it might be the one containing all needed settings. The constructor with more parameters might serve other logic and not necessarily represent the configuration structure.

`@ConstructorBinding` is an **explicit design decision**:

```text
Multiple constructors exist
        |
        v
Which constructor describes the @ConfigurationProperties data?
        |
        v
Place @ConstructorBinding on that constructor
        |
        v
Binder resolves parameters of the selected constructor
```

Advantages:

- Does not break if an IDE, Lombok, or a refactoring adds another constructor.
- Readers know which constructor reflects the configuration schema.
- No setters are needed to populate `final` fields.
- Preserves convenience constructors for unit tests or manual instantiation.
- Lets you place `@DefaultValue` on the exact parameters the Binder uses.

When adding a new constructor, **do not arbitrarily add a second `@ConstructorBinding`**. The goal is to designate a single constructor for configuration, not to declare a set of constructors for the Binder to try one by one.

## 6. Distinguishing `@ConstructorBinding` from `@Autowired`

This is the most important distinction.

### 6.1. `@ConstructorBinding` Receives Configuration Values

```java
@ConfigurationProperties(prefix = "app.report")
public final class ReportProperties {
    private final String title;
    private final int batchSize;

    @ConstructorBinding
    public ReportProperties(String title, int batchSize) {
        this.title = title;
        this.batchSize = batchSize;
    }

    public String getTitle() { return title; }
    public int getBatchSize() { return batchSize; }
}
```

The two parameters `title` and `batchSize` map to configuration keys `app.report.title` and `app.report.batch-size`.

### 6.2. `@Autowired` Is DI for Beans

```java
@Service
public class ReportService {

    private final ReportProperties settings;
    private final ReportRepository repository;

    public ReportService(
            ReportProperties settings,
            ReportRepository repository
    ) {
        this.settings = settings;
        this.repository = repository;
    }
}
```

The Spring container creates `ReportService` by injecting the `ReportProperties` **bean** and the `ReportRepository` **bean**, not by reading a property named `reportRepository` from YAML.

When there is only one constructor, Spring Framework normally uses that constructor for DI without requiring `@Autowired`. If a regular bean class has multiple constructors, the DI constructor-selection rules may require `@Autowired`; that is a separate problem from selecting a configuration-binding constructor.

### 6.3. Do Not Combine Both Annotations to "Increase Ways of Receiving Data"

Conceptually wrong:

```java
@Autowired
@ConstructorBinding
public ReportProperties(String title, int batchSize) {
    // ...
}
```

Do not put both on a single constructor hoping Spring will simultaneously look up `String` and `int` beans and read the configuration file. The two annotations express **two different object-creation mechanisms**.

Spring Boot 3.3 documentation also notes that if you want *not* to use constructor binding with a parameterized constructor, you can mark that constructor with `@Autowired` or use a `private` constructor, depending on a JavaBean binding design. However, that is not the standard approach for creating immutable configuration.

### Quick Comparison Table

| Criterion | Constructor binding | Constructor injection |
| --- | --- | --- |
| Component supplying data | Spring Boot Binder | Spring container |
| Arguments come from | Keys in `Environment` | Matching beans in the context |
| Primary declaration | `@ConfigurationProperties` + eligible constructor | `@Component`, `@Service`, `@Configuration`, ... |
| When multiple constructors exist | `@ConstructorBinding` on the chosen constructor | `@Autowired` may be used per DI rules |
| Purpose | Create a typed configuration object | Wire application components together |
| Should have `final` fields | Very well suited | Also very well suited |
| Uses `@DefaultValue` for config values | Yes | Not via the same Binder mechanism |

## 7. Do Not Add `@Component` to Constructor-Bound Types

Spring Boot 3.3 states a specific limitation: **constructor binding cannot be used with beans created through regular bean creation mechanisms** such as `@Component`, `@Bean` methods, or `@Import`.

A misleading example:

```java
@Component
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    @ConstructorBinding
    public ClientProperties(String baseUrl) {
        // ...
    }
}
```

With `@Component`, Spring tries to instantiate the object using regular bean rules rather than the specialized constructor-binding workflow for configuration properties beans. This can fail or behave unexpectedly.

**Proper registration when using constructor binding:**

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Or register explicitly:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
class ClientConfiguration {
}
```

Corresponding imports:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
```

Both mechanisms enable Spring Boot to **discover and register the configuration bean**. That bean can then be injected into services normally.

### Which Registration Style?

- `@ConfigurationPropertiesScan`: fits when an application has many custom configuration types in scanned packages.
- `@EnableConfigurationProperties(TheProperties.class)`: fits when you want to explicitly declare one or a few types, such as in a module or auto-configuration.
- `@Bean @ConfigurationProperties`: typically useful for JavaBean property binding onto a third-party library bean, **not an equivalent way to constructor-bind an immutable configuration class**.

If a project has only one configuration type, either scanning or explicit enabling works. Avoid redundant duplicate registration when a configuration is already handled by another mechanism.

## 8. Complete Example: Two Constructors, One Selected

The following example uses **Spring Boot 3.3.x**, Java 17, and the `spring-boot-starter` dependency. The package name is `example.constructorbinding`.

### 8.1. Configuration File

`src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: constructor-binding-demo

app:
  delivery:
    endpoint: https://delivery.example.test
    max-retries: 6
    connect-timeout: 2s
```

### 8.2. Class with Two Constructors

`src/main/java/example/constructorbinding/DeliveryProperties.java`:

```java
package example.constructorbinding;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.delivery")
public final class DeliveryProperties {

    private final URI endpoint;
    private final int maxRetries;
    private final Duration connectTimeout;

    @ConstructorBinding
    public DeliveryProperties(
            URI endpoint,
            @DefaultValue("3") int maxRetries,
            @DefaultValue("5s") Duration connectTimeout
    ) {
        this.endpoint = endpoint;
        this.maxRetries = maxRetries;
        this.connectTimeout = connectTimeout;
    }

    // Convenient for code/tests creating the object directly.
    public DeliveryProperties(URI endpoint) {
        this(endpoint, 3, Duration.ofSeconds(5));
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }
}
```

This is an immutable configuration class:

- All three fields are `final`.
- The three-parameter constructor is the **Binder's entry point**.
- The single-parameter constructor delegates to the full constructor via `this(...)` and **is not chosen by the Binder**.
- No setters are needed.
- `@DefaultValue` can apply if a key is absent from the evaluated configuration sources.

### 8.3. Registration and Printing Values

`src/main/java/example/constructorbinding/DemoApplication.java`:

```java
package example.constructorbinding;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showDeliveryProperties(DeliveryProperties config) {
        return args -> {
            System.out.println("endpoint=" + config.getEndpoint());
            System.out.println("maxRetries=" + config.getMaxRetries());
            System.out.println("connectTimeout=" + config.getConnectTimeout());
        };
    }
}
```

`@ConfigurationPropertiesScan` scans `@ConfigurationProperties` types within the appropriate package scope. The `showDeliveryProperties` method receives the **already-created configuration bean** rather than calling a constructor itself.

### 8.4. Running the Application

From a project using the Maven wrapper:

```bash
./mvnw spring-boot:run
```

Or run the packaged JAR (replace the placeholder name with the actual JAR name):

```bash
java -jar app.jar
```

Key output lines:

```text
endpoint=https://delivery.example.test
maxRetries=6
connectTimeout=PT2S
```

Spring Boot uses `app.delivery.endpoint`, `app.delivery.max-retries`, and `app.delivery.connect-timeout`. With these values provided, the `@DefaultValue` defaults do not need to be used.

### 8.5. Observing Defaults When Properties Are Missing

Keep only the following in YAML:

```yaml
app:
  delivery:
    endpoint: https://delivery.example.test
```

After restarting, expected output:

```text
endpoint=https://delivery.example.test
maxRetries=3
connectTimeout=PT5S
```

`maxRetries=3` comes from `@DefaultValue("3")`; `connectTimeout=PT5S` comes from `@DefaultValue("5s")`.

The key takeaway is that **the defaults reside on the parameters of the constructor chosen by the Binder**. Putting defaults only on a convenience constructor that the Binder does not use gives no guarantee those defaults will participate in binding.

### 8.6. Observing Higher-Precedence Configuration Sources

In the terminal:

```bash
java -jar app.jar --app.delivery.max-retries=9
```

Under normal precedence rules, command-line arguments override `max-retries` from YAML. The Binder still invokes **the same constructor**, but the value passed to `maxRetries` changes to `9`.

**Selecting the constructor** and **resolving the effective configuration value** are two independent concerns:

```text
Which source supplies max-retries?    --> PropertySource precedence
Which constructor receives the value? --> @ConstructorBinding
```

## 9. Records in Java 17: Usually No Annotation Needed

Records are a great fit for immutable configuration:

```java
package example.constructorbinding;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientOptions(
        URI endpoint,
        @DefaultValue("3") int retryCount,
        @DefaultValue("5s") Duration timeout
) {
}
```

With this simple record, a canonical constructor is generated from its components. If that is the only eligible constructor, Spring Boot 3.3 **does not require** `@ConstructorBinding`.

Configuration:

```properties
app.client.endpoint=https://api.example.test
app.client.retry-count=4
app.client.timeout=2s
```

Corresponding result:

```text
endpoint   = https://api.example.test
retryCount = 4
timeout    = PT2S
```

Records avoid writing `final` fields, constructors, and getters manually. However, **records are not a separate mechanism**: they are still constructor-bound by the Binder, and still require registering the configuration type via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

## 10. Records with Multiple Constructors: Explicitly Selecting the Canonical Constructor

A record can still have additional constructors. For example, needing a single-parameter constructor to instantiate test objects:

```java
package example.constructorbinding;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.remote")
public record RemoteOptions(
        URI endpoint,
        int maxRetries,
        Duration timeout
) {
    @ConstructorBinding
    public RemoteOptions(URI endpoint, int maxRetries, Duration timeout) {
        this.endpoint = endpoint;
        this.maxRetries = maxRetries;
        this.timeout = timeout;
    }

    public RemoteOptions(URI endpoint) {
        this(endpoint, 3, Duration.ofSeconds(5));
    }
}
```

In this example:

- The three-parameter constructor is the record's canonical constructor, containing all components.
- The single-parameter constructor is an auxiliary constructor.
- `@ConstructorBinding` is attached to the three-parameter constructor to clearly indicate it is the configuration constructor.
- The auxiliary constructor delegates with `this(...)` according to Java record rules.

Configuration:

```properties
app.remote.endpoint=https://remote.example.test
app.remote.max-retries=7
app.remote.timeout=4s
```

The Binder uses values from the three keys instead of picking the single-parameter convenience constructor.

A record with only the default canonical constructor is simpler; **do not add auxiliary constructors solely to pass default values**. When a default belongs to a configuration property, `@DefaultValue` usually expresses that intent more clearly.

## 11. Where Does `@DefaultValue` Go When Multiple Constructors Exist?

In Spring Boot 3.3, `@DefaultValue` is supported on **constructor parameters** and **record components**. When selecting a constructor with the annotation, defaults meant for binding should sit on that constructor's parameters.

Example:

```java
@ConfigurationProperties(prefix = "app.job")
public final class JobProperties {

    private final int concurrency;
    private final Duration pause;

    @ConstructorBinding
    public JobProperties(
            @DefaultValue("4") int concurrency,
            @DefaultValue("250ms") Duration pause
    ) {
        this.concurrency = concurrency;
        this.pause = pause;
    }

    public JobProperties() {
        this(4, Duration.ofMillis(250));
    }

    public int getConcurrency() { return concurrency; }
    public Duration getPause() { return pause; }
}
```

Configuration:

```yaml
app:
  job:
    concurrency: 8
```

Expected values after binding:

```text
concurrency = 8
pause       = PT0.25S
```

Although a no-args constructor exists, the Binder is instructed to choose the two-parameter constructor. The no-args constructor is merely another Java constructor.

### 11.1. Defaults Are Not Validation

`@DefaultValue("4")` does not stop a configuration source from supplying `-10` for `concurrency`. If a value is present yet violates business rules, validation is needed.

Likewise, constructor binding does not automatically guarantee a reference value like `URI endpoint` is always supplied. When data is missing, reference parameters can be `null` if there is no default or validation. Declare required constraints instead of treating every constructor parameter as automatically required.

### 11.2. Do Not Confuse Convenience Constructors with Binder Defaults

These lines:

```java
public JobProperties() {
    this(4, Duration.ofMillis(250));
}
```

are defaults **when Java code calls `new JobProperties()`**.

Whereas:

```java
@DefaultValue("4") int concurrency
```

is the default **when the Spring Boot Binder binds the constructor parameter** and no source supplies a matching value.

Both styles may produce the same number in an example, but **where the value originates and when it applies are different**.

## 12. Nested Objects Are Also Constructor-Bound

With a grouped configuration:

```yaml
app:
  service:
    endpoint: https://service.example.test
    retry:
      max-attempts: 4
      backoff: 250ms
```

We can use a class containing a nested record:

```java
package example.constructorbinding;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.service")
public final class ServiceProperties {

    private final URI endpoint;
    private final Retry retry;

    @ConstructorBinding
    public ServiceProperties(URI endpoint, Retry retry) {
        this.endpoint = endpoint;
        this.retry = retry;
    }

    public ServiceProperties(URI endpoint) {
        this(endpoint, new Retry(3, Duration.ofMillis(500)));
    }

    public URI getEndpoint() { return endpoint; }
    public Retry getRetry() { return retry; }

    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("500ms") Duration backoff
    ) {
    }
}
```

The Binder will bind:

```text
app.service.endpoint           -> ServiceProperties.endpoint
app.service.retry.max-attempts -> Retry.maxAttempts
app.service.retry.backoff      -> Retry.backoff
```

`Retry` is also constructor-bound based on the nested record structure. It is **not mandatory** to write `@ConstructorBinding` on each nested record when it only has a single valid constructor.

### 12.1. What If the Entire Nested Group Is Missing?

If no keys exist under `app.service.retry`, the nested `retry` object may not be created, even if the `Retry` record has `@DefaultValue` on its fields. If you still want a nested object created so child defaults apply, Spring Boot supports an **empty** `@DefaultValue` on the nested parameter:

```java
@ConstructorBinding
public ServiceProperties(
        URI endpoint,
        @DefaultValue Retry retry
) {
    this.endpoint = endpoint;
    this.retry = retry;
}
```

In this case, the Binder is instructed to bind the nested object even without child keys, allowing defaults inside `Retry` to take effect.

Distinguish between:

```text
No app.service.retry.* + no @DefaultValue on nested parameter
    -> nested object can be null

No app.service.retry.* + empty @DefaultValue on nested parameter
    -> Binder can construct nested object from child defaults
```

Do not use an empty `@DefaultValue` to hide missing required errors. If `retry` configuration must genuinely be provided, use validation or an appropriate check.

## 13. Parameter-Name Metadata: `-parameters` Is Needed

The Binder must know which constructor parameter corresponds to which configuration key. For a regular Java class:

```java
public ClientProperties(URI baseUrl, int maxRetries) {
    // ...
}
```

Parameter names `baseUrl` and `maxRetries` must be preserved in metadata at compile time. Spring Boot 3.3 requires classes with constructor binding to be compiled with the option:

```text
-parameters
```

This option causes the Java compiler to preserve parameter names for reflection/the Binder to use.

According to Spring Boot documentation, builds using the **Spring Boot Gradle plugin** or **Maven with `spring-boot-starter-parent`** typically configure this automatically.

If a project uses a custom build setup, ensure the Java compiler plugin enables the appropriate flag.

Maven Compiler Plugin example:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Gradle Groovy DSL example when configuring directly:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

Without parameter-name metadata, Spring Boot may fail to determine the exact key name to bind and raise a binding error. This error **is not caused by missing `@ConstructorBinding`**: the annotation selects the constructor, whereas `-parameters` identifies the parameter names on that constructor.

### 13.1. Difference from Field Names

If a constructor accepts:

```java
public ClientProperties(int retries) {
    this.maxRetries = retries;
}
```

then the parameter name is `retries`, not `maxRetries`. The Binder primarily relies on the parameter names of the chosen constructor; do not assume it will arbitrarily infer them from fields assigned inside the body.

Prefer keeping parameter names consistent with the configuration data being bound:

```java
public ClientProperties(int maxRetries) {
    this.maxRetries = maxRetries;
}
```

When a name must differ due to a Java keyword or special case, Spring Boot also offers the `@Name` annotation on constructor parameters, such as binding a key named `import`, which is a Java keyword.

## 14. `@Name`: When a Configuration Key Cannot Be a Java Parameter Name

Suppose configuration uses the key:

```properties
app.resources.import=https://source.example.test
```

`import` is a Java keyword, so you cannot write:

```java
public ResourceProperties(String import) { ... }
```

Spring Boot provides `@Name` in the `org.springframework.boot.context.properties.bind` package:

```java
package example.constructorbinding;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.Name;

@ConfigurationProperties(prefix = "app.resources")
public final class ResourceProperties {

    private final String importLocation;

    @ConstructorBinding
    public ResourceProperties(@Name("import") String importLocation) {
        this.importLocation = importLocation;
    }

    public ResourceProperties() {
        this.importLocation = "";
    }

    public String getImportLocation() {
        return importLocation;
    }
}
```

`@Name("import")` specifies the configuration name to use for the constructor parameter. Because the class has two constructors, `@ConstructorBinding` selects the constructor accepting `importLocation`.

This is a specialized case; in most projects, choose clear key and parameter names without needing `@Name`.

## 15. Validation When Using Constructor Binding

Immutability does not mean **valid values**. If data contains `max-retries=-10` or omits an endpoint, an immutable object can still hold an undesired state if no constraints are applied.

With the `spring-boot-starter-validation` dependency, you can combine:

```java
package example.constructorbinding;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public final class DeliveryProperties {

    @NotNull
    private final URI endpoint;

    @Min(0)
    private final int maxRetries;

    @NotNull
    private final Duration connectTimeout;

    @ConstructorBinding
    public DeliveryProperties(
            URI endpoint,
            @DefaultValue("3") int maxRetries,
            @DefaultValue("5s") Duration connectTimeout
    ) {
        this.endpoint = endpoint;
        this.maxRetries = maxRetries;
        this.connectTimeout = connectTimeout;
    }

    public DeliveryProperties(URI endpoint) {
        this(endpoint, 3, Duration.ofSeconds(5));
    }

    public URI getEndpoint() { return endpoint; }
    public int getMaxRetries() { return maxRetries; }
    public Duration getConnectTimeout() { return connectTimeout; }
}
```

`@NotNull` and `@Min` describe data constraints, and `@Validated` asks Spring Boot to apply validation to the configuration properties.

When data is invalid, failure can happen right at the binding/validation phase instead of when a business bean calls an API with a null endpoint or negative retry count.

### Validation with Nested Objects

If nested configuration has constraints, consider `@Valid` on the nested reference point and annotations on child fields so validation cascades inward. Do not assume child objects are always fully validated just because the parent class has `@Validated`.

### Defaults and Validation Are Two Different Things

- `@DefaultValue("3")` handles **missing values**.
- `@Min(0)` handles **numeric values outside the allowed domain**.
- `@NotNull` handles **missing reference values**.

Use the appropriate mechanisms for your actual requirements rather than using a convenience constructor to mask missing required configuration.

## 16. JavaBean Binding Differs from Constructor Binding

Spring Boot supports binding via JavaBean getters/setters:

```java
@ConfigurationProperties(prefix = "app.cache")
public class MutableCacheProperties {
    private boolean enabled;
    private int maxEntries;

    public MutableCacheProperties() {
    }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }

    public int getMaxEntries() { return maxEntries; }
    public void setMaxEntries(int maxEntries) {
        this.maxEntries = maxEntries;
    }
}
```

This model:

1. Instantiates the object (usually via a no-args constructor).
2. Binder locates setters/property descriptors.
3. Binder writes values into mutable properties.

The constructor binding model:

1. Binder reads data and performs type conversion.
2. Binder invokes the chosen constructor.
3. The object is created with complete values through the constructor.
4. Fields can be `final`, with no setters needed.

| Aspect | JavaBean binding | Constructor binding |
| --- | --- | --- |
| How values are supplied | Setters or suitable mutable structures | Constructor parameters |
| State after creation | Usually mutable | Easy to design as immutable |
| No-args constructor | Commonly used | Not required |
| Multiple constructors | Bean creation can be configured | Should be selected via `@ConstructorBinding` |
| `@DefaultValue` on parameters | Not the primary tool | Very well suited |
| `final` fields | Awkward for regular setters | Very well suited |
| Registration via scan or enable | Supported | Required for constructor binding |

No single style is always superior. A new, strongly typed configuration object that needs immutability usually fits constructor binding. An older library with JavaBean setters may fit JavaBean binding.

The critical point when **a class has multiple constructors** is leaving no ambiguity about which binding mode is actually in effect.

## 17. Lombok and Auto-Generated Constructors

Lombok can generate constructors based on fields:

```java
@RequiredArgsConstructor
public class ClientProperties {
    private final URI endpoint;
    private final int retries;
}
```

When the same class also includes `@NoArgsConstructor`, `@AllArgsConstructor`, manual constructors, or other annotations, the actual number of constructors may differ from what someone expects by reading only the fields.

Consequences can include:

- The class has multiple constructors without designating the one for the Binder.
- Lombok generates a constructor with the same signature as a manual one, causing a compilation error.
- Parameter-name metadata is not retained if the build configuration is misconfigured.
- Default/validation annotations are not placed where the Binder inspects them.

For a `@ConfigurationProperties` class with multiple constructors, the clearest approach is usually **explicitly writing the selected constructor**:

```java
@ConstructorBinding
public ClientProperties(URI endpoint, int retries) {
    this.endpoint = endpoint;
    this.retries = retries;
}
```

You can still use Lombok to generate getters if the project prefers, but avoid letting configuration classes depend on generated constructors without controlling their semantics.

Records often provide cleaner immutable configuration than Lombok in Java 17, especially when no extra constructors are needed.

## 18. Edge Cases to Think Through Carefully

### 18.1. Two Constructors with the Same Parameter Count

Example:

```java
public TimeoutProperties(Duration timeout, int attempts) { ... }
public TimeoutProperties(int attempts, Duration timeout) { ... }
```

Two constructors have the same parameter count in a different order. The Binder should not have to guess from parameter counts or field order; mark the exact constructor that describes the configuration schema.

### 18.2. Keeping a Single-Parameter Legacy Constructor During Migration

A class might keep an older constructor:

```java
public ConnectorProperties(String url) {
    this(URI.create(url), Duration.ofSeconds(5));
}
```

alongside a new constructor:

```java
@ConstructorBinding
public ConnectorProperties(URI endpoint, Duration timeout) {
    // ...
}
```

Keeping the legacy constructor for Java API compatibility does not cause the Binder to prefer it. Conversely, the default values applied by the legacy constructor do not replace `@DefaultValue` on the new constructor.

### 18.3. Adding an Auxiliary Constructor for Unit Tests

If tests want convenient instantiation:

```java
new ConnectorProperties(URI.create("https://test.example"));
```

that is a reason a convenience constructor might exist. Still, avoid adding auxiliary constructors solely for tests if a record or test builder is clear enough. Each extra constructor increases the need to keep constructor selection explicit.

### 18.4. `@ConstructorBinding` on Nested Helper Types

For nested structures that have multiple constructors, the nested type also needs a way to identify the right constructor. A single constructor on a nested record usually needs no annotation; if a nested class has multiple constructors and uses constructor binding, designate it at the appropriate level rather than annotating only the parent class and expecting child classes to guess correctly.

### 18.5. `Optional` in Configuration Properties

Spring Boot documentation discourages using `Optional` as a `@ConfigurationProperties` property type, as `Optional` is primarily designed as a return type. Choose suitable types, defaults, or validation as needed instead of wrapping every constructor parameter in `Optional`.

### 18.6. A Configuration Class Should Not Inject Business Beans

Architectural mistake:

```java
@ConfigurationProperties(prefix = "app.worker")
public WorkerProperties(TaskRepository repository, int batchSize) {
    // ...
}
```

During constructor binding, the Binder searches for configuration properties for `repository` and `batchSize`; it does not automatically resolve a `TaskRepository` bean for one parameter while binding `batchSize` from properties in a hybrid DI mode.

If a repository is needed, have `WorkerService` accept `TaskRepository` and `WorkerProperties` as **two separate beans**:

```java
@Service
public class WorkerService {
    public WorkerService(
            TaskRepository repository,
            WorkerProperties settings
    ) {
        // ...
    }
}
```

`WorkerProperties` describes only configuration data; `WorkerService` coordinates dependencies.

## 19. Common Errors and How to Handle Them

| Symptom | Possible Cause | Solution |
| --- | --- | --- |
| IDE says `@ConstructorBinding` cannot be placed on a class | Using annotation placement from an older version | In Spring Boot 3.3, place the annotation on the **constructor** |
| IDE cannot resolve `ConstructorBinding` | Wrong package imported | Use `org.springframework.boot.context.properties.bind.ConstructorBinding` |
| Class has multiple constructors and Binder picks the wrong one | Missing constructor designation | Place `@ConstructorBinding` on the configuration constructor |
| Added `@Component` and constructor binding stopped working | Bean created via regular DI mechanism | Use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Error saying constructor parameter names are unknown | Missing `-parameters` metadata | Enable the compiler flag / use appropriate Boot build configuration |
| Missing key still yields `null` | Constructor binding does not treat every reference parameter as required | Add `@NotNull` and validation or a suitable default |
| Missing nested object | Entire nested group has no data | Use an empty `@DefaultValue` on the nested parameter if appropriate |
| Field has a default, yet binding produces unexpected values | Default was put in another constructor or field initializer | Place `@DefaultValue` on the chosen constructor's parameters |
| `@Autowired` confused with `@ConstructorBinding` | Confusing DI and Binder | Separate configuration types from services |
| Adding Lombok generated extra constructors and broke binding | Actual constructor count differs from expected | Write the binding constructor explicitly and control code-gen annotations |
| YAML value differs from object value | Higher-precedence source or different active profile | Check `PropertySource` and active profiles |
| Invalid configuration value still creates object | No validation constraints defined | Add `@Validated` and constraints |
| Record has auxiliary constructor and selection is unclear | Canonical constructor not designated | Mark the matching canonical constructor with `@ConstructorBinding` |
| No `ClientProperties` bean found | Configuration properties not registered | Add scan or enable for the right package |

### Do Not Automatically Blame the Annotation

If the application fails to bind `Duration` because the value is `abc`, adding `@ConstructorBinding` will not make that string a valid duration. Similarly, a misspelled key or an inactive profile is a **source data** issue, not a constructor-selection bug.

When troubleshooting, categorize root causes into four groups:

```text
1. Bean type / registration: scan, enable, @Component?
2. Selected constructor: one or many? @ConstructorBinding present?
3. Source data: right key, right profile, right precedence?
4. Data type / validation: conversion succeeds, constraints satisfied?
```

## 20. Inspecting the Configuration Bean After Binding

To inspect results with sample data, create an `ApplicationRunner`:

```java
@Bean
ApplicationRunner inspect(DeliveryProperties properties) {
    return args -> {
        System.out.println("endpoint=" + properties.getEndpoint());
        System.out.println("maxRetries=" + properties.getMaxRetries());
        System.out.println("connectTimeout="
                + properties.getConnectTimeout());
    };
}
```

This method must be placed **inside a suitable `@Configuration` or `@SpringBootApplication` class**, not as a standalone Java file with just the method.

Once the application creates the bean, you can compare actual values against YAML or environment variables. To inspect config data loading:

```bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
```

Enable verbose logging only temporarily in appropriate environments. Never print secret keys, passwords, or real tokens; this technique is for observing non-sensitive configuration data.

Using `Environment#getProperty` helps distinguish raw source values from bean data. Example:

```java
@Bean
ApplicationRunner inspectEnvironment(Environment env) {
    return args -> System.out.println(
            "app.delivery.max-retries="
                    + env.getProperty("app.delivery.max-retries")
    );
}
```

If `Environment` returns the expected value yet the bean is not created, check registration, constructors, type conversion, and validation. If `Environment` returns an unexpected value, check profiles, environment variables, arguments, and source precedence.

## 21. Reinforcement Exercises

### Exercise 1 — Single Constructor

```java
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int size;

    public CacheProperties(int size) {
        this.size = size;
    }

    public int getSize() { return size; }
}
```

**Question:** Is `@ConstructorBinding` required in Spring Boot 3.3?

**Answer:** Usually no. A single parameterized constructor allows Spring Boot to infer constructor binding, provided the class is registered properly and parameter-name metadata is available.

### Exercise 2 — Adding a Convenience Constructor

```java
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int size;

    public CacheProperties(int size) {
        this.size = size;
    }

    public CacheProperties() {
        this(100);
    }

    public int getSize() { return size; }
}
```

**Question:** If you want the Binder to use the constructor accepting `size`, what should you do?

**Answer:** Annotate `CacheProperties(int size)` with `@ConstructorBinding` from the Spring Boot 3.3 package. The empty constructor is merely a Java convenience option.

### Exercise 3 — Annotation Import

Given two choices:

```java
import org.springframework.boot.context.properties.ConstructorBinding;
```

```java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
```

**Question:** Which choice fits Spring Boot 3.3?

**Answer:** Use the `.bind.ConstructorBinding` package (the second option) and place the annotation on the constructor, not on the class.

### Exercise 4 — Constructor Binding and DI

```java
@ConfigurationProperties(prefix = "app.service")
public class ServiceProperties {
    @ConstructorBinding
    public ServiceProperties(ServiceRepository repository, int poolSize) {
        // ...
    }
}
```

**Question:** Why is this design questionable?

**Answer:** The Binder does not automatically fetch a `ServiceRepository` bean from the Spring context like constructor injection in a `@Service`. `@ConfigurationProperties` should focus on configuration values. Move the repository out of the configuration type and inject it into a business bean.

### Exercise 5 — Record with Auxiliary Constructor

```java
@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(String host, int port) {
    public RemoteProperties(String host) {
        this(host, 8080);
    }
}
```

**Question:** What should you do when you want to make clear which constructor is used for binding?

**Answer:** Annotate the canonical constructor accepting `host` and `port` with `@ConstructorBinding`, not the single-parameter convenience constructor.

### Exercise 6 — Defaults and Validation

A configuration has `max-retries=-5`, while the chosen constructor puts `@DefaultValue("3")` on the parameter. Will the Binder automatically replace `-5` with `3`?

**Answer:** No. `@DefaultValue` handles **missing values**, not existing values that violate rules. If `maxRetries >= 0` is required, add validation such as `@Min(0)`.

### Exercise 7 — Missing Nested Group

A parent class has parameter `Retry retry`, while configuration has no `app.service.retry.*`. To have the Binder instantiate the nested record so inner defaults take effect, what can be used?

**Answer:** An empty `@DefaultValue` on the `Retry retry` parameter of the chosen constructor, combined with defaults on the child record.

### Exercise 8 — Missing Parameter Names

You annotated the right constructor and registered `@ConfigurationPropertiesScan`, yet the Binder reports it cannot find constructor parameter names. Which annotation is missing?

**Answer:** Probably **no annotation is missing**. Check the `-parameters` compiler option and verify parameter-name metadata is preserved in bytecode.

## 22. Recommended Conventions for Spring Boot 3.3 Projects

1. **Prefer a single clear constructor.** For new configuration types, use one immutable constructor or a simple record whenever possible.
2. **Only use `@ConstructorBinding` when explicit selection is needed**, typically when multiple constructors exist.
3. **Place the annotation on the constructor and import from `.bind`.** Do not copy Spring Boot 2.x imports or class-level placement.
4. **Register configuration types with scan or enable.** Avoid turning constructor-bound config into a `@Component`.
5. **Keep constructor parameters aligned with the configuration schema.** Parameter names carry binding meaning.
6. **Ensure the compiler retains parameter names (`-parameters`).**
7. **Place `@DefaultValue` on the constructor chosen by the Binder** when default values are needed.
8. **Use validation for validity checks**, rather than assuming constructors or defaults validate constraints.
9. **Keep configuration separate from business dependencies.** Do not try to use constructor binding to inject repositories or services.
10. **Avoid unnecessary auxiliary constructors**, especially when a record or one full constructor already meets requirements.
11. **Inspect effective configuration sources** before concluding an error lies in the constructor.
12. **Treat auxiliary public constructors as part of the maintained Java API**, avoiding ambiguity during refactoring.

## 23. Summary

Keep the decision flow in mind as follows:

```text
Does the type have @ConfigurationProperties?
               |
               v
Is it registered via scan / enable?
               |
               v
Does it have a single eligible parameterized constructor?
          /                  \
         Yes                 No; multiple constructors
          |                          |
          v                          v
Implicit binding             Select the right constructor
is usually enough            with @ConstructorBinding
          \                          /
           \                        /
            v                      v
               Spring Boot Binder
                        |
                        v
            Reads and converts values from
                 configuration sources
                        |
                        v
             Creates typed configuration bean
                        |
                        v
                Other beans use via DI
```

**Single parameterized constructor:** usually does not need `@ConstructorBinding`.

**Multiple constructors:** place `@ConstructorBinding` on the constructor the Binder should call.

**Record with auxiliary constructors:** can explicitly select the canonical constructor with `@ConstructorBinding`.

**Missing values:** consider `@DefaultValue`; **invalid values:** use validation; **missing parameter names:** check `-parameters`; **bean not created:** check `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

In Spring Boot 3.3, `@ConstructorBinding` is a tool to **designate which constructor is used to bind configuration data**, not an alternative to `@Autowired`. Properly distinguishing the two mechanisms helps you write immutable, clear configuration that stays bug-free as configuration classes grow.

## References

- Spring Boot 3.3 Reference — Externalized Configuration, *Constructor Binding* section: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — *Enabling @ConfigurationProperties-annotated Types*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 API — `ConstructorBinding`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/ConstructorBinding.html
- Spring Boot 3.3 Reference — `@ConfigurationProperties` Validation and Default Values: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
