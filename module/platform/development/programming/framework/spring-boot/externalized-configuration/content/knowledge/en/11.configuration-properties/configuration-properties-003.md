# Registering with @ConfigurationPropertiesScan

In Spring Boot, the **`@ConfigurationProperties`** annotation describes how to map a group of configuration keys to a typed Java object, whereas **`@ConfigurationPropertiesScan`** instructs Spring Boot to **discover and register those configuration classes as beans**. The two annotations serve two distinct steps: *defining the data contract* and *bringing that contract into the Spring ApplicationContext*.

A common mistake is creating a record with `@ConfigurationProperties(prefix = "app.client")`, writing a complete `application.yml`, and then hitting a **bean not found** error when injecting the record into a service. Usually the cause is not YAML syntax, but failing to enable scanning, scanning the wrong package, or using the wrong registration mechanism.

This lesson walks through a small application, explaining the path from `application.yml` to a bean, package scan scope, constructor binding, multi-module setups, validation, comparison with `@EnableConfigurationProperties`, and troubleshooting common errors. Examples primarily target Spring Boot 3.x with Java 17 or later.

## 1. The Big Picture: Definition vs. Registration

~~~text
application.yml / application.properties
      |
      | app.client.base-url=https://api.example.test
      | app.client.connect-timeout=750ms
      | app.client.max-retries=3
      v
Spring Boot Environment
      |
      | PropertySources and precedence order
      v
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(...)
      ^
      |
@ConfigurationPropertiesScan
      |
      | finds @ConfigurationProperties classes in scanned packages
      | registers configuration bean types with ApplicationContext
      v
Spring Boot Binder
      |
      | matches keys by prefix
      | converts strings to URI, Duration, int...
      | applies validation if configured
      v
ClientProperties bean
      |
      v
RemoteClient constructor injection
~~~

Separate these three responsibilities:

1. **Configuration sources** provide key/value pairs after Spring Boot merges files, profiles, environment variables, and startup arguments.
2. **`@ConfigurationProperties`** specifies the prefix and target Java model.
3. **`@ConfigurationPropertiesScan`** locates models annotated with `@ConfigurationProperties` within allowed packages so the framework can register and bind them.

Having a YAML file alone does not create a `ClientProperties` bean. Likewise, placing `@ConfigurationProperties` on a record alone does not mean the record is registered with Spring.

## 2. Minimal Working Example

Suppose you create a Spring Boot application with this structure:

~~~text
order-service/
  build.gradle
  src/
    main/
      java/
        com/example/orders/
          OrderApplication.java
          config/
            ClientProperties.java
          service/
            RemoteClient.java
      resources/
        application.yml
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: order-service

app:
  client:
    base-url: https://api.example.test
    connect-timeout: 750ms
    max-retries: 3
    enabled: true
~~~

Record holding configuration data:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries,
    boolean enabled
) {}
~~~

The `@ConfigurationProperties` annotation declares that the record's components should receive values under the `app.client` prefix. For example, `base-url` maps to `baseUrl`, and `connect-timeout` maps to `connectTimeout`.

Now enable scanning on the startup class:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Business bean consuming the configuration:

~~~java
package com.example.orders.service;

import com.example.orders.config.ClientProperties;
import org.springframework.stereotype.Service;

@Service
public class RemoteClient {
    private final ClientProperties properties;

    public RemoteClient(ClientProperties properties) {
        this.properties = properties;
    }

    public String endpointDescription() {
        return properties.baseUrl()
            + " (timeout=" + properties.connectTimeout()
            + ", retries=" + properties.maxRetries() + ")";
    }
}
~~~

When Spring Boot starts with this package layout:

- `OrderApplication` in `com.example.orders` is the scan root.
- `@ConfigurationPropertiesScan` discovers `ClientProperties` in the subpackage `com.example.orders.config`.
- The framework registers the configuration bean and the Binder converts values from Environment into the record.
- Spring injects the `ClientProperties` bean into `RemoteClient`'s constructor.

This is the core pairing: **`@ConfigurationProperties` on the data type, and `@ConfigurationPropertiesScan` on a configuration or startup class located in the appropriate package.**

## 3. Why Is @ConfigurationPropertiesScan Required?

In a Spring application, a Java class does not automatically become a bean merely by existing on the classpath. Spring needs a registration mechanism: component scanning, `@Bean`, imports, `@EnableConfigurationProperties`, or another mechanism.

The class:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    String baseUrl,
    int maxRetries
) {}
~~~

only describes the binding. Without a corresponding bean definition, Spring has no object to inject:

~~~java
public RemoteClient(ClientProperties properties) {
    this.properties = properties;
}
~~~

A corresponding error message may look like:

~~~text
Parameter 0 of constructor in com.example.orders.service.RemoteClient
required a bean of type 'com.example.orders.config.ClientProperties'
that could not be found.
~~~

Adding `@ConfigurationPropertiesScan` with the right scope is the purpose-built solution. The annotation performs **dedicated scanning for configuration properties classes**, not "scan every class and turn them all into beans."

### How Does It Differ from @SpringBootApplication?

