# Explicit Registration with @EnableConfigurationProperties

In Spring Boot, the `@ConfigurationProperties` annotation describes how to **bind a group of externalized configuration properties** to a Java type. However, simply placing `@ConfigurationProperties` on a class **does not by itself guarantee that the class is registered as a bean** in the ApplicationContext. The application needs a mechanism to recognize and register the configuration type, such as `@ConfigurationPropertiesScan`, creating the bean appropriately, or **`@EnableConfigurationProperties`**.

`@EnableConfigurationProperties` is the **explicit registration** option: the developer specifies the exact `@ConfigurationProperties` classes that a configuration class wants to add to the Spring container. This approach is especially well-suited for infrastructure modules, auto-configurations, integration libraries, setups with few properties classes, or cases where broad package scanning is undesirable.

This lesson covers the lifecycle from configuration file to bean, syntax for registering one or multiple classes, constructor binding with `record`, validation, modular usage, comparison with scanning, and troubleshooting common errors.

## 1. The Problem: Declaring Configuration Is Not Bean Registration

Consider `application.yml`:

~~~yaml
app:
  client:
    base-url: "https://api.example.invalid"
    connect-timeout: 2s
    max-attempts: 3
~~~

We define a clearly structured type:

~~~java
package example.client.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxAttempts
) {}
~~~

`@ConfigurationProperties(prefix = "app.client")` declares that properties under the `app.client` prefix can be bound to `ClientProperties`. For example, `base-url` maps to `baseUrl`, and `connect-timeout` maps to `connectTimeout`.

However, `ClientProperties` has no `@Component`, is not returned by a bean factory method, and has not been declared via a configuration-properties registration mechanism. If you stop there and inject it:

~~~java
import org.springframework.stereotype.Service;

@Service
class ClientService {

    ClientService(ClientProperties properties) {
        // Requires a registered ClientProperties bean.
    }
}
~~~

Spring may report a missing bean of type `ClientProperties` when initializing `ClientService`. This is a **bean registration error**, not automatically a YAML or binding error.

Explicit registration:

~~~java
package example.client.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {
}
~~~

When `ClientConfiguration` is actually loaded into the ApplicationContext, Spring Boot registers `ClientProperties` as a configuration-properties bean and binds it from available property sources.

**Key point to remember:** `@ConfigurationProperties` describes the **type and prefix**; `@EnableConfigurationProperties(ClientProperties.class)` explicitly instructs **Spring to register and bind that type**.

## 2. How Does @EnableConfigurationProperties Work?

A typical flow:

~~~text
application.yml / application.properties
environment variables / command line / Config Data imports
                    |
                    v
              Environment
     PropertySources in precedence order
                    |
                    v
   @Configuration loaded into context
   @EnableConfigurationProperties(
       ClientProperties.class
   )
                    |
                    v
    Register ClientProperties bean
                    |
                    v
            Spring Boot Binder
   - locates keys under prefix app.client
   - maps property names to parameters/fields
   - converts types: URI, Duration, int ...
   - applies validation if configured
                    |
                    v
             ClientProperties
                    |
                    v
              ClientService
~~~

There are three distinct aspects in this diagram:

1. **Configuration sources**: Spring Boot resolves values from files, environment variables, arguments, or additional sources according to precedence rules.
2. **Bean registration**: `@EnableConfigurationProperties` specifies which classes must be present in the container.
3. **Binding and validation**: The Binder converts values into Java types. Constraints can reject invalid values.

A bean can be registered yet fail initialization due to a binding error. Conversely, a completely valid `application.yml` can exist while the application still lacks the `ClientProperties` bean due to missing registration.

## 3. Registering Directly on the @SpringBootApplication Class

For small applications, the annotation can be placed on the main class:

~~~java
package example;

import example.client.config.ClientProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class ClientDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ClientDemoApplication.class, args);
    }
}
~~~

Spring Boot picks up the `ClientProperties` registration in the application context. A service can inject this bean:

~~~java
package example.client;

import example.client.config.ClientProperties;
import org.springframework.stereotype.Service;

@Service
public class RemoteCatalogService {

    private final ClientProperties properties;

    public RemoteCatalogService(ClientProperties properties) {
        this.properties = properties;
    }

    public String description() {
        return "Remote endpoint: " + properties.baseUrl();
    }
}
~~~

The `description()` example only illustrates reading configuration; never use the same pattern to print sensitive values like tokens or passwords to logs or HTTP responses.

### Why Might Explicit Registration Be Needed Even When a Class Is Outside Package Scan?

Suppose the main class is in package `example.web`, while `ClientProperties` resides in `shared.client.config`. Default component scanning from `example.web` will not automatically find classes in other packages.

