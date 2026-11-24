# Constructor Binding and Immutable Configuration Design

## 1. Goal and Context

A Spring Boot application typically has many values that need to change across environments: external service addresses, timeouts, retry counts, threshold limits, connection details, and feature toggles. Instead of reading individual configuration strings across multiple business classes, we can group related keys into a **strongly typed configuration object**.

Spring Boot provides `@ConfigurationProperties` to bind a group of external properties to the properties of a Java object. There are two familiar design approaches:

- **JavaBean binding:** creates the object, then assigns values via setters or mutable properties.
- **Constructor binding:** provides values to the constructor parameters at the moment the object is created.

This lesson focuses on **constructor binding** and how to use it to design **immutable configuration**, including `final` Java classes, `final` fields, and Java `record`s.

A configuration example:

```yaml
# src/main/resources/application.yml
checkout:
  endpoint: "https://api.example.invalid"
  connection-timeout: 3s
  max-attempts: 4
  enabled: true
```

Instead of having four separate `@Value` annotations in a business class, we can use:

```java
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        URI endpoint,
        Duration connectionTimeout,
        int maxAttempts,
        boolean enabled) {
}
```

Spring Boot reads the keys under the `checkout` prefix, performs type conversion, and invokes the `CheckoutProperties` constructor to create the object. Other components simply inject `CheckoutProperties` via dependency injection.

**Core idea:** configuration should be fully provided when the object is formed, rather than creating an "empty shell" and mutating its fields afterward.

## 2. What Problem Does Constructor Binding Solve?

