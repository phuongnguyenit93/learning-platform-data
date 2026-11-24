# Limitations of Constructor Binding with Beans Created via @Component or @Bean

In Spring Boot, `@ConfigurationProperties` maps externalized configuration properties into strongly typed Java objects. When the target type is a **record** or immutable class, **constructor binding** is an especially natural fit: instead of creating an empty object and calling setters, the Spring Boot Binder reads values from `Environment`, performs type conversion, and invokes a constructor to build a complete object.

However, there is an error-prone limitation: **`@ConfigurationProperties` constructor binding does not apply to beans created through Spring's regular bean-creation mechanisms such as `@Component`, `@Bean` methods, or `@Import`**. The reason is that those mechanisms have their own constructor-resolution and bean-lifecycle rules, which do not authorize the Binder to treat constructor parameters as properties to bind.

This lesson draws the boundary between both object-creation paths, identifies broken snippets, shows how to register immutable records properly, demonstrates binding setter-based JavaBeans with `@Component` or `@Bean`, explains how to build business beans that need both configuration and dependencies, and provides a troubleshooting workflow.

## 1. Mental Model: Who Is Creating the Bean?

~~~text
             Spring Boot Environment
             (Config Data, -D, env, CLI...)
                         |
                         v
               app.client.* keys
                         |
          +--------------+-------------------+
          |                                  |
          v                                  v
 @ConfigurationProperties             @ConfigurationProperties
 class/record registered              on @Component or
 via @ConfigurationPropertiesScan     on @Bean method
 or @EnableConfigurationProperties          |
          |                                  v
          v                          Spring creates the bean first
 Spring Boot Binder chooses                  |
 constructor and supplies data               v
          |                          Binder binds properties
          v                          via mechanism suited to the
 Record / immutable class             already-created instance
 (constructor binding)                       |
          |                                  v
          v                          JavaBean / mutable settings
 Typed configuration bean                    |
          |                                  |
          +-------------+--------------------+
                        |
                        v
              Business bean uses
              config via injection
~~~

On the left branch, the configuration object is created via **dedicated configuration-properties registration**. On the right branch, Spring uses a normal bean mechanism to instantiate the object first, and then properties are bound onto the eligible object (typically via setters).

Both paths can read the same data sources, yet **they cannot be swapped at the object-instantiation stage**.

### Quick Summary

- `@ConfigurationProperties` declares the prefix and binding contract.
- `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` registers the configuration type for the Binder.
- **Constructor binding** constructs immutable configuration types from property values.
- `@Component` and `@Bean` create Spring beans through the normal path; adding `@ConfigurationProperties` does not turn Spring's constructor injection into constructor binding.
- For objects already instantiated via `@Bean` or `@Component`, consider **JavaBean binding via setters**.
- For immutable objects needing constructor binding, register the type via the dedicated configuration-properties mechanism.

## 2. Standard Example: An Immutable Record Bound via Constructor

Suppose the application has configuration:

~~~yaml
# src/main/resources/application.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 750ms
    max-retries: 3
    enabled: true
~~~

Create the record without `@Component`:

~~~java
// src/main/java/com/example/orders/config/ClientProperties.java
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

Enable scanning for configuration types:

~~~java
// src/main/java/com/example/orders/OrderApplication.java
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

Consumer injects the record:

~~~java
// src/main/java/com/example/orders/client/RemoteClient.java
package com.example.orders.client;

import com.example.orders.config.ClientProperties;
import org.springframework.stereotype.Service;

@Service
public class RemoteClient {
    private final ClientProperties config;

    public RemoteClient(ClientProperties config) {
        this.config = config;
    }

    public boolean canCallRemote() {
        return config.enabled();
    }
}
~~~

With `@ConfigurationPropertiesScan` placed on `com.example.orders.OrderApplication`, the `com.example.orders.config` package falls within scan scope. The Binder can create `ClientProperties` from the effective keys:

| Property | Record Component | Bound Value |
| --- | --- | --- |
| `app.client.base-url` | `baseUrl: URI` | `https://api.example.test` |
| `app.client.connect-timeout` | `connectTimeout: Duration` | 750 milliseconds |
| `app.client.max-retries` | `maxRetries: int` | 3 |
| `app.client.enabled` | `enabled: boolean` | `true` |

Using the record is equivalent in data to an object created via a regular Java constructor:

~~~java
new ClientProperties(
    URI.create("https://api.example.test"),
    Duration.ofMillis(750),
    3,
    true
);
~~~

The `new` snippet only illustrates the post-binding state; in the application, the Binder creates the object and Spring injects that bean into `RemoteClient`.

**Key point:** in this model, no `@Component` or `@Bean` creates `ClientProperties` before the Binder runs. It is registered via `@ConfigurationPropertiesScan`, which fits constructor binding.

## 3. Why Is @Component + Immutable Record Usually Wrong?

Consider this style:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

It looks plausible at first glance: `@Component` so Spring finds the bean, and `@ConfigurationProperties` so the Binder populates values. Yet this **is not** the recommended way to register a constructor-bound record.

With `@Component`, Spring follows **component scanning and normal bean instantiation**. Upon seeing the record constructor, Spring may treat the `URI`, `Duration`, and `int` parameters as dependencies or arguments to supply via Spring's bean creation mechanism, rather than treating them as `app.client.*` keys for the Binder to fill.

The failure may look like:

~~~text
Parameter 0 of constructor in ...
required a bean of type 'java.net.URI'
that could not be found.
~~~

Or a variation stating Spring has no way to provide matching constructor arguments.

### Why Adding @ConfigurationPropertiesScan May Not Fix It

Per Spring Boot's rules, `@ConfigurationPropertiesScan` **does not pick up classes annotated with `@Component` or meta-annotated with `@Component`** as configuration-properties types to instantiate via dedicated binding. Therefore, leaving `@Component` on the record routes the bean down a different registration path than intended.

**Fix:** remove `@Component` from the record, keep `@ConfigurationProperties`, and register it via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

### @Component Is Not Always Incompatible with @ConfigurationProperties

With a **mutable JavaBean** that has a default constructor and setters, `@Component` plus `@ConfigurationProperties` can be a valid path where Spring instantiates the bean and then values are bound. The limitation applies specifically to **constructor binding**, not to using `@ConfigurationProperties` with component beans in every situation.

Distinguish clearly:

- **Misused:** placing `@Component` on an immutable record and expecting the Binder to supply constructor arguments via constructor binding.
- **Valid:** a JavaBean created first by component scanning, with setters for the Binder to populate properties afterward.
- **Preferred for new designs:** configuration properties types should be registered via dedicated scanning or explicit enabling to keep bean categories separated.

## 4. @Bean Creates the Object First: Constructor Binding Does Not Apply

A similar misunderstanding occurs with `@Bean`.

### Misleading Style

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.client")
    ClientProperties clientProperties() {
        return new ClientProperties(
            URI.create("https://fallback.example.test"),
            Duration.ofSeconds(3),
            1
        );
    }
}
~~~

Suppose `ClientProperties` is an immutable record with three components. Here, **the `@Bean` method invokes the constructor itself**, meaning the bean is already instantiated before Spring Boot handles the returned object. Annotating the method with `@ConfigurationProperties` does not turn the three arguments in `new ClientProperties(...)` into parameters the Binder can swap with Config Data.

Record components have no setters. Thus, binding onto an existing instance cannot use constructor binding to rebuild the record. If external values cannot update it, the object may retain the data passed in Java code (and exact failure/binding behavior depends on Binder settings). This is not the way to build immutable configuration-properties beans from YAML.

### Right Pattern 1 — Do Not Construct the Record Inside @Bean

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

The Spring Boot Binder is allowed to construct the record via its constructor from the matching keys.

### Right Pattern 2 — @Bean Creates a Business Bean and Accepts Typed Config

`@Bean` is well suited to building a **client or service** from already-bound configuration:

~~~java
package com.example.orders.config;

import com.example.orders.client.RemoteGateway;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean
    RemoteGateway remoteGateway(ClientProperties properties) {
        return new RemoteGateway(
            properties.baseUrl(),
            properties.connectTimeout(),
            properties.maxRetries()
        );
    }
}
~~~

Here `RemoteGateway` is an illustrative business class defined by the application. `ClientProperties` is still constructed by the Binder through dedicated registration, while `@Bean` constructs the gateway using the bound data.

The flow becomes clear:

~~~text
YAML / properties / env
          |
          v
  ClientProperties
 (constructor binding)
          |
          v
@Bean remoteGateway(ClientProperties p)
          |
          v
  RemoteGateway bean
~~~

This pattern keeps the configuration model immutable while also allowing Spring to inject an HTTP client, executor, metrics registry, or other dependencies into the `@Bean` method when assembling the business bean.

## 5. Valid Pattern: @Bean Combined with JavaBean Setter Binding

`@ConfigurationProperties` on a `@Bean` method works when binding onto an **already-instantiated object**, especially a third-party library type that has a default constructor and getters/setters.

Suppose there is a mutable type:

~~~java
package com.example.orders.legacy;

import java.time.Duration;

public class LegacyPoolSettings {
    private int maximumSize = 8;
    private Duration idleTimeout = Duration.ofSeconds(30);

    public int getMaximumSize() {
        return maximumSize;
    }

    public void setMaximumSize(int maximumSize) {
        this.maximumSize = maximumSize;
    }

    public Duration getIdleTimeout() {
        return idleTimeout;
    }

    public void setIdleTimeout(Duration idleTimeout) {
        this.idleTimeout = idleTimeout;
    }
}
~~~

Use `@Bean` to register and bind onto the instance:

~~~java
package com.example.orders.config;

import com.example.orders.legacy.LegacyPoolSettings;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacyPoolConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.pool")
    LegacyPoolSettings legacyPoolSettings() {
        return new LegacyPoolSettings();
    }
}
~~~

Configuration file:

~~~properties
app.pool.maximum-size=24
app.pool.idle-timeout=10s
~~~

Once the bean is returned by the method, the Binder can call setters to replace the corresponding defaults from configuration sources. For properties not supplied, defaults from field initializers remain in regular binding.

**Note:** `@Bean` is where the object is instantiated, and `@ConfigurationProperties` on the method requests binding onto that object. This is **JavaBean-style binding**, not **constructor binding**. It fits types with setters, not cases where you want the Binder to call a constructor receiving all values.

### Why Is This Example Important for Third-Party Libraries?

You may not be able to edit the source code of a library class to add `@ConfigurationProperties` or constructor binding. Yet if that class exposes writable properties (suitable setters), a `@Bean` returning an instance lets Spring Boot bind keys under a prefix without writing manual setter calls reading `Environment`.