As long as the application class can import `shared.client.config.ClientProperties`, explicit registration via `@EnableConfigurationProperties(ClientProperties.class)` does not require scanning the entire package containing the properties class. This is a strong advantage in large applications or libraries residing in separate modules.

The requirement is that the class **carrying `@EnableConfigurationProperties` must be loaded by Spring into the context**; placing the annotation on a configuration class that is never scanned or imported has no effect.

## 4. Registering Inside a Dedicated @Configuration Class

When an application has multiple modules, place registrations alongside each module's configuration rather than piling everything onto the main application class.

Example payment module:

~~~java
package example.payment;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentModuleConfiguration {
}
~~~

Data type:

~~~java
package example.payment;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payment.gateway")
public record PaymentProperties(
        URI endpoint,
        Duration timeout,
        boolean enabled
) {}
~~~

YAML source:

~~~yaml
payment:
  gateway:
    enabled: true
    endpoint: "https://gateway.example.invalid"
    timeout: 5s
~~~

A factory receiving typed properties instead of reading keys manually:

~~~java
package example.payment;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
class PaymentClientConfiguration {

    @Bean
    PaymentGatewayClient paymentGatewayClient(
            PaymentProperties properties) {
        return new PaymentGatewayClient(
            properties.endpoint(),
            properties.timeout(),
            properties.enabled()
        );
    }
}
~~~

`PaymentGatewayClient` here is a hypothetical class whose constructor accepts `URI`, `Duration`, and `boolean`. The example shows that a `@Configuration` class can both **register a properties type** and **use that type to construct another business/infrastructure bean**.

In real code, you only need **one single place owning the registration** of `PaymentProperties`. The two configuration classes shown above illustrate two organizational styles; do not include both simultaneously to register the same type.

## 5. Registering Multiple Classes in One Annotation

`@EnableConfigurationProperties` accepts multiple classes:

~~~java
package example.infrastructure;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties({
    DatabasePoolProperties.class,
    StorageProperties.class,
    MonitoringProperties.class
})
public class InfrastructureConfiguration {
}
~~~

Each class declares its own prefix:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "infra.db-pool")
public record DatabasePoolProperties(
        int maxSize,
        Duration acquireTimeout
) {}
~~~

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "infra.storage")
public record StorageProperties(
        String bucketName,
        String region
) {}
~~~

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "infra.monitoring")
public record MonitoringProperties(
        boolean enabled,
        String serviceName
) {}
~~~

Corresponding YAML:

~~~yaml
infra:
  db-pool:
    max-size: 20
    acquire-timeout: 3s
  storage:
    bucket-name: "order-documents"
    region: "apac"
  monitoring:
    enabled: true
    service-name: "order-api"
~~~

Which types get registered is governed by the list in `@EnableConfigurationProperties`; each type binds data under its own prefix. This is not an annotation that "enables all `@ConfigurationProperties` across the project."

If a module has many properties classes and maintaining an explicit list is cumbersome, consider `@ConfigurationPropertiesScan` scoped to specific packages.

## 6. Records and Constructor Binding in Spring Boot 3+

For projects on modern Spring Boot, `record` is a convenient way to model an immutable configuration object:

~~~java
package example.invoice;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "invoice")
public record InvoiceProperties(
        boolean enabled,
        Duration timeout,
        int maxItems
) {}
~~~

Registration:

~~~java
package example.invoice;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InvoiceProperties.class)
class InvoiceConfiguration {
}
~~~

In Spring Boot 3.x, a configuration-properties class with **a single eligible parameterized constructor** (including a record's canonical constructor) is recognized by the binder for constructor binding; normally you do not need `@ConstructorBinding` on a record with one constructor. When multiple constructors exist, you may need to designate the constructor using the API appropriate for your Spring Boot version.

Benefits:

- No setters required.
- Fields are consistent within an initialized object.
- Consuming code has explicit types.
- Configuration is easy to instantiate in tests and pass via constructors.

Usage example:

~~~java
import org.springframework.stereotype.Service;

@Service
public class InvoiceScheduler {

    private final InvoiceProperties properties;

    public InvoiceScheduler(InvoiceProperties properties) {
        this.properties = properties;
    }

    public boolean isEnabled() {
        return properties.enabled();
    }
}
~~~

**Important:** constructor binding for `@ConfigurationProperties` is not standard constructor dependency injection. The constructor parameters of `InvoiceProperties` here are **configuration values**, not Spring service beans. Therefore, do not place `DataSource`, `Repository`, or `HttpClient` as parameters of a configuration record expecting them to be injected as dependencies.

For projects on older Spring Boot versions, constructor-binding syntax and `@ConstructorBinding` placement differ; use the API matching your runtime version. Examples in this lesson target Spring Boot 3+.

## 7. Why Not Annotate a Constructor-Bound Record with @Component?

A confusing pattern:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        int retryCount
) {}
~~~