Consider the JavaBean binding approach:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public class MutableCheckoutProperties {

    private String endpoint;
    private int maxAttempts;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
```

The object above can be instantiated without values and then modified via setters. While this is not necessarily wrong, it has several drawbacks:

1. Incomplete state can exist during the object creation phase.
2. Other application code might accidentally call a setter and mutate values after the application is already running.
3. It is harder to clearly express which properties are required for the constructor.
4. A large group of settings becomes a collection of reassignable fields.

With constructor binding, the design looks like this:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public final class CheckoutProperties {

    private final String endpoint;
    private final int maxAttempts;

    public CheckoutProperties(String endpoint, int maxAttempts) {
        this.endpoint = endpoint;
        this.maxAttempts = maxAttempts;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }
}
```

When Spring Boot creates this object from configuration sources:

- Values are resolved and converted **before calling the constructor**.
- The constructor receives all required values.
- `final` fields are assigned only at initialization time.
- No setters are needed for Spring Boot to bind values.

This approach is especially suitable when configuration is treated as **fixed input state throughout the lifecycle of a bean**.

## 3. Conditions for Constructor Binding to Work

In Spring Boot 3.x, a class annotated with `@ConfigurationProperties` that has **a single suitable parameterized constructor** is normally used with constructor binding without needing `@ConstructorBinding`.

Example:

```java
@ConfigurationProperties(prefix = "checkout")
public final class CheckoutProperties {

    private final String endpoint;
    private final int maxAttempts;

    public CheckoutProperties(String endpoint, int maxAttempts) {
        this.endpoint = endpoint;
        this.maxAttempts = maxAttempts;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }
}
```

An important requirement is that **the configuration bean must be registered through a mechanism dedicated to `@ConfigurationProperties`**, such as:

- `@ConfigurationPropertiesScan`;
- `@EnableConfigurationProperties(CheckoutProperties.class)`.

You should not create a regular `@Component` class and expect `@ConfigurationProperties` constructor binding to automatically replace Spring's autowiring mechanism. Beans created via `@Component`, regular `@Bean` methods, or `@Import` belong to a different bean registration mechanism; constructor binding does not apply to them in the same way.

Constructor binding and **constructor-based dependency injection** are not the same concept:

- Constructor binding for `@ConfigurationProperties`: parameters come from **configuration values** processed by the binder.
- Constructor injection for `@Service`, `@Component`: parameters are primarily **dependencies/beans** resolved by the Spring container.

The two mechanisms are often used in sequence: the binder creates the `CheckoutProperties` bean, and then Spring injects that bean into the service.

## 4. Step 1: Create the Configuration File

Suppose we are building an order confirmation service. Place the following in `src/main/resources/application.yml`:

```yaml
checkout:
  endpoint: "https://checkout.example.invalid"
  connection-timeout: 5s
  max-attempts: 3
  enabled: true
```

The configuration contains four keys:

| YAML Key | Meaning | Desired Java Type |
| --- | --- | --- |
| `checkout.endpoint` | Service address | `URI` |
| `checkout.connection-timeout` | Connection timeout | `Duration` |
| `checkout.max-attempts` | Number of attempts allowed | `int` |
| `checkout.enabled` | Enable/disable feature | `boolean` |

Spring Boot provides type converters for many common types such as `String`, integers, booleans, `Duration`, `DataSize`, `URI`, and several related types. This avoids having to manually parse configuration strings in multiple places.

The address used in the example is an illustrative address, not a real server to contact when running the program.

## 5. Step 2: Write an Immutable Configuration Class Using a Constructor

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public final class CheckoutProperties {

    private final URI endpoint;
    private final Duration connectionTimeout;
    private final int maxAttempts;
    private final boolean enabled;

    public CheckoutProperties(
            URI endpoint,
            Duration connectionTimeout,
            int maxAttempts,
            boolean enabled) {
        this.endpoint = endpoint;
        this.connectionTimeout = connectionTimeout;
        this.maxAttempts = maxAttempts;
        this.enabled = enabled;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public Duration getConnectionTimeout() {
        return connectionTimeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
```

Here:

1. `@ConfigurationProperties(prefix = "checkout")` scopes the group of properties to be bound.
2. The parameter name `connectionTimeout` maps to the `connection-timeout` key thanks to **relaxed binding**.
3. Parameters are converted by the binder to their corresponding Java types before calling the constructor.
4. All fields are `private final` and have no setters.
5. Once the object is created, business code can only read these values through getters.

In Spring Boot 3.x, the single constructor above is sufficient to trigger constructor binding under the standard rules.

For configuration classes using constructor binding, **constructor parameter names** need to be retained in bytecode so the binder knows which configuration key each parameter corresponds to. When building with the Spring Boot Gradle plugin or Maven plugin with the appropriate configuration, the Java compiler option `-parameters` is typically enabled. If a project has a custom build pipeline, check this option rather than ignoring it if parameter-name errors occur.

## 6. Step 3: Register ConfigurationProperties with Spring Boot

Simply declaring the annotation on a class is not enough if the application has no mechanism to discover and register that class.

### 6.1. Using @ConfigurationPropertiesScan

In the main application class:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Spring Boot scans for `@ConfigurationProperties` types within the appropriate packages and registers them as beans. For the example to work, place `CheckoutProperties` in the same package or a subpackage within the scan scope.

If you place the class in a package outside the default scan area, you can explicitly configure `@ConfigurationPropertiesScan(basePackages = "...")`.

### 6.2. Using @EnableConfigurationProperties

Instead of scanning, you can explicitly register the type to bind:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(CheckoutProperties.class)
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

This approach is suitable when there are few configuration classes or when you want to explicitly declare which configuration types to enable.

**Choose just one appropriate registration mechanism** for the example. Do not annotate the constructor-bound `CheckoutProperties` class with `@Component`.

## 7. Step 4: Inject the Configuration Object into a Service

Once the `CheckoutProperties` bean is created, services can use regular dependency injection.

```java
package com.example.configdemo;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final CheckoutProperties properties;

    public CheckoutService(CheckoutProperties properties) {
        this.properties = properties;
    }

    public String describe() {
        return "endpoint=" + properties.getEndpoint()
                + ", timeout=" + properties.getConnectionTimeout()
                + ", maxAttempts=" + properties.getMaxAttempts()
                + ", enabled=" + properties.isEnabled();
    }
}
```

This is **constructor injection of the configuration bean into the service**. Note the sequence:

```text
application.yml / environment variables / CLI arguments
                 |
                 v
        ConfigurationProperties Binder
                 |
                 | creates object via constructor
                 v
          CheckoutProperties bean
                 |
                 | Spring dependency injection
                 v
             CheckoutService
```

A component that runs at startup:

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class CheckoutPrinter implements ApplicationRunner {

    private final CheckoutService service;

    public CheckoutPrinter(CheckoutService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(service.describe());
    }
}
```

Illustrative output when no other configuration source overrides it:

```text
endpoint=https://checkout.example.invalid, timeout=PT5S, maxAttempts=3, enabled=true
```

`Duration#toString()` represents 5 seconds in ISO-8601 format as `PT5S`. The actual value in Java is still a `Duration`, not the string `"5s"`.

## 8. Using Records to Simplify Immutable Design

A Java `record` is well suited for data-only configuration objects. A record automatically generates the canonical constructor, accessors, `equals`, `hashCode`, and `toString`.

With Java 17 and Spring Boot 3.x, the class in the example above can be shortened to:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        URI endpoint,
        Duration connectionTimeout,
        int maxAttempts,
        boolean enabled) {
}
```

If this type is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, Spring Boot can bind the properties using the record's canonical constructor.

Access record values through their accessors:

```java
properties.endpoint();
properties.connectionTimeout();
properties.maxAttempts();
properties.enabled();
```

Note that a record **does not generate** getter methods following the `getEndpoint()` convention. When migrating from a class to a record, calling code must switch to the appropriate accessors.

Corresponding service example:

```java
@Service
public class CheckoutService {

    private final CheckoutProperties properties;

    public CheckoutService(CheckoutProperties properties) {
        this.properties = properties;
    }

    public boolean canCheckout() {
        return properties.enabled() && properties.maxAttempts() > 0;
    }
}
```

A record is a clean choice when configuration data has a clear structure, components are immutable types or protected against modification, and there is no need to inherit from another Java class.

## 9. How Immutable Is It?

**`final` fields or records alone are not enough to guarantee deep immutability.**

Record example:

```java
public record AccessProperties(List<String> allowedOrigins) {
}
```

Even though the record's `allowedOrigins` reference field cannot be reassigned, **the list it points to can still be mutated** if it is a mutable `ArrayList` and someone holds a reference to it.

To make the configuration object more stable, you can make a defensive copy:

```java
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "access")
public record AccessProperties(List<String> allowedOrigins) {

    public AccessProperties {
        allowedOrigins = allowedOrigins == null
                ? List.of()
                : List.copyOf(allowedOrigins);
    }
}
```

This is a **compact canonical constructor** of a record. Java allows normalizing parameters before the record components are assigned.

`List.copyOf` creates a list that cannot be modified through standard APIs and does not share the caller's mutable list. When the element type is `String`, this is a simple design to improve immutability. If the inner elements are mutable objects, you still need to consider the immutability of each individual element.

Similarly, for `Map`, you can consider `Map.copyOf`. These methods do not accept `null` elements or values; choose a clear configuration contract before applying them.

## 10. Default Values with @DefaultValue

An immutable configuration often raises the question: if a key is absent from the configuration sources, what will the constructor receive?

Spring Boot provides `@DefaultValue` for constructor binding parameters or record components to supply fallback values during the binding step.

Example:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        @DefaultValue("https://checkout.example.invalid") String endpoint,
        @DefaultValue("5s") Duration connectionTimeout,
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("true") boolean enabled) {
}
```

If a key is missing from the evaluated sources and the binder uses the default value, it converts the string in `@DefaultValue` to the corresponding Java type.

For example, if `application.yml` only contains:

```yaml
checkout:
  endpoint: "https://checkout.internal.invalid"
```

then the expected values are:

```text
endpoint          = https://checkout.internal.invalid
connectionTimeout = PT5S
maxAttempts       = 3
enabled           = true
```

Distinguish between:

- **Configuration-level defaults:** writing keys in a shared `application.yml` so all environments see them.
- **Binder-level defaults:** using `@DefaultValue` when a value is not present in the sources the binder is binding from.
- **Business-code defaults:** branching manually during processing; sometimes necessary, though it can easily scatter configuration rules.

For configuration used by operators, important default values should generally be documented in the application's documentation.

### 10.1. Distinguishing a Missing Value from an Empty Value

An undeclared value is different from a value that is declared as empty:

```properties
checkout.endpoint=
```

When an empty value is already present, do not assume `@DefaultValue` will always substitute the default string. The outcome depends on the configuration source, target type, and conversion rules. For required fields such as a URL, use validation to catch invalid data.

## 11. Nested Configuration and Constructor Binding

A real-world application may have multiple levels:

```yaml
checkout:
  endpoint: "https://checkout.example.invalid"
  retry:
    attempts: 4
    delay: 2s
```

With nested records:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        String endpoint,
        Retry retry) {

    public record Retry(
            int attempts,
            Duration delay) {
    }
}
```

Binding mapping:

```text
checkout.endpoint         -> CheckoutProperties.endpoint
checkout.retry.attempts   -> CheckoutProperties.Retry.attempts
checkout.retry.delay      -> CheckoutProperties.Retry.delay
```

Spring Boot can create `Retry` using its constructor, then pass the `Retry` object into the `CheckoutProperties` constructor.

How to access:

```java
String endpoint = properties.endpoint();
int attempts = properties.retry().attempts();
Duration delay = properties.retry().delay();
```

If **the entire `retry` branch is missing from configuration**, the binder may not create the nested object and the `retry` parameter may receive `null`. This matters because `properties.retry().attempts()` will fail if `retry()` is `null`.

You can handle this in one of the following ways:

- Treat the nested branch as **required** and use validation.
- Set a default value for the nested object.
- Use a constructor to explicitly handle the missing-branch state.

## 12. Creating a Default Nested Object

Spring Boot supports a useful syntax: `@DefaultValue` **with no arguments** on a nested component to instruct the binder to bind a nested object even when no properties belong to that branch.

Example:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        @DefaultValue("https://checkout.example.invalid") String endpoint,
        @DefaultValue Retry retry) {

    public record Retry(
            @DefaultValue("3") int attempts,
            @DefaultValue("1s") Duration delay) {
    }
}
```