`@SpringBootApplication` already includes default package-scoped component scanning, which picks up beans annotated with stereotypes such as `@Component`, `@Service`, `@Repository`, or `@Controller`.

`@ConfigurationProperties` **is not equivalent to `@Component`**. Therefore, do not assume `@SpringBootApplication` automatically discovers every `@ConfigurationProperties` record via standard component scanning.

When you add:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

you are adding the typed configuration class scanning step to the application's startup mechanism.

## 4. Package Scope Rules for @ConfigurationPropertiesScan

When no attributes are passed:

~~~java
@ConfigurationPropertiesScan
~~~

Spring Boot uses the **package containing the annotated class** as the scan root. It inspects eligible classes in that root package and its subpackages.

For example:

~~~text
com.example.orders
  ├── OrderApplication                  @ConfigurationPropertiesScan
  ├── config
  │    ├── ClientProperties             @ConfigurationProperties
  │    └── CacheProperties              @ConfigurationProperties
  └── service
       └── RemoteClient                 @Service
~~~

If the annotation is on `com.example.orders.OrderApplication`, classes in `com.example.orders.config` are in scope. Both `ClientProperties` and `CacheProperties` can be discovered.

Conversely:

~~~text
com.example
  ├── orders
  │    └── OrderApplication             @ConfigurationPropertiesScan
  └── shared
       └── SecurityProperties           @ConfigurationProperties
~~~

`com.example.shared.SecurityProperties` **is not in a subpackage of `com.example.orders`**, so it is not scanned by the default annotation on `OrderApplication` alone.

### Solving with basePackages

When you need to explicitly specify packages, use `basePackages`:

~~~java
package com.example.orders;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan(basePackages = {
    "com.example.orders.config",
    "com.example.shared.config"
})
public class OrderApplication {}
~~~

This is useful when configuration resides in modules or packages outside the default scan area. However, string package names can break if a refactor renames a package without updating the annotation.

### Solving with basePackageClasses

A safer approach when you have marker classes is `basePackageClasses`:

~~~java
package com.example.orders;

import com.example.orders.config.ClientProperties;
import com.example.shared.config.SecurityProperties;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan(basePackageClasses = {
    ClientProperties.class,
    SecurityProperties.class
})
public class OrderApplication {}
~~~

Spring Boot uses the **packages of the specified classes as scan roots**. It does not merely register just those two exact classes: any eligible `@ConfigurationProperties` types within those packages can also be discovered.

When you want to register strictly one or a few specific types rather than entire packages, `@EnableConfigurationProperties(ClientProperties.class)` usually expresses intent more clearly.

### Where Should the Root Package Be Placed?

If most of the application lives under `com.example.orders`, placing the main class and `@ConfigurationPropertiesScan` in that package is usually appropriate. There is no need to widen the scan to all of `com.example` if the project contains unrelated services and modules. Scanning the right scope avoids creating unintended configuration beans.

## 5. Distinguishing @ConfigurationPropertiesScan and @ComponentScan

Both annotations have "scan" in their names, but their targets differ.

| Aspect | `@ComponentScan` | `@ConfigurationPropertiesScan` |
| --- | --- | --- |
| Purpose | Discover Spring components by stereotype annotations | Discover eligible `@ConfigurationProperties` classes |
| Example classes | `@Service`, `@Component` | `@ConfigurationProperties(prefix = "...")` |
| Bean role | Services, repositories, controllers, configurations, and components | Objects holding bound configuration |
| Guaranteed to create @ConfigurationProperties bean? | No, if only `@ConfigurationProperties` is used without a stereotype | Yes, for eligible classes within the scan scope |
| Scans every @Service? | Possible, depending on scope | No |
| Constructor binding for immutable records | Not the default mechanism for constructor-bound config types | An appropriate registration mechanism |

A common point of confusion: Spring Boot documentation notes that **classes annotated or meta-annotated with `@Component` are not picked up by `@ConfigurationPropertiesScan`**. Such classes may be registered by component scanning, but that is **a different registration path**.

For example:

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public class MutableClientProperties {
    // Fields + getters/setters...
}
~~~

This kind of bean can be discovered by component scanning and then bound through appropriate configuration properties support. However, **you should not say `@ConfigurationPropertiesScan` finds it**. In particular, constructor binding for `@ConfigurationProperties` is not applied in the same way to beans created by regular Spring bean mechanisms like `@Component` or `@Bean`.

For immutable records, the clear choice is:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(...) {}
~~~

and registering it via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, **without adding `@Component` just to avoid a bean-not-found error**.

## 6. Constructor Binding with Records or Immutable Classes

Spring Boot 3.x can bind configuration properties via constructors for immutable objects. With a record having a single canonical constructor, for example:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

when the class is registered via configuration properties scanning, the Binder retrieves matching properties and passes them to the record constructor.

Data:

~~~properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=2s
app.client.max-retries=3
~~~

creates a record equivalent to:

~~~java
new ClientProperties(
    URI.create("https://api.example.test"),
    Duration.ofSeconds(2),
    3
);
~~~

The `new ...` snippet only illustrates the binding result; in a real application, Spring Boot creates the object through the Binder mechanism and injects that bean into consumers.

### Do You Always Have to Write @ConstructorBinding?