If the library class is immutable and only has parameterized constructors, create **your own typed properties bean** and use it inside a `@Bean` method to construct the library class; do not attempt setter binding on an immutable instance.

## 6. @Component with a Mutable JavaBean: A Different Mechanism from Constructor Binding

An example component created by Spring and then bound:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.worker")
public class WorkerSettings {
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

Data:

~~~yaml
app:
  worker:
    concurrency: 12
    poll-interval: 2s
~~~

If the component is within Spring's component scan scope, Spring instantiates `WorkerSettings` with a suitable no-args constructor, and then `@ConfigurationProperties` processing binds values via setters.

Fundamentally, it is still:

1. Spring creates the bean via the `@Component` mechanism.
2. Property binding is applied to the created instance.
3. Consumers inject the instance after the bean is initialized.

It does not go through the path where the Binder directly calls a constructor with `app.worker.*` keys to construct an immutable object.

### When Should You Avoid @Component for Settings?

When you want a record or immutable class, need control over constructor binding, want a clean separation between configuration beans and business beans, or want centralized defaults/validation on a typed config contract, use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

Using `@Component` with mutable settings can make sense in legacy code, yet you should not reflexively "add `@Component` to fix a missing-bean error." That changes the bean-creation path and can mask the real reason scanning missed the class.

## 7. @Import and Manual BeanDefinitions Share Similar Limitations

Beyond `@Component` and `@Bean`, beans created through other standard Spring mechanisms—such as using `@Import` to bring a configuration class or bean definition into the context—do not automatically receive `@ConfigurationProperties` constructor binding either.

Distinguish two cases:

- **Using `@Import(SomeConfiguration.class)` to register a configuration class**, after which `@Bean` or component scanning creates the beans it declares. Those beans follow their respective bean-creation mechanisms.
- **Using `@EnableConfigurationProperties(MyProperties.class)` on a configuration class**: even if that configuration class itself was brought into the context via `@Import`, `MyProperties` is still registered via the mechanism dedicated to configuration properties.

Thus, the issue is not "`@Import` is always wrong," but **who instantiates the constructor-bound properties instance**. If you want the Binder to instantiate the object directly from property values, use the dedicated registration mechanism for `@ConfigurationProperties`.

Do not assume any class brought into the `ApplicationContext` by any mechanism behaves identically to a properly scanned configuration-properties bean.

## 8. Choosing @ConfigurationPropertiesScan or @EnableConfigurationProperties?

Both are proper paths for registering typed properties classes, including immutable records.

### Scanning by Package

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

If `OrderApplication` is in `com.example.orders`, the scanner defaults to finding `@ConfigurationProperties` types in that package and its subpackages. This is convenient when an application has many configuration groups.

Scanning other packages:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan(basePackages = {
    "com.example.orders.config",
    "com.example.shared.config"
})
public class OrderApplication {}
~~~

Or specifying a marker class's package:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan(basePackageClasses = ClientProperties.class)
public class OrderApplication {}
~~~

`basePackageClasses` selects **the marker type's package**, not just that single type. Other `@ConfigurationProperties` classes in the same scope can also be discovered.

### Registering a Specific Type

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {}
~~~

With `@EnableConfigurationProperties`, you name the exact type to register, regardless of which package the scanner covers.

### Comparison Table

| Need | Choice |
| --- | --- |
| Application with many properties types in clear packages | `@ConfigurationPropertiesScan` |
| Starter/config module registering a specific type | `@EnableConfigurationProperties(ThatType.class)` |
| Constructor-bound immutable typed record | Dedicated scan or explicit enable |
| Business bean needing typed config | Inject config bean into `@Bean`/business constructor |
| Mutable library class with setters | `@Bean` + `@ConfigurationProperties` on method |
| Pre-instantiated mutable settings component | `@Component` + `@ConfigurationProperties` can bind via setters |

Do not register the same type via both scanning and enabling "just in case." Projects should choose a consistent strategy and investigate if bean-candidate or duplicate bean-definition errors occur.

## 9. Why Are Constructor Injection and Constructor Binding Not the Same?

Both appear as Java constructors, yet their inputs originate from two different systems.

### Spring Constructor Injection

~~~java
@Service
public class OrderService {
    private final RemoteClient remoteClient;

    public OrderService(RemoteClient remoteClient) {
        this.remoteClient = remoteClient;
    }
}
~~~

Spring looks up a `RemoteClient` bean in the ApplicationContext to pass into `OrderService`'s constructor. This is **dependency injection**: constructor parameters represent Spring bean dependencies.

### Spring Boot Constructor Binding

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

The Spring Boot Binder reads `app.client.base-url`, `app.client.connect-timeout`, and `app.client.max-retries` from configuration sources, converts types, and calls the constructor. Parameters represent **configuration values**, not Spring beans looked up in the container.

### How the Difference Causes Failures

If you put `@Component` on `ClientProperties`, Spring tries to inject `URI` or `Duration` as dependencies. Yet you have not defined `URI` or `Duration` beans; you only have values in YAML. As a result, a missing-bean error can occur even when the YAML file is completely valid.

The solution is routing each responsibility down its proper path:

~~~text
Binder -> ClientProperties(URI, Duration, int)
Spring DI -> RemoteClient(ClientProperties)
~~~

Do not use a `@Component` class constructor expecting to receive both property values from the Binder and Spring beans from DI as if the two mechanisms merge automatically.

## 10. How Should You Design When You Need Both Config Values and Dependencies?

Suppose an HTTP gateway needs `WebClient.Builder` or a client factory Spring bean, while also needing base URL, timeout, and retry settings from configuration. A clean design splits them:

**Step 1 — Configuration properties hold only data:**

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

**Step 2 — Register typed properties:**

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

**Step 3 — Business bean uses constructor injection for both the config bean and other dependencies:**

~~~java
package com.example.orders.client;

import com.example.orders.config.RemoteProperties;
import org.springframework.stereotype.Service;

@Service
public class GatewayService {
    private final RemoteProperties settings;
    private final RequestSigner signer;