`@Component` tells Spring to register the type via normal component mechanics. The record's constructor may then be treated as requiring bean dependency injection, even though parameters like `String` and `int` are actually **configuration values**.

For constructor binding, Spring Boot recommends registering via **configuration properties scanning** or **`@EnableConfigurationProperties`**, rather than creating the bean via `@Component`, `@Bean`, or standard Spring bean registration. This is an important boundary between the Binder constructing configuration objects and Spring injecting dependencies to build a component.

Recommended approach:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        int retryCount
) {}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
class ClientConfig {
}
~~~

An alternative for **mutable JavaBean-style** objects is registering the class as a component and letting the binder set properties via setters. Once you choose an immutable record for externalized configuration, stick with the dedicated configuration-properties registration mechanism.

Do not add both `@Component` **and** `@EnableConfigurationProperties(ClientProperties.class)` out of habit, as that can produce duplicate beans or unpredictable behavior.

## 8. Comparing @EnableConfigurationProperties and @ConfigurationPropertiesScan

Both mechanisms let Spring Boot manage `@ConfigurationProperties` types; they differ in **how classes are selected**.

| Criterion | `@EnableConfigurationProperties` | `@ConfigurationPropertiesScan` |
| --- | --- | --- |
| Class selection | Lists exact classes | Scans specified packages |
| Scope | Explicitly declared types | Eligible types found in scan scope |
| Adding a new properties class | Must be added to the list | Discovered automatically if in a scanned package |
| Explicitness | High | Depends on package layout |
| Modules/libraries | Very suitable when types are known upfront | Suitable when managing many types in a package |
| Record/constructor binding | Supported | Supported |
| Depends on package scanning | Does not need to scan the properties package | Requires proper scan scope definition |

**Scanning** example:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan(basePackages = "example.config")
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

**Explicit** example:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties({
    ApiClientProperties.class,
    BillingProperties.class
})
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Neither option is "always better." With a few classes or a library having clear boundaries, explicit registration tells readers exactly what the module registers. With an application containing many config classes under standard packages, scanning reduces manual list maintenance.

**Avoid duplication:** If a properties class is already scanned, you normally should not re-register it via `@EnableConfigurationProperties` elsewhere. A project should adopt a clear convention for where registration lives to minimize ambiguity and ease verification.

## 9. Distinguishing @EnableConfigurationProperties from @ConfigurationProperties

The two annotations have distinct roles:

~~~java
@ConfigurationProperties(prefix = "remote.api")
public record RemoteApiProperties(
        String baseUrl,
        int maxRetries
) {}
~~~

The annotation on the class states that the class holds properties mapped from `remote.api`.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RemoteApiProperties.class)
class RemoteApiConfiguration {
}
~~~

The annotation on the configuration class states that Spring Boot must **register RemoteApiProperties for use in this context**.

You cannot replace `@ConfigurationProperties(prefix = ...)` with only `@EnableConfigurationProperties(...)` without defining the prefix and type structure. Conversely, creating a properties class without a registration mechanism means other beans cannot automatically inject it.

If the same class is both the properties type and annotated with `@Configuration`, the design blurs **configuration data** and **bean declarations**. Usually it is better to separate them:

~~~text
RemoteApiProperties.java     -> Typed configuration data only
RemoteApiConfiguration.java  -> Registers properties and infrastructure beans
RemoteApiClient.java         -> Uses properties for actual work
~~~

This separation prevents configuration types from carrying business logic or unnecessary runtime dependencies.

## 10. When Should @EnableConfigurationProperties Be Placed in Auto-Configuration?

A Spring Boot starter library might provide a client and let users configure it:

~~~yaml
acme:
  client:
    enabled: true
    base-url: "https://api.example.invalid"
    timeout: 3s
~~~

The library defines:

~~~java
package example.autoconfig;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.client")
public record AcmeClientProperties(
        boolean enabled,
        URI baseUrl,
        Duration timeout
) {}
~~~

The library's auto-configuration:

~~~java
package example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
@EnableConfigurationProperties(AcmeClientProperties.class)
class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
            properties.baseUrl(),
            properties.timeout()
        );
    }
}
~~~

`AcmeClient` is a hypothetical client class. This code illustrates the pattern: auto-configuration **explicitly registers its own properties type**, then constructs other beans using those typed properties. The library does not force consuming applications to scan `example.autoconfig`.

For Spring Boot to actually load the auto-configuration, the library must register it according to its Spring Boot version's mechanism. In Spring Boot 3, a standard approach is listing the fully qualified name of the auto-configuration class in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example file contents:

~~~text
example.autoconfig.AcmeClientAutoConfiguration
~~~

Without this registration, the auto-configuration class may not be loaded even if all annotations are written correctly.

### Registering Properties Does Not Force Creating the Client Bean

In the example above, `@EnableConfigurationProperties` registers and binds `AcmeClientProperties`. Whether `AcmeClient` is created depends on `@Bean` and its conditions.

If the client should exist only when `acme.client.enabled=true`, you can add:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "acme.client",
    name = "enabled",
    havingValue = "true"
)
@ConditionalOnMissingBean
AcmeClient acmeClient(AcmeClientProperties properties) {
    return new AcmeClient(
        properties.baseUrl(),
        properties.timeout()
    );
}
~~~

Remember that **a condition on the client bean does not suppress binding/validating the registered properties bean**. If validation requires an endpoint even when the feature is disabled, design defaults and conditional validation appropriately, or place conditions at the registration boundary if you truly do not want to register the module when disabled.

## 11. Combining Validation to Catch Invalid Configuration at Startup

Explicit registration ensures typed properties are created, but does not replace **data constraints**. For example:

~~~yaml
integration:
  base-url: ""
  max-attempts: -5
~~~

Both values can be parsed as strings/integers, yet neither is valid for an HTTP client needing a URL and a positive retry count.

You can add Jakarta Bean Validation (with an appropriate validator dependency, typically the Spring Boot validation starter):

~~~java
package example.integration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "integration")
public record IntegrationProperties(
        @NotBlank String baseUrl,
        @Min(1) int maxAttempts,
        Duration timeout
) {}
~~~

Registration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(IntegrationProperties.class)
class IntegrationConfiguration {
}
~~~

If `base-url` is blank or `max-attempts` is zero or negative, validating the configuration bean can halt startup with an appropriate binding/validation error.

**Keep these distinct:**

1. **Missing bean:** No typed-properties registration mechanism or the configuration class wasn't loaded.
2. **Binding failure:** Bean is registered, but a value cannot be converted to the Java type, e.g., `timeout: "later"` to `Duration`.
3. **Validation failure:** Value converts, but violates constraints, e.g., `max-attempts: -5` with `@Min(1)`.
4. **Client initialization failure:** Typed properties hold valid data, yet the client cannot connect or another dependency is missing.

For hierarchical configs, nested objects needing validation may require `@Valid` as appropriate. Do not assume every child field in a complex configuration is automatically validated merely because the root type has `@Validated`.

### Absent Properties and Primitive Types

A record with `int maxAttempts` may receive the language default or be affected by how the Binder constructs objects when a key is missing. If configuration requires users to supply a value, apply appropriate constraints; when you need to distinguish "undeclared" from "declared as 0," `Integer` expresses absence more clearly than `int`.

Do not rely on `@EnableConfigurationProperties` itself to decide which properties are "required." That annotation **registers**; requiredness and defaults must be designed on the typed properties and validation rules.

## 12. Default Values for Properties Types

In configuration, some properties can have safe defaults:

~~~yaml
service:
  timeout: 3s
  max-retries: 2
~~~

However, a config file might omit some keys. With constructor binding, parameter-level defaults can be specified via the appropriate Spring Boot API. Spring Boot 3 example:

~~~java
package example.service;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        @DefaultValue("3s") Duration timeout,
        @DefaultValue("2") int maxRetries,
        @DefaultValue("false") boolean enabled
) {}
~~~

A `ServiceProperties` registered via `@EnableConfigurationProperties(ServiceProperties.class)` receives these defaults when the corresponding properties are absent.

Guidelines:

- Use defaults when they are **meaningful and safe across all environments**.
- For secrets, mandatory endpoints, or critical safety parameters, validate explicitly instead of supplying dummy values.
- Do not treat defaults as an automatic fallback for mistyped values.
- If an environment provides a value, the Binder attempts to convert it to the target type; it does not silently fall back to a default when content is invalid.

Do not scatter defaults across every service. The properties object is the right place to centralize these decisions.

## 13. How Are Nested Objects and Collections Registered?

Suppose the configuration is:

~~~yaml
store:
  enabled: true
  endpoints:
    - "https://one.example.invalid"
    - "https://two.example.invalid"
  retry:
    attempts: 3
    delay: 250ms
~~~

Java type:

~~~java
package example.store;

import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "store")
public record StoreProperties(
        boolean enabled,
        List<String> endpoints,
        Retry retry
) {
    public record Retry(
            int attempts,
            Duration delay
    ) {}
}
~~~

Register the **root type**:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(StoreProperties.class)
class StoreConfiguration {
}
~~~