No. In Spring Boot 3.x, **a single parameterized constructor** is normally inferred for constructor binding; a record with a canonical constructor is the prime example. For classes with multiple constructors or complex structures, you may need to specify which constructor to use according to your actual Spring Boot version.

Do not copy an `@ConstructorBinding` import path from an older Spring Boot version to a newer one without checking version compatibility. This lesson uses simple records, so that annotation is not needed.

### Why Can @Component Cause Issues?

Spring Framework instantiates `@Component` beans using constructor injection for their dependencies. Meanwhile, `ClientProperties`'s constructor takes `URI`, `Duration`, and `int`, which are **values the Binder must convert from keys/values** rather than Spring beans to inject.

Therefore, putting `@Component` on a constructor-bound record is not an equivalent substitute for configuration properties scanning. For immutable typed configuration, use the dedicated registration mechanism so the Spring Boot Binder handles instantiation.

## 7. Using Mutable JavaBeans When Setter Binding Is Needed

Not all configuration properties have to be records. A class with a default constructor and getters/setters can still be instantiated and populated by the Binder:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private int concurrency = 4;
    private Duration pollInterval = Duration.ofSeconds(5);

    public int getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(int concurrency) {
        this.concurrency = concurrency;
    }

    public Duration getPollInterval() {
        return pollInterval;
    }

    public void setPollInterval(Duration pollInterval) {
        this.pollInterval = pollInterval;
    }
}
~~~

Configuration file:

~~~yaml
app:
  worker:
    concurrency: 8
    poll-interval: 2s
~~~

If `WorkerProperties` is within `@ConfigurationPropertiesScan` scope, it is registered and can be bound as a configuration bean. Fields with defaults serve as fallbacks when keys are absent from effective sources.

For immutable records, defaults must rely on appropriate constructor/binding mechanisms; do not blindly apply JavaBean field-initializer thinking to records.

A design choice:

- Use a record if configuration values should remain fixed after binding and you want an explicit contract.
- Use a JavaBean if you need setter binding, legacy library compatibility, or specific mutable property requirements.
- Both can still be registered via `@ConfigurationPropertiesScan` if they are eligible `@ConfigurationProperties` types within scanned packages.

Do not confuse a "mutable properties class" with "live self-updating configuration." Editing a YAML file while the application is running does not automatically rebind a mutable bean without a dedicated refresh/rebind mechanism.

## 8. Pattern for Using @ConfigurationPropertiesScan Across Multiple Packages

A real-world application has multiple configuration groups:

~~~text
com.example.orders
  ├── OrderApplication.java
  ├── config
  │    ├── ClientProperties.java
  │    ├── MailProperties.java
  │    └── CacheProperties.java
  ├── client
  │    └── RemoteOrderClient.java
  └── mail
       └── MailService.java
~~~

The property types:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl, Duration timeout) {}

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String host, int port) {}

@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(Duration ttl, int maximumSize) {}
~~~

These are three separate class/record examples, placed in three Java files following the one-public-type-per-file convention in real projects.

On the main class:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

If the main class is in `com.example.orders` and the properties types reside under `com.example.orders.config`, **one scan annotation suffices to discover all three**. There is no need to add `@Component` to each record.

### Criteria for Splitting Properties Classes

Organize by functional boundaries: client, mail, cache, storage, export, or payment. Avoid creating one class holding dozens of unrelated keys just because scanning can find everything.

Consumers can inject the exact model they need:

~~~java
@Service
public class MailService {
    private final MailProperties mail;

    public MailService(MailProperties mail) {
        this.mail = mail;
    }
}
~~~

This makes refactoring configuration and writing unit tests simpler than scattering `Environment.getProperty("app.mail.host")` everywhere.

## 9. Comparison with @EnableConfigurationProperties

Both annotations bring `@ConfigurationProperties` into the ApplicationContext, but they differ in how scope is specified.

### @ConfigurationPropertiesScan: Package-Based Discovery

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

Suitable when you have **many properties types** organized in one or more packages and want automatic discovery.

### @EnableConfigurationProperties: Type-Based Registration

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {}
~~~

Suitable when you want to **explicitly list the exact properties types to register**, such as an auto-configuration module enabling `ClientProperties`, or a test needing only one specific bean.

It can also be placed directly on the application:

~~~java
@SpringBootApplication
@EnableConfigurationProperties({
    ClientProperties.class,
    MailProperties.class
})
public class OrderApplication {}
~~~

This approach does not require the listed classes to reside under a scanned package. Of course, they must be on the classpath.

| Question | `@ConfigurationPropertiesScan` | `@EnableConfigurationProperties` |
| --- | --- | --- |
| Goal description | Scan packages for properties types | Register specific properties types |
| Typical number of types | Convenient when there are many types | Convenient for a small, known set of types |
| Depends on package location | Yes | Does not require package scanning |
| Need to list each class? | No | Yes, when declaring the type list |
| Suitable on main app | Yes | Yes |
| Suitable in small config modules | Possible | Usually easier to control for just a few types |

**Do not register the same class with both mechanisms "just to be sure."** If a class is registered through multiple paths, you may end up with hard-to-read config or multiple candidate beans depending on how registrations interact. Choose a clear and consistent registration model.