    public GatewayService(
        RemoteProperties settings,
        RequestSigner signer
    ) {
        this.settings = settings;
        this.signer = signer;
    }

    public boolean isRetryConfigured() {
        return settings.maxRetries() > 0;
    }
}
~~~

`RequestSigner` is an illustrative business type that must have a matching registered bean. `GatewayService` is a Spring component whose constructor receives **two bean dependencies**. `RemoteProperties` is already created by the Binder, so its inner values do not need to become individual Spring beans.

If you prefer a factory method instead of `@Service`:

~~~java
@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean
    GatewayService gatewayService(
        RemoteProperties settings,
        RequestSigner signer
    ) {
        return new GatewayService(settings, signer);
    }
}
~~~

**There is no need** to annotate `GatewayService` with `@ConfigurationProperties`; it is a business bean consuming configuration, not a data type for the Binder to construct from YAML.

## 11. @ConfigurationProperties on @Bean Methods: Same Keys, Different Lifecycle

With the same `app.pool` prefix, how the object is created depends on the registration path:

| Design | Who Creates the Instance? | Typical Binding Style | Best Fit |
| --- | --- | --- | --- |
| `@ConfigurationProperties` on record + scan | Spring Boot Binder | Constructor binding | Immutable records/classes |
| `@ConfigurationProperties` on JavaBean + scan | Dedicated configuration properties mechanism | Setter binding | Mutable classes |
| `@Component` + `@ConfigurationProperties` | Spring component mechanism | Binds onto already-created bean | Mutable beans with setters |
| `@Bean` + `@ConfigurationProperties` | Factory method returns instance | Binds onto already-created instance | Mutable types, third-party libraries |
| `@Bean` returning business object, taking typed properties bean | Spring factory method | Does not bind business object directly | Clients/services needing config values |

For a mutable class, multiple options may work functionally, yet dedicated registration keeps roles clearer. For an immutable record, choosing the right registration path is crucial because constructor binding is not an arbitrary post-instantiation step.

## 12. What If a Record or Class Has Multiple Constructors?

In modern Spring Boot, a class/record with a single eligible parameterized constructor can be inferred for constructor binding. Yet when a data type has **multiple constructors** or a more complex design, the Binder may need an explicit constructor selection depending on the Spring Boot version.

Example of an immutable class with one constructor receiving configuration values:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.retry")
public class RetryProperties {
    private final int maxAttempts;
    private final Duration backoff;