Spring Boot Binder processes the `store` prefix and child fields according to the structure. You **do not need** to separately register `StoreProperties.Retry` with `@EnableConfigurationProperties`, because it is just a nested value object, not an independent configuration-properties root bean.

With proper design, an adapter simply injects `StoreProperties`:

~~~java
import org.springframework.stereotype.Service;

@Service
class StoreService {

    private final StoreProperties properties;

    StoreService(StoreProperties properties) {
        this.properties = properties;
    }

    int maxAttempts() {
        return properties.retry().attempts();
    }
}
~~~

If `retry` can be absent, design defaults or validation for that case to avoid calling `retry().attempts()` when the nested value object is null.

## 14. Registering a Configuration Class from an External Module

Suppose `order-service` depends on an internally developed library containing:

~~~text
shared-client/
  src/main/java/shared/client/
    SharedClientProperties.java
    SharedClientConfiguration.java

order-service/
  src/main/java/example/order/
    OrderApplication.java
~~~

In the library:

~~~java
package shared.client;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shared.client")
public record SharedClientProperties(
        String baseUrl,
        Duration timeout
) {}
~~~

~~~java
package shared.client;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(SharedClientProperties.class)
public class SharedClientConfiguration {
}
~~~

The application can import the configuration class:

~~~java
package example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;
import shared.client.SharedClientConfiguration;

@SpringBootApplication
@Import(SharedClientConfiguration.class)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

In this case, `@Import` brings `SharedClientConfiguration` into the context; the module's `@EnableConfigurationProperties` registers `SharedClientProperties`. The app does not need to widen component scanning across all of the library's packages.

Another option is placing `@EnableConfigurationProperties(SharedClientProperties.class)` directly on the application class. What matters is establishing **one clear registration boundary**, rather than creating competing configurations out of habit.

## 15. Why Is @EnableConfigurationProperties Different from @Import?

Both relate to registration, but their roles differ.

`@Import(SomeConfiguration.class)` brings a Spring configuration or supported type into the context through standard import mechanics. `@EnableConfigurationProperties(SomeProperties.class)` is a **specialized mechanism for typed externalized configuration** that integrates the binding pipeline.

For a properties record:

~~~java
@ConfigurationProperties(prefix = "billing")
public record BillingProperties(
        String currency,
        int retryCount
) {}
~~~

Recommended:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(BillingProperties.class)
class BillingConfig {
}
~~~

Do not replace it with:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(BillingProperties.class)
class BillingConfig {
}
~~~

expecting `BillingProperties`'s constructor to automatically receive `billing.currency` and `billing.retry-count` via constructor binding. Standard Spring bean registration is not equivalent to creating typed configuration-properties beans.

For an object created via `@Bean` and then bound via `@ConfigurationProperties` on the method, that is a **different pattern**, typically useful when a third-party class cannot be edited. Do not mix the two patterns without understanding why.

## 16. Configuring Third-Party Objects: When to Use @Bean?

Suppose a library provides a mutable type:

~~~java
public class VendorPool {
    private int maxSize;

    public int getMaxSize() {
        return maxSize;
    }

    public void setMaxSize(int maxSize) {
        this.maxSize = maxSize;
    }
}
~~~

You cannot edit `VendorPool`'s source to add `@ConfigurationProperties`. Spring Boot lets you attach the binding annotation to the factory method:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class VendorConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "vendor.pool")
    VendorPool vendorPool() {
        return new VendorPool();
    }
}
~~~

With:

~~~yaml
vendor:
  pool:
    max-size: 16
~~~

Spring instantiates `VendorPool` via the factory method and the binder applies properties via matching setters.

This is a **separate option** from:

~~~java
@EnableConfigurationProperties(VendorPool.class)
~~~

because `VendorPool` does not necessarily carry `@ConfigurationProperties` on its class and is not designed as an application constructor-bound typed properties class.

In short:

- **Project-owned classes** modeling typed config: `@ConfigurationProperties` on class + `@EnableConfigurationProperties` or scan.
- **Mutable third-party types**: `@Bean` + `@ConfigurationProperties` on the factory method to bind.

The goal is matching the bean creation and binding path to the object type, rather than slapping every annotation on every class.

## 17. Bean Names and Injection Style

When Spring Boot registers a properties class via dedicated mechanisms like `@EnableConfigurationProperties` or scanning, the bean name by convention may combine the prefix and the **fully qualified class name**, e.g.:

~~~text
app.client-example.client.config.ClientProperties
~~~

Do not treat a hardcoded bean name as a primary contract in application code. In most cases, inject by **type**:

~~~java
@Service
class ClientManager {

    private final ClientProperties properties;

    ClientManager(ClientProperties properties) {
        this.properties = properties;
    }
}
~~~