With a configuration that does not declare `checkout.retry.*`, the binder can create `Retry` from the defaults of its nested components. Then:

```java
properties.retry().attempts()  // 3
properties.retry().delay()     // PT1S
```

Note: default values must still be convertible to the constructor parameter types. When strict validity checks are needed, add validation.

This approach is suitable when the `retry` branch is a logical configuration section that should always exist, and the application has sensible defaults.

## 13. Using Validation to Protect True Invariants

An object with `final` fields can still be created with **invalid** data, such as `maxAttempts=-7` or a missing URL.

Spring Boot can combine `@ConfigurationProperties` with Bean Validation to validate inputs during initialization.

Example with a record:

```java
package com.example.configdemo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        @NotBlank String endpoint,
        @Min(1) @Max(20) int maxAttempts,
        @NotNull @Valid Retry retry) {

    public record Retry(
            @Min(1) int attempts,
            @NotNull java.time.Duration delay) {
    }
}
```

The constraints:

- `@NotBlank` requires `endpoint` not to be a whitespace-only or empty string.
- `@Min(1)` and `@Max(20)` bound the number of attempts.
- `@NotNull` on `retry` requires the nested object to be present.
- `@Valid` cascades validation to the constraints inside `Retry`.
- `@NotNull` on `delay` requires a `Duration` value.