## 10. @Bean + @ConfigurationProperties: Configuring Third-Party Objects

`@ConfigurationPropertiesScan` discovers **classes** annotated with `@ConfigurationProperties`. However, sometimes you want to bind keys onto an object created by another library—a type whose source code you do not control.

In that case, `@ConfigurationProperties` can be placed on a **`@Bean` method** so Spring binds matching properties onto the bean instance after the factory method creates it.

Example of a mutable type with setters provided by an internal library:

~~~java
package com.example.orders.config;

import com.example.legacy.LegacyPoolSettings;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacyPoolConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.legacy-pool")
    LegacyPoolSettings legacyPoolSettings() {
        return new LegacyPoolSettings();
    }
}
~~~

Assuming `LegacyPoolSettings` has suitable getters/setters, keys like `app.legacy-pool.maximum-size` can be bound onto the bean.

Key points:

- The bean is registered by **`@Bean`**, not by `@ConfigurationPropertiesScan` finding the third-party class.
- Setter/property binding depends on the capabilities of the target type.
- When using `@Bean` to create a library type, constructor binding for immutable configuration beans does not operate through the dedicated configuration properties registration path.

If you own the type and want an immutable model, it is usually cleaner to define your own `@ConfigurationProperties` record and register it via scan or enable.

## 11. How Does the Spring Boot Binder Handle Names and Types?

One major advantage of configuration properties is **relaxed binding**: key names from configuration sources can be mapped via Spring Boot's rules to Java property names.

For example:

~~~properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=1500ms
app.client.max-retries=4
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

The Binder can convert the values:

| Key | Record Component | Java Type | Result |
| --- | --- | --- | --- |
| `app.client.base-url` | `baseUrl` | `URI` | API URI |
| `app.client.connect-timeout` | `connectTimeout` | `Duration` | 1.5 seconds |
| `app.client.max-retries` | `maxRetries` | `int` | 4 |

Canonical key names should prefer **lowercase kebab-case** in files:

~~~properties
app.client.connect-timeout=1500ms
~~~

In deployment environments, environment variables can use names following Spring Boot's conversion rules, such as `APP_CLIENT_CONNECTTIMEOUT`. The Binder reads from Environment and applies relaxed binding instead of requiring every source to use identical casing.

**Scanning does not change source precedence.** If YAML sets timeout to 3 seconds but the command line passes `--app.client.connect-timeout=500ms`, the bean is bound using the effective value across configuration sources during normal binding—YAML does not win just because it is inside the project.

## 12. Nested Properties, Lists, and Maps When Scanning

Scanning only determines **which root properties classes are registered as beans**. It does not require each nested type to have its own `@ConfigurationProperties`.

For example:

~~~yaml
app:
  outbound:
    endpoint: https://gateway.example.test
    retry:
      max-attempts: 3
      backoff: 250ms
    allowed-regions:
      - ap-southeast-1
      - eu-west-1
    headers:
      x-tenant: demo
      x-region: asia
~~~

Record:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.outbound")
public record OutboundProperties(
    URI endpoint,
    Retry retry,
    List<String> allowedRegions,
    Map<String, String> headers
) {
    public record Retry(
        int maxAttempts,
        Duration backoff
    ) {}
}
~~~

The scanner only needs to see the root `OutboundProperties`. Nested `Retry` is handled by the Binder as part of the data model, without placing `@ConfigurationPropertiesScan` or `@Component` on the nested record.

Usage:

~~~java
@Service
public class OutboundService {
    private final OutboundProperties properties;

    public OutboundService(OutboundProperties properties) {
        this.properties = properties;
    }

    public int retryLimit() {
        return properties.retry().maxAttempts();
    }
}
~~~

Avoid trying to turn every nested part into an independent Spring bean if it only makes sense inside one configuration group.

### When to Split into a Separate Bean?

If an `app.retry.*` group is shared across multiple independent modules as a distinct contract, you can create `RetryProperties` with its own prefix and register it via scan. But if retry belongs strictly to one HTTP client, keeping it as a nested value clarifies the dependency.

## 13. Validating Configuration Properties Beans

A bean that is scanned and bound can still hold values that are invalid for business rules. `@ConfigurationPropertiesScan` **does not automatically infer constraints such as "port between 1 and 65535."** You must declare validation if you want Spring Boot to verify them at startup.

For example:

~~~java
package com.example.orders.config;

import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
    @NotBlank String host,
    @Min(1) @Max(65535) int port,
    @NotNull @Valid Timeout timeout
) {
    public record Timeout(
        @NotNull Duration connect,
        @NotNull Duration read
    ) {}
}
~~~

Configuration file:

~~~yaml
app:
  mail:
    host: smtp.example.test
    port: 587
    timeout:
      connect: 2s
      read: 5s
~~~

With Spring Boot 3.x and Jakarta Validation, the project needs an appropriate validation dependency, such as `spring-boot-starter-validation`. Once the bean is scanned and bound, constraints can be checked. `@Valid` on the nested object ensures validation cascades into `Timeout`.

If `app.mail.port=70000` or `host` is blank, a validation error can stop application startup with a message identifying the problematic properties. That is usually desirable for essential settings: **fail fast** instead of waiting for the first request to use an invalid value.