If multiple beans of the same Java type exist in the ApplicationContext, type-based injection can become ambiguous; adjust the design, use appropriate qualifiers, or separate configuration types by purpose.

Do not create multiple `ClientProperties` beans just to bind two different prefixes to the same class expecting `@EnableConfigurationProperties` to distinguish them automatically. Each typed configuration root should usually have a distinct type/prefix, especially if two groups belong to different modules.

Furthermore, a properties bean is not a domain entity or request-scoped object. It typically represents **application-level** configuration values bound during startup.

## 18. Common Error: NoSuchBeanDefinition / No Qualifying Bean

Suppose a service is:

~~~java
@Service
class EmailService {

    EmailService(EmailProperties properties) {
    }
}
~~~

And:

~~~java
@ConfigurationProperties(prefix = "email")
public record EmailProperties(
        String senderName
) {}
~~~

If the context has not registered `EmailProperties`, startup may report a missing bean of this type. Checklist to find the cause:

1. Does `EmailProperties` have `@ConfigurationProperties(prefix = "email")`?
2. Is `@EnableConfigurationProperties(EmailProperties.class)` or appropriate scanning configured?
3. Is the configuration class holding the annotation loaded by Spring Boot into the context?
4. Is there any `@Conditional...` preventing the configuration from activating?
5. Is the code injecting the right `EmailProperties` type or another class with the same simple name in a different package?

Do not "quick-fix" this by adding `@Component` onto a constructor-bound record; that pushes the issue into a different Spring bean creation mechanism.

A missing-bean error that happens only in tests and not when running the app usually stems from a test context loading only a slice of configuration without the class carrying `@EnableConfigurationProperties`.

## 19. Common Error: Wrong Prefix or Unbindable Value

Example:

~~~java
@ConfigurationProperties(prefix = "mail.client")
public record MailClientProperties(
        String host,
        int port
) {}
~~~

YAML:

~~~yaml
mail:
  server:
    host: "smtp.example.invalid"
    port: 2525
~~~

Type registration succeeds, but prefix `mail.client` does not match `mail.server`. Properties `mail.client.host` and `mail.client.port` are not supplied by this YAML.

Do not conclude `@EnableConfigurationProperties` does not work. Check the **prefix and key names**.

Fix:

~~~yaml
mail:
  client:
    host: "smtp.example.invalid"
    port: 2525
~~~

If configured as:

~~~yaml
mail:
  client:
    host: "smtp.example.invalid"
    port: "unknown"
~~~

then `port` cannot convert to `int`. This is a conversion/binding error, not a registration error. The distinction matters because changing registration annotations will not fix bad data.

Special types such as duration, data size, enum, and URI require formats supported by converters. Registration annotations only enable proper binding; they do not replace converters or validation.

## 20. Common Error: Duplicate Beans or Multiple Registration Paths

A confusing setup:

~~~java
@Component
@ConfigurationProperties(prefix = "mail.client")
public class MailClientProperties {
    // mutable fields, getters/setters ...
}
~~~

and simultaneously:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(MailClientProperties.class)
class MailConfig {
}
~~~

The author may accidentally create two registration paths for the same purpose. Depending on context structure and naming, this can cause competing beans, injection ambiguity, or unexpected behavior.

Simple conventions:

- If using **constructor-bound immutable properties**, put `@ConfigurationProperties` on the type and register via `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`.
- If using **JavaBean-style properties as a component** for a specific reason, understand how binding works and avoid adding parallel registrations.
- Across multiple modules, designate which module owns each properties type and how it enters the context.
- Do not annotate properties classes with `@Service`, `@Repository`, or `@Controller`; they are configuration data, not business layers or HTTP endpoints.

**Do not add a `@Bean` returning `new ClientProperties(...)`** just to make the compiler "see" an object. Doing so forfeits dedicated config binding unless you explicitly handle binding properly.

## 21. Testing Explicit Registration with ApplicationContextRunner

When writing auto-configuration or infrastructure modules, `ApplicationContextRunner` from Spring Boot test is a handy tool to spin up a lightweight context and verify registration/binding.

Example:

~~~java
package example.client.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ClientConfigurationTest {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestClientConfig.class);

    @Test
    void registersAndBindsProperties() {
        contextRunner
            .withPropertyValues(
                "app.client.base-url=https://api.example.invalid",
                "app.client.connect-timeout=2s",
                "app.client.max-attempts=3"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(
                    ClientProperties.class);

                ClientProperties properties =
                    context.getBean(ClientProperties.class);

                assertThat(properties.maxAttempts())
                    .isEqualTo(3);
                assertThat(properties.connectTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(2));
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestClientConfig {
    }
}
~~~

Assume the `ClientProperties` record from earlier exists in this package. This test proves three specific things:

1. `TestClientConfig` is loaded into the context.
2. `@EnableConfigurationProperties` registers a single `ClientProperties` bean.
3. Values from property sources are bound into typed fields.

If config fails to load due to test environment or missing converters, inspect the context type and dependencies. `ApplicationContextRunner` provides a useful minimal context, which does not automatically include all auto-configurations of a full application.

### Testing Missing Registration

A test can intentionally build a context containing only a service requiring `ClientProperties` without `ClientConfiguration`. If the service requires that constructor parameter, the context will fail to start.

This test proves the module has a dependency on the properties bean. Do not mask missing registration with a fallback default or try to handle it in the client; the issue lies in **ApplicationContext composition**.

### Testing Invalid Configuration

Example:

~~~java
contextRunner
    .withPropertyValues(
        "app.client.base-url=https://api.example.invalid",
        "app.client.connect-timeout=not-a-duration",
        "app.client.max-attempts=3"
    )
    .run(context -> {
        assertThat(context).hasFailed();
    });
~~~

When the converter tries to convert `not-a-duration` to `Duration`, creating the configuration-properties bean fails. This test helps separate registration errors from conversion errors and catches broken deployment configs before production.

## 22. Testing with @SpringBootTest and Real Application Configuration

In an integration test with a Spring Boot context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "app.client.base-url=https://test.example.invalid",
    "app.client.connect-timeout=1s",
    "app.client.max-attempts=2"
})
class ClientPropertiesIntegrationTest {

    @Autowired
    ClientProperties properties;

    @Test
    void resolvesConfiguration() {
        assertThat(properties.baseUrl().toString())
            .isEqualTo("https://test.example.invalid");
        assertThat(properties.maxAttempts()).isEqualTo(2);
    }
}
~~~

This assumes the test's application class loads the configuration carrying `@EnableConfigurationProperties(ClientProperties.class)`. If the test loads only a slice context excluding that class, import or enable the properties appropriately in the test configuration.

Avoid tests depending on production secrets or live endpoints. Supply dummy values, test containers, or test-specific properties sufficient to exercise application wiring without calling real external services.

## 23. Registration, Binding, and Validation Are Three Independent Responsibilities

A core mental model to keep in mind:

| Question | Primary Mechanism |
| --- | --- |
| Which type represents the property group? | `@ConfigurationProperties(prefix = ...)` |
| Is that type a Spring bean? | `@EnableConfigurationProperties`, scan, or suitable registration |
| Where do values come from? | Spring Environment and PropertySources/Config Data |
| How are key names mapped to fields? | Spring Boot Binder and relaxed binding |
| How are string values converted to Java types? | ConversionService / Binder |
| Are values valid for operational requirements? | Validation / constraint checks |
| Is the client bean created? | `@Bean`, `@Conditional...`, and context conditions |
| Do values update immediately when YAML changes? | Not by default; requires explicit refresh design |

For instance, having `@EnableConfigurationProperties(MailProperties.class)` while missing `mail.host`: bean registration succeeds, whereas binding/validation or mail client construction may fail.

Conversely, having accurate `mail.host` in YAML without registering `MailProperties` means Spring has no bean of that type to inject.

## 24. Profile-Specific Configuration and Precedence

Common base configuration:

~~~yaml
# application.yml
app:
  client:
    base-url: "https://dev.example.invalid"
    connect-timeout: 2s
    max-attempts: 3
~~~

Production profile:

~~~yaml
# application-prod.yml
app:
  client:
    base-url: "https://prod.example.invalid"
    connect-timeout: 5s
~~~

When the application activates the `prod` profile and no higher-precedence source overrides them, the properties bean receives `baseUrl` and `connectTimeout` from production configuration, while `maxAttempts` retains its value from base configuration.

You **do not need**:

~~~java
@EnableConfigurationProperties(
    ProdClientProperties.class
)
~~~

just because the endpoint differs in production, if both environments share the same typed properties structure. A single `ClientProperties`, registered once, receives **values appropriate for the active environment**.

Do not create `LocalClientProperties`, `StagingClientProperties`, `ProdClientProperties` if only URIs or timeouts differ. Profiles and externalized configuration handle **value** differences; the properties type represents the **configuration contract**.

If bean topology genuinely differs, use `@Profile` or `@ConditionalOnProperty` on the integration bean configuration; bean creation conditions and registering typed properties are separate concerns.

## 25. When Should You Use Explicit Registration?

Choose `@EnableConfigurationProperties` when:

- A module has **one or a few** well-known properties types.
- You want the configuration class to state explicitly which configuration contracts the module registers.
- Properties types live outside standard scanned packages.
- Building a library/starter/auto-configuration and you do not want to force applications to scan the library's packages.
- You want to test a small set of configuration in an isolated ApplicationContext.
- You want to keep immutable records free from component-style bean creation.