For the Jakarta Validation example to work in a typical Spring Boot project, a validation provider dependency is required, usually `spring-boot-starter-validation`.

Maven example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

When Spring Boot binds and validates configuration beans, invalid data can cause the application to **fail immediately at startup**. This is usually better than running for some time and only discovering misconfigured parameters later.

**Important:** immutability states that data cannot be modified after the object is created. Validation states that the data **was already valid when created**. The two properties complement each other, but neither replaces the other.

## 14. Using Constructors to Enforce Business Invariants

In addition to Bean Validation, a constructor can contain domain validation logic.

Regular class example:

```java
@ConfigurationProperties(prefix = "retry")
public final class RetryProperties {

    private final int maxAttempts;

    public RetryProperties(int maxAttempts) {
        if (maxAttempts < 1 || maxAttempts > 10) {
            throw new IllegalArgumentException(
                    "retry.max-attempts must be in range 1..10");
        }
        this.maxAttempts = maxAttempts;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }
}
```

This constructor ensures no valid `RetryProperties` instance can be created with `maxAttempts` outside the range 1..10, even when instantiated manually outside Spring.

With a record, you can use a **compact constructor**:

```java
@ConfigurationProperties(prefix = "retry")
public record RetryProperties(int maxAttempts) {

    public RetryProperties {
        if (maxAttempts < 1 || maxAttempts > 10) {
            throw new IllegalArgumentException(
                    "retry.max-attempts must be in range 1..10");
        }
    }
}
```

Here you do not need to assign `this.maxAttempts` manually inside the compact constructor; Java performs the assignment to the record component after the constructor body completes.

Comparing the options:

- **Bean Validation:** provides expressive constraint annotations, well suited for many properties and structured configuration error reporting.
- **Validation in constructor:** useful when invariants span multiple parameters or when you want to guard manual object creation outside Spring as well.
- Both can be combined when there is a clear reason.

Keep error messages easy to understand and avoid printing sensitive secrets when a constraint fails.

## 15. What If There Are Multiple Constructors?