### Scanning and Validation Are Distinct

- `@ConfigurationPropertiesScan`: discovers and registers.
- `@ConfigurationProperties`: binds keys to data types.
- `@Validated` and constraints: check validity conditions when validation infrastructure is configured.
- Business bean: consumes the bound data.

Do not conclude "I added `@ConfigurationPropertiesScan`, so every field is validated." If an attribute is required, declare meaningful constraints for its type and ensure a validation provider is available.

## 14. Default Values and Missing Keys

Consider this record:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    String baseUrl,
    int maxRetries,
    Duration timeout
) {}
~~~

If `app.client.timeout` is absent from the file, a constructor-bound configuration may receive `null` for the `Duration` component unless you design an appropriate default or validation. If `max-retries` is absent, primitive `int` may receive a default like `0` during binding.

Do not equate "the bean was created successfully" with "every required property was supplied."

### Defaults for Mutable JavaBeans

Field initializers can be used:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private int concurrency = 4;
    private Duration pollInterval = Duration.ofSeconds(5);

    // corresponding getters and setters
}
~~~

### Defaults for Constructor-Bound Records

Spring Boot Binder supports the `@DefaultValue` annotation on constructor-binding parameters to specify fallbacks. Record-style example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
    @DefaultValue("4") int concurrency,
    @DefaultValue("5s") Duration pollInterval
) {}
~~~

This example follows modern Spring Boot's constructor binding model. For required values, do not add defaults to mask missing configuration; use validation instead.

If defaults depend on other fields or involve complex semantics, consider handling that explicitly in your model or a business class rather than cramming all rules into the constructor.

## 15. Why Didn't Scan Find the Bean? Common Scenarios

### Scenario A — Missing @ConfigurationPropertiesScan

~~~java
@SpringBootApplication
public class OrderApplication {}
~~~

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl) {}
~~~

No dedicated registration mechanism is present here. If code injects `ClientProperties`, it may fail with a missing bean error.

**Fix:** add `@ConfigurationPropertiesScan` to the main class or use `@EnableConfigurationProperties(ClientProperties.class)`.

### Scenario B — Class Outside the Scanned Package

~~~text
com.example.orders.OrderApplication
com.example.shared.config.ClientProperties
~~~

If `@ConfigurationPropertiesScan` is only placed on `com.example.orders` with no arguments, the scanner does not cover `com.example.shared.config`.

**Fix:** use `basePackages` or `basePackageClasses` appropriately:

~~~java
@ConfigurationPropertiesScan(
    basePackageClasses = ClientProperties.class
)
~~~

Or use `@EnableConfigurationProperties(ClientProperties.class)` when only a single type is needed.

### Scenario C — Missing @ConfigurationProperties on the Class

~~~java
public record ClientProperties(URI baseUrl, Duration timeout) {}
~~~

If the record lacks `@ConfigurationProperties`, the scanner has no signal that it is a root configuration properties type.

**Fix:** annotate with the proper prefix:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl, Duration timeout) {}
~~~

### Scenario D — Adding @Component and Assuming Scan Is Working

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    // ...
}
~~~

A component-annotated class can be registered by component scanning, but **is excluded from dedicated `@ConfigurationPropertiesScan`**. With constructor-bound records, this can make bean creation behave unexpectedly.

**Fix:** if your intent is configuration properties class scanning, remove `@Component` and use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

### Scenario E — Misspelled Prefix

File:

~~~properties
app.client.connect-timeout=750ms
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.clients")
public record ClientProperties(Duration connectTimeout) {}
~~~

The bean may register successfully, yet fail to bind the expected key because `app.client` differs from `app.clients`. If the field is optional, the mistake can go unnoticed.

**Fix:** standardize prefixes and use validation on required fields.

### Scenario F — Bean Exists, but Type Binding Fails

~~~properties
app.client.max-retries=several
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(int maxRetries) {}
~~~

The scanner found the bean type, but the Binder cannot convert `several` into an `int`. This is a **binding/conversion** error, not a package scan error.

**Fix:** supply a value of the right type or adjust the target type to match your design.

### Scenario G — Validation Failure

~~~properties
app.mail.port=70000
~~~

The record has `@Max(65535) int port`. When validation is enabled, the bean may fail to initialize due to invalid configuration. Do not "fix" this by removing `@ConfigurationPropertiesScan`; fix the bad data or constraint.

## 16. Bean-Not-Found Errors vs. Binding Errors

Based on timing and error messages, you can classify failures:

| Symptom | What to Check First |
| --- | --- |
| `NoSuchBeanDefinitionException` or "required a bean ... could not be found" | Bean registration, scan package, class annotation |
| Bean found, but fields are `null`/`0` | Misspelled prefix/key, missing configuration, defaults and primitive types |
| Message "Failed to bind properties under ..." | Type conversion, constructor, nested config structure, list/map |
| Bean Validation constraint violation message | Value fails `@NotBlank`, `@Min`, `@NotNull`, or another constraint |
| Two beans of the same type found on injection | Duplicate registration paths or multiple bean candidates |
| Bean holds a value different from `application.yml` | Property source precedence, profiles, imports, env vars, or CLI args |
| Config file edited at runtime, but bean unchanged | No refresh/rebind mechanism; scanning is not hot reload |