    public RetryProperties(int maxAttempts, Duration backoff) {
        this.maxAttempts = maxAttempts;
        this.backoff = backoff;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public Duration getBackoff() {
        return backoff;
    }
}
~~~

Register via dedicated scan or enable so the Binder can invoke the constructor from `app.retry.max-attempts` and `app.retry.backoff`.

If the class has multiple constructors and needs to pick one binding constructor, Spring Boot 3.x supports `@ConstructorBinding` on the chosen constructor (the annotation's package in newer versions differs from older examples):

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.retry")
public class RetryProperties {
    private final int maxAttempts;
    private final Duration backoff;

    @ConstructorBinding
    public RetryProperties(int maxAttempts, Duration backoff) {
        this.maxAttempts = maxAttempts;
        this.backoff = backoff;
    }

    // Example auxiliary constructor for pure Java usage
    public RetryProperties() {
        this(3, Duration.ofSeconds(1));
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public Duration getBackoff() {
        return backoff;
    }
}
~~~

Depending on the version, detecting constructor parameter names may require build metadata such as `-parameters`. In modern Boot projects using standard plugins and build setups, many cases are handled automatically; if binding reports parameter names cannot be resolved, inspect compiler configuration.

**Even with `@ConstructorBinding`, do not conclude it makes a `@Component` or `@Bean`-created bean bind via constructor.** The annotation only participates in the Binder workflow for types registered via the proper mechanism.

## 13. Default Values with Constructor Binding

A constructor-bound immutable record has no setters and cannot hold defaults in the "default constructor then set each field" style of a JavaBean. The Spring Boot Binder provides `@DefaultValue` for constructor-binding parameters.

Example:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    @DefaultValue("3") int maxAttempts,
    @DefaultValue("200ms") Duration backoff
) {}
~~~

When `app.retry.max-attempts` or `app.retry.backoff` is absent from configuration sources, the Binder can apply these defaults per its rules. Using defaults is a deliberate choice and should not mask missing essential keys.

With a mutable JavaBean, defaults can sit in field initializers:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public class RetrySettings {
    private int maxAttempts = 3;
    private Duration backoff = Duration.ofMillis(200);

    // Corresponding getters and setters
}
~~~

If this class is created via `@Component` or `@Bean` and then bound via setters, default values persist when keys are omitted. **Do not copy a record's default approach onto a mutable class assuming every bean-creation mechanism behaves identically.**

### Absent Key Is Not Empty Value or Invalid Type

A missing key can use a default; an existing key holding a value that cannot convert to `Duration` can still cause binding to fail. `@DefaultValue` is not a tool to ignore syntactically invalid configuration values.

Example:

~~~properties
# Value cannot be converted to a valid Duration
app.retry.backoff=tomorrow
~~~

When binding `Duration`, the failure is a conversion error. Fix the data, rather than merely adding `@DefaultValue("200ms")`.

## 14. Validation: Proper Registration Alone Is Not Enough

Constructor binding creates a typed object, yet **does not automatically enforce all business constraints**. If you need a required URL, non-negative retry count, or non-null timeout, you can use Jakarta Bean Validation when the project configures a suitable provider.

Example:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    @NotNull URI baseUrl,
    @NotNull Duration connectTimeout,
    @Min(0) int maxRetries
) {}
~~~

Common dependency in Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

When the bean is registered via scan or enable, the Binder creates the instance and validation checks the constraints. If `base-url` is missing or `max-retries=-1`, initialization can fail with a binding/validation error, catching misconfiguration early.

Distinguish three error categories:

- **Missing bean:** scanner/enable did not register the configuration type.
- **Object creation failure:** wrong instantiation path, constructor binding misused with `@Component`/`@Bean`, missing type or converter.
- **Invalid values:** missing property, wrong type, or constraint violation after binding.

Fixing the right layer prevents misguided workarounds like adding `@Component` to a record just to "get rid of the missing-bean error."

## 15. @NestedConfigurationProperty and Nested Objects

An immutable record can contain nested configuration:

~~~yaml
app:
  outbound:
    base-url: https://gateway.example.test
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.outbound")
public record OutboundProperties(
    URI baseUrl,
    Retry retry
) {
    public record Retry(
        int maxAttempts,
        Duration backoff
    ) {}
}
~~~

If `OutboundProperties` is registered via the dedicated configuration-properties mechanism, the Binder processes nested `Retry` as part of the data structure. There is no need to turn `Retry` into a `@Component` or separate Spring bean just because it is a record with a constructor.

If a nested object needs its own validation, use `@Valid` on the component holding the nested object and constraints inside the nested type, with bean validation enabled.

**Do not confuse nested records with dependency injection:** `Retry` is nested data inside a configuration object; it is not a dependency for Spring to look up by type in the ApplicationContext.

## 16. Binding Does Not Depend on Whether Values Come from YAML or -D

A `ClientProperties` created by the Binder still reads effective values from Spring Boot's `Environment`. Example:

~~~properties
# application.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
app.client.max-retries=2
~~~

Run:

~~~bash
java -Dapp.client.connect-timeout=800ms -jar order-service.jar
~~~

The JVM system property can override the file for `app.client.connect-timeout`, provided no higher-precedence source overrides it. The record binds with an 800 ms timeout.

Or:

~~~bash
java -jar order-service.jar --app.client.max-retries=5
~~~

The command-line property can override retry count to 5. Regardless of input source, the record uses the same prefix and types.

An environment variable following Spring Boot conventions is typically used as:

~~~bash
APP_CLIENT_CONNECTTIMEOUT=1s java -jar order-service.jar
~~~

Sources must use key names compatible with relaxed binding. For example, `app.client.connect-timeout` in a file maps to `connectTimeout` in Java.

**Whether a configuration source takes precedence is a matter of `Environment` and Config Data**, not whether the bean was created via scan or enable. The limitation of constructor binding lies in **the bean-creation mechanism**, not in how values are written in files.

## 17. Real-World Errors and Diagnostic Clues

### Error A — Record Has Both @Component and @ConfigurationProperties

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl, Duration timeout) {}
~~~

**Symptom:** missing dependency bean such as `URI`, or constructor cannot be resolved by Spring.

**Cause:** Spring follows component construction instead of Binder constructor binding.