In Spring Boot 3.x, the **single parameterized constructor** case usually does not require `@ConstructorBinding`. However, when a `@ConfigurationProperties` class has **multiple constructors**, you must specify which constructor should be used for configuration binding.

Example:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "worker")
public final class WorkerProperties {

    private final String region;
    private final int threads;

    @ConstructorBinding
    public WorkerProperties(String region, int threads) {
        this.region = region;
        this.threads = threads;
    }

    public WorkerProperties() {
        this("local", 2);
    }

    public String getRegion() {
        return region;
    }

    public int getThreads() {
        return threads;
    }
}
```

The `@ConstructorBinding` annotation here designates the desired constructor for the **binder**. For Spring Boot 3.x, the corresponding import is:

```java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
```

Pay attention to **version differences**. Some older Spring Boot 2.x documentation or code uses a different placement and package for `@ConstructorBinding` compared to Spring Boot 3.x. When upgrading, check against the actual Spring Boot version in `pom.xml` or `build.gradle`.

For a `record` that only has its regular canonical constructor, Spring Boot can use that constructor automatically; there is no need to add `@ConstructorBinding` just to add extra annotations to the code.

## 16. @ConfigurationProperties Is Not @Value on a Constructor

Both examples share the trait of receiving values at object creation time, but their mechanisms differ.

### 16.1. @Value on a Regular Bean Constructor

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class SmsClient {

    private final String sender;

    public SmsClient(@Value("${sms.sender:system}") String sender) {
        this.sender = sender;
    }
}
```

Spring uses **dependency injection** to create `SmsClient`, while resolving the `${sms.sender:system}` placeholder.

### 16.2. Constructor Binding of ConfigurationProperties

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "sms")
public record SmsProperties(String sender, int retryCount) {
}
```

Here, the binder looks up the `sms.sender` and `sms.retry-count` keys, performs type conversion, and creates a **dedicated configuration bean**. Constructor parameters do not each need `@Value`.

A regular service can then inject `SmsProperties`:

```java
@Service
public class SmsClient {

    private final SmsProperties properties;

    public SmsClient(SmsProperties properties) {
        this.properties = properties;
    }
}
```

**Do not add `@Component` to `SmsProperties` just to "be sure the bean is registered"** when you intend to use constructor binding. Use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

For one or two standalone values, `@Value` may suffice. For a structured configuration group that needs validation or immutability, `@ConfigurationProperties` usually expresses a cleaner design.

## 17. Relaxed Binding and Naming Rules

YAML files commonly use **kebab-case** names:

```yaml
worker:
  max-threads: 8
  idle-timeout: 30s
```

A record can use camelCase:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        int maxThreads,
        java.time.Duration idleTimeout) {
}
```

Spring Boot's binder supports linking corresponding naming formats according to relaxed binding rules.

This also helps when working with environment variables. Typical OS environment variable form:

```bash
WORKER_MAXTHREADS=12 WORKER_IDLETIMEOUT=45s java -jar app.jar
```

In Spring Boot's canonical conversion for environment variables, dots become underscores, hyphens are removed, and names are uppercased. Thus, names like `WORKER_MAXTHREADS` are the standard form for the `worker.max-threads` key, rather than arbitrarily writing `WORKER_MAX_THREADS` and expecting the binder to treat every case identically.

When a value is not as expected, check the key name in the actual source, the constructor parameter name, and the result from Spring's `Environment`.

## 18. Constructor Binding Still Follows Source Precedence

Immutable design **does not change** how Spring Boot selects external configuration.

Example:

```yaml
# application.yml
worker:
  max-threads: 4
```

A record:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

When running:

```bash
java -jar app.jar --worker.max-threads=16
```

the binder receives the effective value of `worker.max-threads`, typically `16` because command-line arguments have higher precedence than Config Data in standard Spring Boot setups.

With a profile:

```yaml
# application-prod.yml
worker:
  max-threads: 24
```

When running:

```bash
java -jar app.jar --spring.profiles.active=prod
```

if no higher-precedence source overrides it, the record is created with `maxThreads=24`.

This illustrates the principle:

**Source precedence determines the input value; constructor binding determines how that input value is turned into a typed and potentially immutable object.**

## 19. Immutability and Configuration Lifecycle

A `@ConfigurationProperties` bean using constructor binding is normally created during Spring context startup.

Suppose at startup we have:

```text
worker.max-threads = 8
```

The binder creates:

```java
new WorkerProperties(8)
```

If you later edit `application.yml` to:

```yaml
worker:
  max-threads: 12
```