Again: **`@ConfigurationPropertiesScan` does not automatically reload files and does not fix misspelled keys**. It handles **discovering and registering configuration types**.

## 17. Multi-Module Example: Shared Module + Application Module

Suppose the workspace contains:

~~~text
order-platform/
  common-config/
    src/main/java/
      com/example/shared/config/
        SecurityProperties.java
        RetryProperties.java

  order-service/
    src/main/java/
      com/example/orders/
        OrderApplication.java
        service/OrderService.java
~~~

The `order-service` module depends on `common-config`. If `@ConfigurationPropertiesScan` is placed on `com.example.orders.OrderApplication` without specifying additional base packages, classes in `com.example.shared.config` are out of scope.

You can declare:

~~~java
package com.example.orders;

import com.example.shared.config.RetryProperties;
import com.example.shared.config.SecurityProperties;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan(basePackageClasses = {
    RetryProperties.class,
    SecurityProperties.class
})
public class OrderApplication {}
~~~

Now the scanner scans the packages containing the specified types. If a package contains other `@ConfigurationProperties` types, those may be registered as well.

If a shared module provides a single properties type and wants consumers to decide explicitly which beans to enable, you can use:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(SecurityProperties.class)
public class SecurityModuleConfiguration {}
~~~

To keep modules and starters reusable, clearly define **who owns registering properties beans**: the consuming application or the configuration module. Avoid both scanning a broad package and unnecessarily re-enabling the same types.

## 18. Integration with Profiles and Environment Overrides

`@ConfigurationPropertiesScan` operates at the bean registration layer. Profiles and source ordering are resolved at the Config Data/Environment layer before the Binder reads values.

Suppose the base file is:

~~~properties
# application.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
~~~

Development file:

~~~properties
# application-dev.properties
app.client.base-url=http://localhost:8090
app.client.connect-timeout=500ms
~~~

Run:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

The scanned `ClientProperties` bean can receive values from `application-dev.properties` when the `dev` profile is active and no higher-precedence source overrides them.

If you run:

~~~bash
java -jar order-service.jar \
  --spring.profiles.active=dev \
  --app.client.connect-timeout=250ms
~~~

then the effective timeout typically comes from the command-line argument `250ms`. The scanner does not determine source precedence; it simply ensures the configuration bean exists to receive the bound result.

You can also use JVM system properties:

~~~bash
java -Dapp.client.connect-timeout=2s -jar order-service.jar
~~~

or environment variables following Spring Boot rules:

~~~bash
APP_CLIENT_CONNECTTIMEOUT=2s java -jar order-service.jar
~~~

These sources are evaluated by Spring Boot when determining effective values. A single `ClientProperties` record can remain unchanged even though local, staging, and production pass configuration differently.

## 19. Which Classes Should Carry the Annotation?

Several valid placements:

**On the main class:**

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

**On a @Configuration class:**

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConfigurationPropertiesScan(
    basePackages = "com.example.orders.config"
)
public class PropertiesScanConfiguration {}
~~~

`PropertiesScanConfiguration` must actually be registered by Spring—for instance, within the application's component scan or imported by another configuration. **Simply creating a Java file with `@ConfigurationPropertiesScan` without bringing that class into the ApplicationContext gives the annotation no chance to run.**

**On a plain imported class:**

~~~java
@ConfigurationPropertiesScan(
    basePackageClasses = ClientProperties.class
)
public class ScanDefinition {}
~~~

If `ScanDefinition` is brought into the context through a valid configuration-class processing mechanism, scanning can be triggered. In practice, placing it on the main class or an explicitly registered `@Configuration` class is clearer.

What matters is not the name of the class holding the annotation, but **whether Spring processes that class as a configuration source** and **whether the package scope covers the properties classes**.

## 20. Writing Tests to Verify Scanning and Binding

A simple integration test confirms that `ClientProperties` is registered with the application:

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import com.example.orders.config.ClientProperties;

@SpringBootTest(properties = {
    "app.client.base-url=https://api.example.test",
    "app.client.connect-timeout=900ms",
    "app.client.max-retries=4",
    "app.client.enabled=true"
})
class ClientPropertiesIntegrationTest {

    @Autowired
    ClientProperties properties;

    @Test
    void propertiesBeanIsScannedAndBound() {
        assertThat(properties.baseUrl().getHost())
            .isEqualTo("api.example.test");
        assertThat(properties.connectTimeout())
            .isEqualTo(Duration.ofMillis(900));
        assertThat(properties.maxRetries())
            .isEqualTo(4);
        assertThat(properties.enabled()).isTrue();
    }
}
~~~

This test assumes `OrderApplication` is in a package Spring Boot test discovers automatically and has `@ConfigurationPropertiesScan` with the right scope. `@SpringBootTest(properties = {...})` supplies values to the test environment to verify binding without modifying production config files.

If the test reports the bean does not exist, check scanning first; if the bean exists but value assertions fail, check keys, prefix, types, and source ordering.

### Small Tests Without a Full Application