Consider `@ConfigurationPropertiesScan` when:

- The application has many properties types organized consistently inside packages.
- The list of types changes frequently, making manual enumeration costly to maintain.
- The team has established a clear, easy-to-audit package scan convention.

Consider `@Bean` + `@ConfigurationProperties` on a method when:

- The configuration target is a third-party class requiring setter binding.
- You cannot place annotations on that class.
- You understand it is a normally created bean bound afterwards, not record constructor binding.

## 26. Diagnostic Checklist

When a properties bean does not behave as expected:

1. **Type**: Does the class have `@ConfigurationProperties` with the exact prefix?
2. **Registration**: Is `@EnableConfigurationProperties(Type.class)` or appropriate scanning configured?
3. **Configuration class**: Is the class carrying `@EnableConfigurationProperties` actually loaded by Spring?
4. **Duplicates**: Are `@Component`, scanning, and explicit registration combined to create multiple bean paths?
5. **Property sources**: Do files, profiles, imports, environment variables, and command line contain the exact keys?
6. **Binding**: Does YAML map the right structure, kebab-case names, and Java types?
7. **Conversion**: Do numbers, booleans, `Duration`, `URI`, and enums use supported formats?
8. **Validation**: Are the validation dependency, `@Validated`, and required constraints present?
9. **Bean consumer**: Which type does the service/client inject, and are there multiple beans of that type?
10. **Test context**: Does the test load full configuration, or a slice context that excluded registration?
11. **Deployment**: Is a higher-precedence source overriding the value?
12. **Startup lifecycle**: Do config changes require an explicit restart/refresh?

Some error messages that help classify issues:

~~~text
No qualifying bean of type '...ClientProperties'
    -> Check registration and context composition.

Failed to bind properties under 'app.client'
    -> Check prefix, source structure, and conversion.

Validation failed for ...Properties
    -> Check constraints and concrete values.

No qualifying bean of type '...Client'
    -> Check @Bean factory / @ConditionalOnProperty / @Profile.
~~~

Exact message wording varies by version and exception wrapping; read the root cause instead of stopping at the "Application failed to start" headline.

## 27. Capstone Exercise

**Prompt:** An application needs typed configuration for a worker where max threads is 8, polling interval is 5 seconds, and there is a feature enable flag. Explicitly register the configuration bean without using `@Component` on the record.

**Step 1 — application.yml:**

~~~yaml
worker:
  enabled: true
  max-threads: 8
  polling-interval: 5s
~~~

**Step 2 — typed properties:**

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        boolean enabled,
        int maxThreads,
        Duration pollingInterval
) {}
~~~

**Step 3 — registration:**

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(WorkerProperties.class)
class WorkerConfiguration {
}
~~~

**Step 4 — consumer:**

~~~java
import org.springframework.stereotype.Service;

@Service
class WorkerService {

    private final WorkerProperties properties;

    WorkerService(WorkerProperties properties) {
        this.properties = properties;
    }

    int concurrency() {
        return properties.maxThreads();
    }
}
~~~

**Step 5 — self-check questions:**

- If `@EnableConfigurationProperties(WorkerProperties.class)` is removed and no other scan exists, what error will the service hit?
- If `max-threads: "many"` is set, is that a registration error or a conversion error?
- If `max-threads: -1` is set, what constraint is needed for startup to fail intentionally?
- If production wants `max-threads: 16`, do you need to create `ProdWorkerProperties`?
- If `WorkerProperties` resides in a library module outside package scan, how do you ensure `WorkerConfiguration` is imported/loaded?

Thought check: bean registration, binding, validation, and environment-specific values are separate responsibilities. Do not solve one responsibility by slapping on an annotation meant for another.

## 28. Key Takeaways

`@EnableConfigurationProperties` is used to **explicitly register one or more `@ConfigurationProperties` classes** in the ApplicationContext. It is typically placed on a `@Configuration` or application class loaded by Spring Boot. After registration, the Binder reads properties under the declared prefix, converts types, and constructs a configuration object ready to inject into services and bean factories.

Use this annotation to make clear which module owns typed configuration, especially for immutable records or library/auto-configuration modules. Compared to `@ConfigurationPropertiesScan`, it avoids package-based discovery and presents an exact list. Avoid mixing constructor binding with `@Component`, avoid duplicate registration paths, and never confuse **having a bean** with **having valid configuration**.

**Concise formula: `@ConfigurationProperties` defines the contract; `@EnableConfigurationProperties` registers the contract as a bean; Spring Boot Binder applies values; validation verifies values meet requirements.**