An existing immutable configuration bean **does not turn into a new object** simply because the file on disk changed. You normally have to restart the application for new values to be loaded into the bean, unless the project has a specific refresh/rebind mechanism designed for it.

This makes sense for immutable configuration: services see a stable configuration snapshot rather than fields changing mid-request.

If the application requires runtime configuration changes, choose an architecture dedicated to that capability rather than expecting constructor binding to provide hot reload out of the box.

## 20. Centralized Configuration Design Instead of Scattered Values

Suppose a service calling an external API needs:

```yaml
gateway:
  base-url: "https://gateway.example.invalid"
  connect-timeout: 2s
  read-timeout: 10s
  retry-count: 3
```

If each business class uses several `@Value` annotations, configuration becomes scattered:

```java
@Value("${gateway.base-url}")
private String url;

@Value("${gateway.retry-count}")
private int retries;
```

A better approach for related properties:

```java
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        java.net.URI baseUrl,
        java.time.Duration connectTimeout,
        java.time.Duration readTimeout,
        int retryCount) {
}
```

Services use the same type:

```java
@Service
public class GatewayClient {

    private final GatewayProperties config;

    public GatewayClient(GatewayProperties config) {
        this.config = config;
    }

    public String summary() {
        return "timeout=" + config.readTimeout()
                + ", retries=" + config.retryCount();
    }
}
```

Benefits:

1. Configuration has **a single name and a single data-type contract**.
2. Related properties are grouped under the `gateway` prefix.
3. Validation can be added once on the configuration class.
4. Unit tests can construct the record directly without Spring.
5. Services do not need to know individual string key names.
6. When configuration design changes, the compiler helps locate accessor usages.

Do not lump every property in the entire application into one giant record. Split them along responsibility boundaries such as `MailProperties`, `GatewayProperties`, and `StorageProperties`.

## 21. Immutable List and Map Configuration

A configuration object may contain lists or maps.

Example:

```yaml
cors:
  allowed-origins:
    - "https://app.example.invalid"
    - "https://admin.example.invalid"
  headers:
    client-id: "X-Client-Id"
    trace-id: "X-Trace-Id"
```

Record:

```java
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "cors")
public record CorsProperties(
        List<String> allowedOrigins,
        Map<String, String> headers) {

    public CorsProperties {
        allowedOrigins = allowedOrigins == null
                ? List.of()
                : List.copyOf(allowedOrigins);

        headers = headers == null
                ? Map.of()
                : Map.copyOf(headers);
    }
}
```

This accepts data from the binder and normalizes it into collections that cannot be modified via common mutating methods.

However, keep in mind:

- `List.copyOf` and `Map.copyOf` do not accept `null` elements or values.
- An unmodifiable collection **does not make mutable element objects immutable**.
- If configuration requires element ordering, use appropriate data types and operations; do not assume `Map.copyOf` preserves an iteration order the application relies on.
- If you want to distinguish "collection not declared" from "empty collection present", do not accidentally normalize both to the same value.

Immutability is **a meaningful design decision**, not merely adding the `final` keyword.

## 22. Testing Constructor-Bound Configuration

With a record or a constructor-only class, you can test at two different levels.

### 22.1. Unit Tests Without Spring