When you want to test scanning in isolation inside a lightweight context, you can use `ApplicationContextRunner` from Spring Boot Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ScanOnlyTest {
    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfiguration.class)
            .withPropertyValues(
                "app.client.base-url=https://api.example.test",
                "app.client.connect-timeout=900ms",
                "app.client.max-retries=4",
                "app.client.enabled=true"
            );

    @Test
    void registersClientProperties() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(ClientProperties.class);
            assertThat(context.getBean(ClientProperties.class)
                .maxRetries()).isEqualTo(4);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @ConfigurationPropertiesScan(
        basePackageClasses = ClientProperties.class
    )
    static class TestConfiguration {}
}
~~~

In this example, `ClientProperties` is the record from earlier and needs the appropriate package import. The `ApplicationContextRunner` test demonstrates verifying registration in a minimal context; your full project tests still require the Boot test dependency and appropriate runtime conditions.

You can also unit test consumers without running Spring by instantiating the record directly:

~~~java
ClientProperties properties = new ClientProperties(
    URI.create("https://api.example.test"),
    Duration.ofMillis(900),
    4,
    true
);
RemoteClient client = new RemoteClient(properties);
~~~

Unit tests like this test `RemoteClient` logic, **not that scanning or binding works**. To test scanning, you need an actual Spring context.

## 21. Configuration Metadata for IDEs: Does Not Replace Scanning

In a large project, you can add the **Spring Boot Configuration Processor** to generate metadata so IDEs suggest keys and display property descriptions:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

With Maven, an example dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

These examples assume dependency version management compatible with a Spring Boot project. The Configuration Processor produces metadata for developer tooling; **it does not register the `ClientProperties` bean at runtime**. If `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` is missing, IDE autocomplete suggesting `app.client.connect-timeout` does not prove the Spring ApplicationContext contains the bean.

Distinguish clearly:

- **Annotation processor**: supports metadata at build time.
- **`@ConfigurationPropertiesScan`**: supports discovery and registration at startup.
- **Binder**: converts configuration sources into Java objects.
- **Bean Validation**: checks data constraints if configured.

## 22. Diagnosing Configuration Bean Errors in a Running Application

When a business bean fails to inject `ClientProperties`, work through the error in order:

1. **Does the class have `@ConfigurationProperties`?** Is the prefix right?
2. **Is there a registration mechanism?** Is `@ConfigurationPropertiesScan` on a main/config class processed by Spring, or is `@EnableConfigurationProperties` used?
3. **Is the package in scan scope?** If the class is in another module/shared package, add the appropriate base package or enable it directly.
4. **Does the class have `@Component`?** If you want constructor binding via dedicated scanning, avoid mixing the two registration paths.
5. **Is the configuration class hosting the scan actually a configuration source?** A class not picked up by component scan/import will not trigger its annotations.
6. **Is the bean missing, or does it exist but fail binding?** Distinguish missing-bean messages from conversion/validation errors.
7. **Is the key present in Environment?** Check profiles, config imports, startup arguments, and override sources.
8. **Is the target Java type compatible?** E.g., `2s` for `Duration`, integer for `int`, valid URL for `URI`.
9. **Are there duplicate registrations or multiple bean candidates?** For type-based injection, check beans of the same type if an ambiguity error occurs.
10. **Which context is your test loading?** A slice test does not always scan the same packages or auto-configurations as the main application.

Spring Boot Actuator provides the `configprops` endpoint to inspect configuration properties when enabled and properly secured. Never publicly expose endpoints that could leak environment details, and never print passwords, tokens, or private keys to logs just for debugging.

### Do Not Use System.getProperty to Conclude a Bean Wasn't Bound

`System.getProperty("app.client.connect-timeout")` only reads JVM system properties. If the key is supplied via YAML, plain Java returns `null`, while `Environment` and `ClientProperties` still receive the proper value.

To inspect the effective value, check `Environment.getProperty("app.client.connect-timeout")` or the bound bean. To determine which source won, use property-source/origin diagnostics appropriate for a secure environment.

## 23. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "Adding `@ConfigurationProperties` automatically makes a bean appear." | A bean registration mechanism such as scan or enable is required. |
| "`@SpringBootApplication` already scans all `@ConfigurationProperties`." | Component scanning and configuration properties scanning are two separate mechanisms. |
| "`@ConfigurationPropertiesScan` scans the entire classpath." | By default, it scans the annotated class's package and its subpackages. |
| "`basePackageClasses` only registers the exact classes listed." | It uses those classes' packages as scan roots, not as an exact class list. |
| "Adding `@Component` to a record is equivalent to scanning." | No; it changes the registration mechanism and is unsuitable for dedicated constructor binding. |
| "Scanning fixes misspelled keys in YAML." | The Binder still requires matching prefixes and key names. |
| "Scanning makes `application-dev.yml` beat the base file." | Precedence and profiles are handled by the Config Data/Environment system. |
| "Scanning validates every field automatically." | Constraints and appropriate validation setup are required. |
| "Editing the config file automatically re-scans beans." | Scanning and binding normally happen at startup, not hot reload. |
| "Configuration processor replaces scanning." | Build-time metadata and runtime bean registration serve different roles. |
| "A nested record also needs its own `@ConfigurationPropertiesScan`." | The Binder handles nested types as part of the root properties model. |