**Fix:** remove `@Component`, add dedicated registration via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(ClientProperties.class)`.

### Error B — @Bean Returns a New Record with Hardcoded Defaults

~~~java
@Bean
@ConfigurationProperties(prefix = "app.client")
ClientProperties clientProperties() {
    return new ClientProperties(
        URI.create("https://fallback.example.test"),
        Duration.ofSeconds(3)
    );
}
~~~

**Symptom:** YAML has values yet the object does not receive the expected fields; binding errors may also occur depending on types.

**Cause:** the method already constructed an immutable instance, the Binder has no setters, and constructor binding is not how `@Bean` methods work.

**Fix:** let the Binder create the record from configuration sources via scan/enable; or use a `@Bean` method to create a **business bean** from an already-bound typed properties bean.

### Error C — JavaBean @Bean Has Setters Yet Still Does Not Bind

~~~java
@Bean
@ConfigurationProperties(prefix = "app.pool")
LegacyPoolSettings pool() {
    return new LegacyPoolSettings();
}
~~~

**Symptom:** fields keep their defaults.

**Check:** does the class have properly named public setters; does the `app.pool` prefix match keys like `app.pool.maximum-size`; is the configuration actually loaded and not overridden by another source?

Do not conclude from this error that "`@Bean` never works with `@ConfigurationProperties`": `@Bean` supports binding onto suitable instances, it simply **does not use constructor binding**.

### Error D — Record Is Valid Yet No Bean Exists

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl) {}
~~~

**Symptom:** message `required a bean of type ClientProperties that could not be found`.

**Possible causes:** missing `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`; scan placed in a package that does not cover the record.

**Fix:** register properly, do not add `@Component` to the record.

### Error E — Record Is Scanned Yet Fails to Bind Values

~~~properties
app.client.max-retries=many
~~~

The record expects `int maxRetries`.

**Symptom:** `Failed to bind properties under ...` or conversion error.

**Cause:** data cannot convert to `int`, unrelated to `@Component` or `@Bean`. Fix the value to a valid number.

### Error F — Component Constructor Takes Both a Dependency and @Value

~~~java
@Component
public class SomeService {
    public SomeService(
        OtherService other,
        @Value("${app.worker.concurrency:4}") int concurrency
    ) {
        // ...
    }
}
~~~

**Is this `@ConfigurationProperties` constructor binding?** No. This is **regular Spring constructor injection** with one argument resolved via `@Value` and one argument being a Spring bean. This pattern can be valid for business components, yet it does not turn `SomeService` into an immutable configuration-properties object.

If many properties belong to the same group, extracting a typed `WorkerProperties` bean and injecting it into the service is cleaner.

## 18. When Can a @Bean Method Accept Constructor-Bound Properties?

A factory method can accept an **already-bound configuration-properties bean** as a parameter:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientFactoryConfiguration {

    @Bean
    RemoteClient remoteClient(
        ClientProperties clientProperties,
        ClientMetrics clientMetrics
    ) {
        return new RemoteClient(
            clientProperties.baseUrl(),
            clientProperties.connectTimeout(),
            clientMetrics
        );
    }
}
~~~

`RemoteClient` and `ClientMetrics` are illustrative types requiring appropriate definitions and beans in the application. The relationship is:

- `ClientProperties`: created via dedicated configuration-properties registration using constructor binding.
- `ClientMetrics`: another dependency created by Spring.
- `RemoteClient`: created by the factory method from both.

Nothing prevents `@Bean` from **consuming** a constructor-bound object. The limitation is only against using `@Bean` to **instantiate the properties object itself when you want Binder constructor binding**.

This design pattern is commonly used when configuring a third-party library client that cannot be annotated with `@ConfigurationProperties`.

## 19. Choosing the Right Implementation per Scenario

| Scenario | Suitable Approach |
| --- | --- |
| Need an immutable record with URI, Duration, int | `@ConfigurationProperties` + scan/enable |
| Immutable class whose constructor only takes property values | Dedicated registration for the Binder |
| A service component needing timeout and a repository bean | Inject typed properties bean and repository via constructor |
| Library provides a mutable settings object with setters | `@Bean` + `@ConfigurationProperties` on method |
| Legacy project has mutable `@Component` properties beans | Can keep setter binding if compatibility requires |
| Migrating from mutable bean to record | Remove `@Component`/record-creating factory, add scan/enable |
| Package has many typed configurations | `@ConfigurationPropertiesScan` |
| Starter wants to register a single type | `@EnableConfigurationProperties(TheType.class)` |
| Nested object is just child config data | Let the Binder handle nested objects |
| Need defaults for a constructor-bound record | `@DefaultValue` and appropriate validation |
| Need fail-fast when keys are missing | `@Validated` + Bean Validation |
| Key overridden by another source | Check property source precedence, do not change bean mechanism |
| Need config changes when file is edited | Design dedicated refresh/rebind; constructor binding does not hot-reload |

## 20. Designing a Migration from Mutable @Component to a Record

Suppose legacy code is:

~~~java
@Component
@ConfigurationProperties(prefix = "app.export")
public class ExportSettings {
    private String directory;
    private int batchSize = 100;

    public String getDirectory() {
        return directory;
    }

    public void setDirectory(String directory) {
        this.directory = directory;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }
}
~~~

To migrate to immutability, you can use a record:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.export")
public record ExportProperties(
    String directory,
    @DefaultValue("100") int batchSize
) {}
~~~

Change the registration:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

Update the consumer:

~~~java
@Service
public class ExportService {
    private final ExportProperties properties;

    public ExportService(ExportProperties properties) {
        this.properties = properties;
    }

    public int batchSize() {
        return properties.batchSize();
    }
}
~~~

Understand the order of changes:

1. Create the immutable properties model representing the same key names.
2. Move existing defaults from field initializers to the default mechanism for constructor-bound types.
3. Do not add `@Component` to the record.
4. Register the record via scan or enable.
5. Update consumers to inject the record and call record accessors.
6. If both types share the same prefix during transition, explicitly manage which bean is actually active; avoid keeping two ambiguous registration paths.

If you need to check that `directory` is non-blank or `batchSize` is positive, add validation. In multi-module applications, verify the record's package falls inside the scan scope.

## 21. Writing Tests to Separate Registration and Binding

An integration test can prove the record is scanned/enabled and receives values from the environment:

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
    "app.client.max-retries=5",
    "app.client.enabled=true"
})
class ClientPropertiesTest {

    @Autowired
    ClientProperties config;

    @Test
    void constructorBoundRecordHasValues() {
        assertThat(config.baseUrl().getHost())
            .isEqualTo("api.example.test");
        assertThat(config.connectTimeout())
            .isEqualTo(Duration.ofMillis(900));
        assertThat(config.maxRetries()).isEqualTo(5);
        assertThat(config.enabled()).isTrue();
    }
}
~~~

The test assumes the main class has `@ConfigurationPropertiesScan` covering the right package or `@EnableConfigurationProperties`, and that Spring Boot Test dependencies are present. If the test fails to inject the bean, inspect the **registration path**. If the bean exists with wrong values, inspect **binding/precedence**.

### Testing a Mutable Library Class Created via @Bean

Suppose `LegacyPoolSettings` has setters as shown earlier. You can spin up a test context and assert the bean receives `app.pool.maximum-size=24`. That test has a different purpose from the record test: it proves **setter binding on an already-created bean**, not that the Binder invokes a constructor on the library type.

To unit test a consumer without starting Spring, construct the typed properties record directly:

~~~java
ClientProperties props = new ClientProperties(
    URI.create("https://api.example.test"),
    Duration.ofMillis(900),
    5,
    true
);

RemoteClient client = new RemoteClient(props);
~~~

This snippet assumes a matching `RemoteClient(ClientProperties)` constructor is defined. Plain Java tests prove the consumer uses data properly, yet **do not prove scanning or binding**. To verify registration, a real Spring context is needed.

## 22. Can Every Immutable Class Use Constructor Binding?

Not automatically. The Spring Boot Binder needs a way to determine the constructor, property names, target types, and suitable conversions. Check:

- Is the class annotated with `@ConfigurationProperties(prefix = "...")` and registered via the proper mechanism?
- Does the constructor have parameters matching configuration keys?
- Can parameter names be resolved by the Binder from build metadata or appropriate annotations?
- Do types like `Duration`, `URI`, enums, and nested objects have suitable converters/binders?
- With multiple constructors, is the binding constructor designated if required by the version?
- Are any required properties missing or mistyped?
- Does the class also carry `@Component` or get created via `@Bean`?

An immutable class with overly complex constructor logic, Spring bean dependencies, or network calls is not a good candidate for a typed configuration model. **Configuration properties objects should model data**, while creating clients or opening connections belongs in separate business beans.

### Do Not Confuse Validation with Constructor Injection

A constructor containing:

~~~java
if (maxRetries < 0) {
    throw new IllegalArgumentException("maxRetries must be nonnegative");
}
~~~

can validate inputs itself; however, putting this code inside a `@Component` bean's constructor does not turn the object into constructor-bound `@ConfigurationProperties`. To have the system bind structured keys/values, you still need dedicated registration.

## 23. Reading Startup Errors by Root-Cause Category

| Observed Error | Likely Cause | Resolution |
| --- | --- | --- |
| Spring asks for `URI`, `Duration` beans on a `@Component` record | Using Spring constructor injection instead of Binder constructor binding | Remove `@Component`, scan/enable record |
| `required a bean of type ClientProperties ... could not be found` | Not registered or scanned wrong package | Check `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` |
| `Failed to bind properties under 'app.client'` | Binder entered binding yet value/constructor/type failed | Check keys, values, constructor, converters, defaults |
| `No qualifying bean ... expected single matching bean but found ...` | Multiple beans of same type or overlapping registration paths | Check bean names, qualifiers, and registration strategy |
| Mutable `@Bean` keeps defaults | Wrong setters, prefix, file, or precedence | Check getters/setters, value sources, prefix |
| `@Bean` record does not reflect YAML changes | Immutable instance created by Java factory; no constructor binding | Create record via dedicated Binder, switch factory to consume record |
| `@NotNull`/`@Min` fails | Missing data or constraint violation | Fix source/validation, not scanning |
| Editing config file at runtime does not update object | No dedicated refresh/rebind mechanism | Design reload mechanism, do not rely on scanning |

### Short Troubleshooting Workflow

1. Identify whether the failing object is a **configuration properties bean** or a **business bean**.
2. Check how the object is **registered**: scan/enable, component, factory method, import.
3. If constructor binding is desired, confirm it is **not instantiated via `@Component` or `@Bean`**.
4. Check constructors/record components and the corresponding prefix.
5. Check effective values in `Environment`, including profiles, imports, environment variables, `-D`, and command-line arguments.
6. Check conversion and validation.
7. When testing, separate integration tests verifying bean creation/binding from business unit tests.

Do not take "Spring Boot read the YAML" as proof that a record was registered down the right path; the two steps are distinct.

## 24. Misconceptions to Discard

| Misconception | Accurate Understanding |
| --- | --- |
| "Having `@ConfigurationProperties` makes constructors bind automatically." | You must also register the type via the proper mechanism and have an eligible constructor. |
| "`@Component` on a record helps the Binder find parameter values." | Component constructor injection is not dedicated constructor binding. |
| "`@Bean` plus `@ConfigurationProperties` is always forbidden." | `@Bean` supports binding onto suitable mutable instances; the limitation is constructor binding. |
| "`@Bean` returns a record and the Binder re-calls the constructor with YAML values." | The factory already created the instance; there is no constructor binding step to replace that instance. |
| "`@ConfigurationPropertiesScan` picks up every `@Component` properties class." | Component types are excluded from dedicated properties scanning. |
| "`@EnableConfigurationProperties` is only for mutable classes." | It also registers immutable types eligible for Binder constructor binding. |
| "A Spring bean's constructor parameters match keys so the Binder understands them." | Spring DI constructor parameters are dependencies, not property values by default. |
| "`@Bean` cannot accept a config record as a parameter." | You can inject a properties bean already created by the Binder into a factory method. |
| "A nested record needs its own `@Component`." | The Binder processes nested values as part of the root configuration model. |
| "If the config bean was created, every value must be valid." | You still need type checking, defaults, and validation. |
| "Editing YAML at runtime recreates immutable beans automatically." | A separate refresh/rebind mechanism is required. |
| "On errors, just add `@Component` so Spring sees the class." | Adding `@Component` can route the class onto an unsuitable bean-creation path. |

## 25. Exercises: Identify the Object-Creation Mechanism

### Exercise 1 — Record Registered via Dedicated Scanning

~~~java
@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(Duration ttl, int maximumSize) {}
~~~

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class App {}
~~~

**Question:** if the record is in a scanned package, is this a candidate for constructor binding?

**Answer:** yes. The record is registered via `@ConfigurationPropertiesScan`, which fits Spring Boot's dedicated constructor binding when keys and types match.

### Exercise 2 — Record with @Component Added

~~~java
@Component
@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(Duration ttl, int maximumSize) {}
~~~

**Question:** is this equivalent to Exercise 1?

**Answer:** no. Spring's component mechanism creates the bean via constructor injection. The dedicated scanner skips component classes when registering constructor-bound properties. Remove `@Component` and register via scan/enable.

### Exercise 3 — Mutable Bean from a @Bean Method

~~~java
@Bean
@ConfigurationProperties(prefix = "app.pool")
LegacyPoolSettings settings() {
    return new LegacyPoolSettings();
}
~~~

`LegacyPoolSettings` has a default constructor and setter `setMaximumSize`.

**Question:** can it receive `app.pool.maximum-size=16`?

**Answer:** yes, via binding onto the mutable instance after the method creates the bean; this is not constructor binding.

### Exercise 4 — Immutable Record Instantiated with new in @Bean

~~~java
@Bean
@ConfigurationProperties(prefix = "app.client")
ClientProperties client() {
    return new ClientProperties(
        URI.create("https://fallback.example.test"),
        Duration.ofSeconds(5),
        1
    );
}
~~~

**Question:** does the Binder replace the three arguments passed to `new` using YAML?

**Answer:** there is no constructor binding on a bean already created by a factory method. Use scan/enable so the Binder builds the record, and have `@Bean` accept the bound record only if assembling a business bean.

### Exercise 5 — A Service Needing Configuration and a Dependency

~~~java
@Service
public class ExportService {
    ExportService(
        ExportProperties properties,
        StorageClient storageClient
    ) {
        // ...
    }
}
~~~

**Question:** what mechanism does this constructor use?

**Answer:** Spring constructor injection for two beans, `ExportProperties` and `StorageClient`. `ExportProperties` may have been created earlier by Binder constructor binding, yet `ExportService`'s constructor itself is not Binder constructor binding.

### Exercise 6 — @EnableConfigurationProperties

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
class ClientConfiguration {}
~~~

**Question:** must `ClientProperties` live in a package scanned by `@ConfigurationPropertiesScan`?

**Answer:** no. Enabling explicitly registers the type; the class only needs to be on the classpath and the configuration class processed by Spring.

### Exercise 7 — Migrating from Mutable to Record

Previously `@Component @ConfigurationProperties(prefix = "app.worker")` had setter `setConcurrency`; now switched to:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int concurrency) {}
~~~

**Question:** what must change?

**Answer:** remove `@Component`, add scan/enable, update consumers if needed, and move defaults/validation to the appropriate constructor-bound model. Do not merely delete the setter while leaving the same bean-creation path intact.

### Exercise 8 — Type Mismatch Is Not a Registration Issue

~~~properties
app.worker.concurrency=many
~~~

The record uses `int concurrency` and is already scanned properly.

**Question:** is adding `@Component` the right fix?

**Answer:** no. The error is that `many` cannot convert to `int`; fix the data or choose an appropriate type.

## 26. Final Decision Table

| What Do You Want to Do? | Right Mechanism |
| --- | --- |
| Bind keys into an immutable record's constructor | `@ConfigurationProperties` + `@ConfigurationPropertiesScan` |
| Bind keys into an immutable class's constructor | Dedicated scan/enable, eligible constructor |
| Register one exact properties type | `@EnableConfigurationProperties(Type.class)` |
| Have Spring create a regular component | `@Component`/`@Service` + constructor dependency injection |
| Bind properties onto a mutable component with setters | `@Component` + `@ConfigurationProperties` can be used |
| Instantiate a library settings object and set properties | `@Bean` + `@ConfigurationProperties` on method |
| Create a client from immutable config and other dependencies | `@Bean Client(ImmutableProperties, OtherBean)` |
| Supply defaults for a constructor-bound record | `@DefaultValue` or valid constructor design |
| Validate critical config at startup | `@Validated` and Bean Validation |
| Diagnose a missing-bean error | Check registration, scanned packages, and stereotype annotations |
| Diagnose a binder error | Check prefix, keys, conversion, constructor, and validation |

**Core conclusion:** `@ConfigurationProperties` constructor binding only fits when the Spring Boot Binder is invoked via the **dedicated configuration-properties registration path**. Beans created by Spring via `@Component` or `@Bean` can still receive configuration by binding onto mutable instances, yet **do not use constructor binding in the same way**. For records or immutable classes, let the Binder create the typed config bean; for business services or clients, inject that typed config bean into a regular Spring constructor or `@Bean` factory method. Maintaining this boundary prevents startup errors, keeps configuration strongly typed, and makes projects easier to test.