Example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class WorkerPropertiesUnitTest {

    @Test
    void storesValues() {
        WorkerProperties properties = new WorkerProperties(6);

        assertEquals(6, properties.maxThreads());
    }
}
```

This test checks the **Java object's contract**. It does not test Spring reading YAML or binding property names.

### 22.2. Testing Binding with ApplicationContextRunner

To test the binding mechanism itself, Spring Boot Test provides `ApplicationContextRunner`.

Suppose we have the record:

```java
package com.example.configdemo;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        int maxThreads,
        Duration idleTimeout) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class WorkerPropertiesBindingTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsThroughConstructor() {
        contextRunner
                .withPropertyValues(
                        "worker.max-threads=12",
                        "worker.idle-timeout=45s")
                .run(context -> {
                    WorkerProperties properties =
                            context.getBean(WorkerProperties.class);

                    assertThat(properties.maxThreads()).isEqualTo(12);
                    assertThat(properties.idleTimeout())
                            .isEqualTo(Duration.ofSeconds(45));
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfig {
    }
}
```

Note that `WorkerProperties` in this test is registered with `@EnableConfigurationProperties`, allowing Spring Boot to use the binder. Values are supplied via `withPropertyValues`, independent of any specific YAML file.

This style of test is useful when verifying:

- Correct property names.
- Correct type conversion.
- Default values.
- Validation and startup failures.
- Nested configuration branches.

### 22.3. Integration Testing with @SpringBootTest

If you need to verify how multiple beans work together across the application, you can use:

```java
@SpringBootTest(properties = {
        "worker.max-threads=16",
        "worker.idle-timeout=30s"
})
class WorkerIntegrationTest {

    @Autowired
    private WorkerProperties properties;

    @Test
    void usesTestProperties() {
        assertEquals(16, properties.maxThreads());
    }
}
```

This example requires importing the corresponding annotations from JUnit, Spring, and Spring Boot Test. The application must have a suitable `@SpringBootApplication` configuration discovered by Spring Boot or explicitly declared.

You do not need to use `@SpringBootTest` for every test; small-scoped binding tests generally run faster and pinpoint errors more easily.

## 23. Common Mistakes and How to Handle Them

### 23.1. Putting @Component on a Record and Expecting the Binder to Use the Constructor

Unsuitable example for constructor binding:

```java
@Component
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

Problem: `@Component` puts the class through the standard bean registration mechanism; `@ConfigurationProperties` constructor binding is not applied the same way as when a bean is created via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

Correct approach:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

and register the type using one of the two mechanisms dedicated to `@ConfigurationProperties`.

### 23.2. Forgetting to Register the Configuration Class

Having `@ConfigurationProperties` without scanning or enabling: services may fail reporting that the `WorkerProperties` bean could not be found.

Check scanned packages, annotations on the application class, and the registration setup instead of adding `@Component` as a workaround when using constructor binding.

### 23.3. Misspelling the Prefix or Key Name

Record:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

YAML file:

```yaml
workers:
  max-threads: 8
```

Here `workers` and `worker` are different. The binder cannot infer that the two prefixes mean the same thing.

Another mistake is writing singular `worker.max-thread` while the configuration expects `maxThreads`. Keep canonical names consistent across sources and Java types.

### 23.4. Missing -parameters When Using Class Constructors

With regular classes, constructor parameter names play a role in binding. If compilation does not retain parameter names, the binder may fail to identify the corresponding keys.

Ensure compilation includes `-parameters`. When using official Spring Boot build plugins, check the current configuration before manually adding the option again.

### 23.5. Using @ConstructorBinding from the Wrong Version Package

A project upgraded from Spring Boot 2.x might still import `@ConstructorBinding` from the old package or place it in the old location. In Spring Boot 3.x, when you need to specify a constructor, use the annotation on the constructor from:

```java
org.springframework.boot.context.properties.bind.ConstructorBinding
```

Do not copy old snippets without checking the actual version.

### 23.6. Expecting Setters to Run on a Record

Records do not have JavaBean-style setters. Spring Boot creates records via their constructor, and record components cannot be reassigned afterward through normal setter binding.

If you genuinely need mutable update steps, re-evaluate the requirement instead of trying to add inappropriate setters to a record.

### 23.7. Forgetting That a Nested Branch Can Be Null

With a record:

```java
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(Retry retry) {
    public record Retry(int attempts) {
    }
}
```

if `checkout.retry.*` is not declared, `retry()` can be `null`. Use validation or nested defaults if that branch must always be present.

### 23.8. Wrong Value Type in Configuration

Example:

```yaml
worker:
  max-threads: many
```

`many` cannot be converted to `int` under standard rules. Binding may prevent the application from starting.

Set a value of the matching type, such as `8`, and verify which source is providing the effective value.

### 23.9. Assuming final Means Deeply Immutable

A `final List<String>` field does not prevent mutating the list contents. For collection data, use defensive copies and appropriate immutable types if stability is required.

### 23.10. Using record.toString() with Secrets

A record's generated `toString()` can display all components, including passwords or tokens if the configuration contains them.

**Do not log the entire configuration bean** in production systems when it contains sensitive fields. Using a record makes code concise, but does not automatically protect secrets.

## 24. Comparing Mutable and Immutable Designs

### Mutable JavaBean

```java
@ConfigurationProperties(prefix = "mail")
public class MailProperties {

    private String host;
    private int port;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }
}
```

### Immutable Class Constructor

```java
@ConfigurationProperties(prefix = "mail")
public final class MailProperties {

    private final String host;
    private final int port;

    public MailProperties(String host, int port) {
        this.host = host;
        this.port = port;
    }

    public String getHost() {
        return host;
    }

    public int getPort() {
        return port;
    }
}
```

### Immutable Record

```java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(String host, int port) {
}
```

The three examples express the same two values `host` and `port`, but each should be used **individually** since they share the name `MailProperties`. The difference lies in their mutability contract:

| Design | Setters | Initialized via Constructor with Values | Immutability After Creation |
| --- | --- | --- | --- |
| Mutable JavaBean | Yes | Not required | No |
| Class with final fields | No | Yes | Yes for immutable components |
| Record | No | Yes, via canonical constructor | Shallowly immutable; watch mutable components |

For applications that treat configuration as a startup snapshot, a constructor-bound class or record is usually a clear model. For a bean whose properties code needs to update during its lifecycle, evaluate the actual requirement rather than picking mutable configuration merely for initial convenience.

## 25. Practice Exercises

### Exercise A: Design a Record

Given YAML:

```yaml
report:
  title: "Daily report"
  interval: 10m
  max-records: 500
  enabled: true
```

Write a constructor-bound record.

Sample answer:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "report")
public record ReportProperties(
        String title,
        Duration interval,
        int maxRecords,
        boolean enabled) {
}
```

Register `ReportProperties` with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

### Exercise B: Add a Default Value

The application needs `report.max-records` to default to `100` when undeclared.

One approach:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "report")
public record ReportProperties(
        @DefaultValue("100") int maxRecords) {
}
```

If `application.yml` contains `report.max-records=500`, the actual configuration value is still used; the default only applies when no matching data is present.

### Exercise C: Nested Branch

Given YAML:

```yaml
storage:
  bucket: "reports"
  retry:
    attempts: 3
    delay: 2s
```

Write the record:

```java
@ConfigurationProperties(prefix = "storage")
public record StorageProperties(
        String bucket,
        Retry retry) {

    public record Retry(
            int attempts,
            java.time.Duration delay) {
    }
}
```

Describe the value of `properties.retry().attempts()`. With the given configuration, the result is `3`.

### Exercise D: Check Immutability Semantics

Consider:

```java
public record RegionProperties(List<String> regions) {
}
```

Question: can a caller mutate the contents of an `ArrayList` passed into the record?

Yes, because the record only holds a reference to the list. Make a defensive copy using `List.copyOf` in a compact constructor and decide on a policy for `null`.

### Exercise E: Spot the Registration Error

Consider:

```java
@Component
@ConfigurationProperties(prefix = "report")
public record ReportProperties(int maxRecords) {
}
```

Question: what is inappropriate if the goal is constructor binding?

`@Component` registers the bean via the regular component mechanism. Remove `@Component` and use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` so Spring Boot binds via the constructor using the dedicated mechanism for configuration properties.

### Exercise F: Determine the Effective Value

`application.yml`:

```yaml
worker:
  max-threads: 4
```

`application-prod.yml`:

```yaml
worker:
  max-threads: 10
```

Launch command:

```bash
java -jar app.jar --spring.profiles.active=prod --worker.max-threads=16
```

Record:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

The final value is `16` under normal circumstances: command-line arguments have higher precedence than file configuration. Constructor binding does not change this rule.

## 26. Takeaways

- **Constructor binding** uses a constructor to create a `@ConfigurationProperties` object from resolved and converted properties.
- **Immutability** helps configuration beans preserve stable state after initialization; use `final` fields, no setters, or a Java `record`.
- In Spring Boot 3.x, a class with a single parameterized constructor or a record with a regular canonical constructor typically **does not need `@ConstructorBinding`**. If there are multiple constructors, place the annotation on the desired constructor.
- **Register using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`**. Do not use `@Component` expecting constructor binding to run as it does for a dedicated configuration-properties bean.
- Constructor parameters receive configuration values; services receive the **configuration bean** through regular Spring dependency injection.
- `@DefaultValue` provides fallback values for constructor binding, including declaring defaults for nested branches.
- For required configuration, use **Bean Validation** and/or invariant checks in the constructor to fail fast at startup.
- Records are **shallowly immutable**; mutable collections or nested objects still need handling if deep immutability is desired.
- Immutable binding does not affect **source precedence** across YAML, profiles, environment variables, and command-line arguments.
- Constructor binding itself does not automatically refresh a bean when configuration files change at runtime.
- Designing configuration groups by responsibility and testing both the Java object contract and binding behavior makes configuration clearer, safer, and easier to maintain.