## 24. Practice Exercises

### Exercise 1 — Default Package

Given:

~~~text
com.example.orders.OrderApplication   @ConfigurationPropertiesScan
com.example.orders.config.ClientProperties  @ConfigurationProperties
~~~

**Question:** Does the default scanner find `ClientProperties`?

**Answer:** Yes, because `com.example.orders.config` is a subpackage of `com.example.orders`.

### Exercise 2 — Sibling Package

Given:

~~~text
com.example.orders.OrderApplication
com.example.shared.config.ClientProperties
~~~

**Question:** With only the default `@ConfigurationPropertiesScan` on `OrderApplication`, is the bean guaranteed to be found?

**Answer:** No. Package `com.example.shared.config` is outside the `com.example.orders` package tree. Use `basePackages`, `basePackageClasses`, or `@EnableConfigurationProperties(ClientProperties.class)`.

### Exercise 3 — Missing Annotation on Record

~~~java
public record ClientProperties(URI baseUrl) {}
~~~

**Question:** With `@ConfigurationPropertiesScan` on the main class, is this record automatically treated as a root config bean?

**Answer:** No, because it lacks `@ConfigurationProperties` defining the root and prefix.

### Exercise 4 — Scanned Record, Values in Properties File

~~~properties
app.retry.max-attempts=5
app.retry.backoff=200ms
~~~

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    int maxAttempts,
    Duration backoff
) {}
~~~

**Question:** When properly scanned and bound, what do the two fields receive?

**Answer:** `maxAttempts=5` and `backoff=Duration.ofMillis(200)`.

### Exercise 5 — Wanting to Register Exactly One Type

**Context:** A module only needs `StorageProperties`; other properties classes in the same package are unrelated.

**Question:** Which annotation expresses single-type registration most clearly?

**Answer:** `@EnableConfigurationProperties(StorageProperties.class)`. `@ConfigurationPropertiesScan(basePackageClasses = StorageProperties.class)` scans the entire package and may pick up other types as well.

### Exercise 6 — Bean Not Found Even Though IDE Autocompletes Keys

The project added `spring-boot-configuration-processor`, the IDE autocompletes `app.client.base-url`, yet Spring reports missing bean `ClientProperties`.

**Answer:** The annotation processor generates build-time metadata, not bean registration. You need scan/enable and proper package configuration.

### Exercise 7 — Binding Error, Not Scan Error

~~~properties
app.client.max-retries=many
~~~

The record has `int maxRetries`, and the scanner discovered the class.

**Answer:** The Binder cannot convert `many` into an integer. Fix the value or target type; widening package scanning will not fix this error.

### Exercise 8 — @Component on an Immutable Record

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl) {}
~~~

**Question:** Is this the recommended way to use constructor-bound configuration properties with scanning?

**Answer:** No. `@Component` changes how the bean is created, and dedicated `@ConfigurationPropertiesScan` excludes component classes. Remove `@Component` and use scan or enable.

### Exercise 9 — Runtime Configuration Differs from Default File

~~~properties
app.client.connect-timeout=3s
~~~

Run:

~~~bash
java -jar order-service.jar --app.client.connect-timeout=500ms
~~~

**Question:** What timeout does the scanned bean receive?

**Answer:** Typically `500ms`, since command-line arguments take precedence over files and binding succeeds. `@ConfigurationPropertiesScan` does not block overrides.

## 25. End-of-Lesson Summary Table

| Goal | How to Do It |
| --- | --- |
| Represent a typed group of keys | `@ConfigurationProperties(prefix = "app.client")` on class/record |
| Auto-discover properties types in packages | `@ConfigurationPropertiesScan` on processed main/config class |
| Scan exact packages by string | `@ConfigurationPropertiesScan(basePackages = "...")` |
| Scan package based on marker type | `@ConfigurationPropertiesScan(basePackageClasses = ClientProperties.class)` |
| Explicitly register one class | `@EnableConfigurationProperties(ClientProperties.class)` |
| Explicitly register multiple types | `@EnableConfigurationProperties({A.class, B.class})` |
| Bind into a library type with setters | `@Bean` combined with `@ConfigurationProperties` on the method |
| Create an immutable record | Dedicated scan/enable so Binder instantiates via constructor |
| Require value constraints | `@Validated` and Jakarta Bean Validation constraints |
| Enable key autocomplete support | `spring-boot-configuration-processor` |
| Test bean scanning and binding | `@SpringBootTest` or `ApplicationContextRunner` |
| Fix "could not be found" | Check registration and packages first |
| Fix "Failed to bind" | Check prefix, keys, types, constructor, and validation |
| Fix unexpected values | Check active profiles and `Environment` precedence |

Keep the sequence in mind: **`@ConfigurationProperties` says "which data belongs to this object"; `@ConfigurationPropertiesScan` says "discover and register configuration objects in these packages"; Spring Boot Binder says "turn effective keys/values into typed Java values."** Once you separate these three steps, you will know when to scan packages, when to register types explicitly, and where to look when a configuration bean fails to appear or receive expected values.
