# `@ConfigurationProperties` for Grouping Configuration by Prefix

When a Spring Boot application has many related configuration parameters — such as external service addresses, timeouts, retry counts, or operating modes — reading each value individually with `@Value` quickly scatters the code. Property key strings appear across multiple services, type conversion becomes hard to manage, and mandatory configuration constraints are difficult to check in one place.

**`@ConfigurationProperties`** solves this problem: Spring Boot binds properties sharing the same *prefix* into a structured, strongly typed Java object. Services simply inject that object via constructor injection.

For example, the configuration group:

~~~yaml
app:
  payment:
    endpoint: https://payments.example.test
    connect-timeout: 2s
    read-timeout: 5s
    retry:
      max-attempts: 3
      backoff: 500ms
~~~

can become a `PaymentProperties` object with `URI`, `Duration`, and a nested `Retry` group. Importantly, the service does not need to know whether values came from YAML, a properties file, an environment variable, or a command-line argument.

This lesson explains how Spring Boot binds configuration, ways to register configuration beans, mutable JavaBeans vs. immutable records, relaxed binding, conversion, validation, defaults, testing, and common pitfalls.

## 1. From scattered @Value fields to a configuration contract

An initial example:

~~~java
@Service
public class PaymentClient {

    public PaymentClient(
            @Value("${app.payment.endpoint}") String endpoint,
            @Value("${app.payment.connect-timeout}") String connectTimeout,
            @Value("${app.payment.read-timeout}") String readTimeout,
            @Value("${app.payment.retry.max-attempts}") int maxAttempts) {
        // Initialize client...
    }
}
~~~

This style works for a few small properties, but as the count grows, problems emerge:

- Many classes must know string property names.
- Type conversion and default value logic are easily duplicated.
- It is hard to see the full configuration of a module at a glance.
- There is no single place to validate constraints across values.
- During refactoring, the compiler cannot catch misspelled property strings.
- Service constructors can grow long just from configuration parameters.

With `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI endpoint,
        Duration connectTimeout,
        Duration readTimeout,
        Retry retry
) {
    public record Retry(int maxAttempts, Duration backoff) {
    }
}
~~~

The service becomes:

~~~java
@Service
public class PaymentClient {

    private final PaymentProperties properties;

    public PaymentClient(PaymentProperties properties) {
        this.properties = properties;
    }

    public URI endpoint() {
        return properties.endpoint();
    }
}
~~~

This is the **type-safe configuration** model: configuration is a named, typed, structured dependency instead of unrelated strings mixed into business logic.

## 2. Binding mechanism and the meaning of prefix

The annotation belongs to Spring Boot:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
~~~

`@ConfigurationProperties(prefix = "app.payment")` tells the binder to read the group of properties starting with `app.payment` from `Environment`.

~~~text
application.yml / application.properties
         + environment variables
         + command-line arguments
                    |
                    v
              Environment
                    |
                    v
           Configuration Binder
             prefix: app.payment
                    |
                    v
             PaymentProperties
                    |
                    v
                PaymentClient
~~~

For example, a configuration source in properties format:

~~~properties
app.payment.endpoint=https://payments.example.test
app.payment.connect-timeout=2s
app.payment.read-timeout=5s
app.payment.retry.max-attempts=3
app.payment.retry.backoff=500ms
~~~

The binder can construct the corresponding structure:

~~~text
PaymentProperties
├── endpoint = https://payments.example.test
├── connectTimeout = PT2S
├── readTimeout = PT5S
└── retry
    ├── maxAttempts = 3
    └── backoff = PT0.5S
~~~

`PT2S` and `PT0.5S` are `Duration` representations for two seconds and half a second.

**The prefix is not a bean name, package name, or file path.** It is the leading part of the logical configuration key. For instance, `app.mail.from-address` does not belong to the `app.payment` group.

### 2.1. Binding does not read only application.yml

`Environment` can hold multiple `PropertySource`s. Spring Boot processes configuration from files, environment variables, command-line arguments, and other sources in precedence order.

If the same property appears in multiple sources, the higher-precedence source can override the lower one. The Java class used for binding remains unchanged.

### 2.2. The annotation alone is not enough

The class:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(URI endpoint) {
}
~~~

will not necessarily become a bean from the annotation alone. It must be registered via a mechanism such as `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or an appropriate bean registration path.

## 3. Writing mutable configuration in JavaBean style

With a JavaBean having a no-args constructor and setters, Spring Boot can bind each property after creating the instance:

~~~java
package com.example.payment;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private URI endpoint;
    private Duration connectTimeout = Duration.ofSeconds(2);
    private Duration readTimeout = Duration.ofSeconds(5);

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

Here:

- `endpoint` receives the value from `app.payment.endpoint`.
- `connectTimeout` receives `app.payment.connect-timeout`.
- `readTimeout` receives `app.payment.read-timeout`.
- Initializer values act as defaults when the corresponding property is not provided.

JavaBean style is familiar in older systems, though the object is mutable and requires boilerplate getters/setters. If you want an immutable object after binding, records or constructor binding are usually a better fit.

## 4. Registering with @ConfigurationPropertiesScan

In an application with many configuration groups, scanning is convenient:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Package structure:

~~~text
com.example
├── Application.java
├── payment
│   └── PaymentProperties.java
└── mail
    └── MailProperties.java
~~~

Because `Application` sits in the parent package, appropriate scan configuration discovers `@ConfigurationProperties` classes in subpackages.

You can specify an explicit scope:

~~~java
@ConfigurationPropertiesScan(
        basePackages = "com.example.shared.config"
)
~~~

or use a marker class to avoid hard-coding package strings:

~~~java
@ConfigurationPropertiesScan(
        basePackageClasses = SharedConfigMarker.class
)
~~~

`SharedConfigMarker` is a class defined in the package to scan.

Note: `@ConfigurationPropertiesScan` is not the same as `@SpringBootApplication`'s component scan; it exists to discover and register configuration properties classes. Classes already registered as `@Component` are not processed through the same regular properties-scan path.

## 5. Explicit registration with @EnableConfigurationProperties

When you only want to register specific configuration types:

~~~java
package com.example.payment;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {
}
~~~

Or:

~~~java
@EnableConfigurationProperties({
        PaymentProperties.class,
        MailProperties.class
})
~~~

This approach works especially well for:

- Starter auto-configurations.
- Modules with dedicated configuration.
- Test contexts needing a specific properties class.
- Components where scanning an entire package is undesirable.

| Aspect | `@ConfigurationPropertiesScan` | `@EnableConfigurationProperties` |
| --- | --- | --- |
| Type selection | Scans packages | Lists specific classes |
| Adding a new properties type | Discovered automatically if in scan scope | Must be added explicitly |
| Typical use | Applications | Starters, modules, tests |
| Supports constructor-bound classes | Yes, on supporting Boot lines | Yes, on supporting Boot lines |
| Requires `@Component` | No | No |

Pick one consistent registration path for each properties group.

## 6. @Component and JavaBean binding

A JavaBean class can be registered as a component:

~~~java
@Component
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private String endpoint;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

Spring instantiates the bean via standard component creation, and the binder populates properties afterward.

However, if the class is a record or an immutable class designed for constructor binding, **do not** also annotate it with `@Component`. Spring may treat constructor parameters as bean dependencies to autowire from the container rather than configuration values.

For records, use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

## 7. @Bean combined with @ConfigurationProperties

When a class belongs to an external library and you cannot add annotations to it, you can place `@ConfigurationProperties` on a factory method:

~~~java
@Configuration(proxyBeanMethods = false)
public class ExternalClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.external")
    public ExternalClientOptions externalClientOptions() {
        return new ExternalClientOptions();
    }
}
~~~

`ExternalClientOptions` is an illustrative type with setters or writable properties for the binder to populate.

This pattern works well for third-party classes with JavaBean-style properties. If the external type is immutable or lacks suitable binding support, define your own `ExternalProperties` class and use a factory method to build the client:

~~~java
@Bean
ExternalClient externalClient(ExternalProperties properties) {
    return ExternalClient.builder()
            .endpoint(properties.endpoint())
            .timeout(properties.timeout())
            .build();
}
~~~

That way, configuration stays under your application's control, while the library class receives already converted and validated data.

## 8. When to choose which registration approach?

If you are writing a standard Spring Boot application and want to use record properties, `@ConfigurationPropertiesScan` is usually straightforward. If you are writing auto-configuration that exposes an explicit configuration contract, use `@EnableConfigurationProperties`.

If you are working with a mutable library class having setters, `@Bean` with `@ConfigurationProperties` can be helpful. `@Component` still works with mutable JavaBeans, though it should not be mixed with constructor-bound records.

Most importantly, **the properties class must actually be registered**. When a service reports it cannot inject a properties bean, check registration before suspecting YAML contents.

## 9. Immutable records and constructor binding

In modern Spring Boot, a record is a clean way to represent immutable configuration:

~~~java
package com.example.payment;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI endpoint,
        Duration connectTimeout,
        Duration readTimeout
) {
}
~~~

YAML:

~~~yaml
app:
  payment:
    endpoint: https://payments.example.test
    connect-timeout: 2s
    read-timeout: 5s
~~~

The binder uses the record's canonical constructor to create the populated instance. Services then call accessors such as `endpoint()` and `readTimeout()`. No setters are needed, and callers cannot accidentally mutate a timeout via a setter call at runtime.

### 9.1. Is @ConstructorBinding required?

In Spring Boot 3.x, a configuration properties class with a single parameterized constructor is normally inferred as constructor binding; a standard record **does not need** `@ConstructorBinding`.

If a class has multiple constructors, one constructor may need `@ConstructorBinding` to indicate which constructor is used for binding:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private final URI endpoint;

    @ConstructorBinding
    public PaymentProperties(URI endpoint) {
        this.endpoint = endpoint;
    }

    public URI getEndpoint() {
        return endpoint;
    }
}
~~~

In Spring Boot 3.x, import:

~~~java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
~~~

In Spring Boot 2.x, this annotation had a different history and package depending on the version. When maintaining legacy code, use the API matching your actual Boot dependency rather than copying imports across major versions.

### 9.2. Why not use @Component on a record?

The example below is not a recommended choice:

~~~java
@Component
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(URI endpoint, Duration timeout) {
}
~~~

Spring may attempt to resolve `URI` and `Duration` as beans to autowire into the component's constructor. That differs from constructor binding from `Environment` and usually prevents the context from starting as expected.

Solution: remove `@Component` and use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(PaymentProperties.class)`.

## 10. Relaxed binding: Java names and property names do not need to match literally

The Spring Boot Binder supports **relaxed binding**. The same property can be expressed in different formats across compatible configuration sources.

Java:

~~~java
public record PaymentProperties(Duration connectTimeout) {
}
~~~

Property forms normally recognized by the binder:

~~~properties
app.payment.connect-timeout=2s
app.payment.connectTimeout=2s
app.payment.connect_timeout=2s
~~~

For consistency, use **kebab-case** in `application.yml`, `application.properties`, and documentation:

~~~properties
app.payment.connect-timeout=2s
~~~

In Java, the component/field name is `connectTimeout` in camelCase.

### 10.1. Environment variable rules

For a canonical property name, the standard rule to convert it into an OS environment variable is:

1. Replace dots with underscores.
2. Remove dashes inside each segment.
3. Convert the name to uppercase.

For example:

| Canonical property | Environment variable |
| --- | --- |
| `app.payment.endpoint` | `APP_PAYMENT_ENDPOINT` |
| `app.payment.read-timeout` | `APP_PAYMENT_READTIMEOUT` |
| `app.payment.retry.max-attempts` | `APP_PAYMENT_RETRY_MAXATTEMPTS` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |

Common trap: `read-timeout` becomes `READTIMEOUT`; do not assume an extra underscore is inserted between `READ` and `TIMEOUT`. Underscores represent segment boundaries originally separated by dots.

Test actual env values in your deployment environment to confirm container tools, shells, or CI/CD pass them properly.

### 10.2. Lists from the environment

With configuration:

~~~yaml
app:
  routing:
    regions:
      - ap-southeast-1
      - eu-west-1
~~~

elements can be specified by index:

~~~text
APP_ROUTING_REGIONS_0=ap-southeast-1
APP_ROUTING_REGIONS_1=eu-west-1
~~~

The index rule in environment variables places digits surrounded by underscores.

### 10.3. Avoid creating confusing aliases

Relaxed binding does not mean you should constantly vary property spellings. Publish one canonical name, keep it stable in operations documentation, and follow the matching conversion rule for each property source.

## 11. Type conversion during binding

`@ConfigurationProperties` does not bind only strings. Spring Boot provides conversion for many common types:

~~~java
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        boolean enabled,
        int maxConnections,
        Duration requestTimeout,
        DataSize maxUploadSize,
        URI endpoint,
        List<String> allowedRegions,
        Map<String, String> tags
) {
}
~~~

YAML example:

~~~yaml
app:
  storage:
    enabled: true
    max-connections: 20
    request-timeout: 750ms
    max-upload-size: 20MB
    endpoint: https://objects.example.test
    allowed-regions:
      - ap-southeast-1
      - eu-west-1
    tags:
      owner: platform
      environment: staging
~~~

Common type categories:

| Java type | Configuration example | Result |
| --- | --- | --- |
| `boolean` | `true` | On/off flag |
| `int`, `long` | `20` | Integer |
| `String` | `staging` | Text |
| `Duration` | `750ms`, `2s`, `5m` | Duration |
| `DataSize` | `20MB`, `512KB` | Data size |
| `URI` | `https://objects.example.test` | URI |
| Enum | `STRICT` | An enum value |
| `List<T>` | YAML sequence | List |
| `Map<K,V>` | YAML mapping | Key/value map |
| Nested object | `retry.max-attempts` | Nested group |

`DataSize` belongs to Spring Framework:

~~~java
import org.springframework.util.unit.DataSize;
~~~

### 11.1. Specify time units explicitly

For example:

~~~properties
app.payment.connect-timeout=2s
app.payment.retry.backoff=500ms
~~~

The binder converts them to `Duration`. Using suffixes like `ms`, `s`, `m`, and `h` avoids guessing whether a bare number means milliseconds or seconds. In some situations, `@DurationUnit` specifies the default unit when a number lacks a suffix.

### 11.2. Specify size units explicitly

For example:

~~~properties
app.storage.max-upload-size=20MB
~~~

The `DataSize` type expresses intent far better than an integer whose byte unit is unexplained.

### 11.3. Enums

~~~java
public enum RetryPolicy {
    NONE, FIXED, EXPONENTIAL
}
~~~

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(RetryPolicy retryPolicy) {
}
~~~

~~~properties
app.payment.retry-policy=EXPONENTIAL
~~~

If a value cannot convert to the enum or target type, Boot can report a binding error at startup instead of letting an invalid string travel deep into business logic.

## 12. Nested properties: subgroups, lists, and maps

A large module often has multi-level configuration.

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        boolean enabled,
        String fromAddress,
        Retry retry
) {
    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {
    }
}
~~~

YAML:

~~~yaml
app:
  notification:
    enabled: true
    from-address: noreply@example.test
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

The service can call:

~~~java
int maxAttempts = properties.retry().maxAttempts();
Duration backoff = properties.retry().backoff();
~~~

This assumes `retry` is present. If configuration allows omitting the entire nested group, declare a default or validation; do not blindly dereference a potentially null object.

### 12.1. Nested objects in JavaBeans

With a JavaBean, you can initialize the child object directly:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {

    private Retry retry = new Retry();

    public Retry getRetry() {
        return retry;
    }

    public void setRetry(Retry retry) {
        this.retry = retry;
    }

    public static class Retry {

        private int maxAttempts = 3;
        private Duration backoff = Duration.ofMillis(250);

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public Duration getBackoff() {
            return backoff;
        }

        public void setBackoff(Duration backoff) {
            this.backoff = backoff;
        }
    }
}
~~~

If the file omits `retry`, the child object is already initialized and retains its declared defaults.

### 12.2. Lists of objects

YAML:

~~~yaml
app:
  routing:
    targets:
      - name: primary
        url: https://primary.example.test
      - name: backup
        url: https://backup.example.test
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(List<Target> targets) {

    public record Target(String name, URI url) {
    }
}
~~~

The binder builds the list of `Target`s with values from YAML.

**Watch out when overriding lists:** across configuration sources at different precedence levels, Spring Boot normally takes the list from the higher-precedence source rather than accumulating items from multiple lists. Do not assume `application-prod.yml` will simply append items to the list in `application.yml`.

### 12.3. Maps and special keys

Maps fit named configuration pairs well:

~~~yaml
app:
  routing:
    labels:
      owner: platform
      team: billing
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(Map<String, String> labels) {
}
~~~

If map keys contain special characters or must preserve dots/characters literally, the binder has specific map-key rules, including bracket notation in some cases. Test actual keys, especially when keys represent external identifiers.

## 13. Default values: JavaBean initializers and @DefaultValue

Some properties should have clear defaults, such as timeouts or retry counts. Other properties, especially critical endpoints or secrets, should require an explicit value.

### 13.1. JavaBean field initializers

~~~java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private Duration readTimeout = Duration.ofSeconds(5);

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

If `app.payment.read-timeout` is absent, the field can keep its initialized value.

### 13.2. Records and @DefaultValue

With Spring Boot 3.x and supporting lines:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @DefaultValue("5s") Duration readTimeout,
        @DefaultValue("3") int maxAttempts
) {
}
~~~

If the property is not provided, the binder can use this default during constructor binding.

### 13.3. Nested objects with defaults

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @DefaultValue Retry retry
) {
    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("250ms") Duration backoff
    ) {
    }
}
~~~

An empty `@DefaultValue` on the `Retry` component can instruct the binder to instantiate the nested object even when no child keys exist, and then apply defaults for each nested component.

Do not set arbitrary defaults just to let an application boot in production with dummy endpoints or invalid credentials.

## 14. Validation: failing fast on invalid configuration

Binding to the right type does not guarantee the configuration is valid for business rules. For example, retry count might be 0, an email string blank, or an endpoint missing.

You can use **Bean Validation** to check constraints while creating the configuration properties bean.

Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Record example:

~~~java
import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        @NotNull URI endpoint,
        @NotBlank String fromAddress,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry
) {
    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff
    ) {
    }
}
~~~

If configured:

~~~yaml
app:
  mail:
    endpoint: https://mail.example.test
    from-address: ""
    request-timeout: 5s
    retry:
      max-attempts: 0
      backoff: 250ms
~~~

then `fromAddress` violates `@NotBlank` and `maxAttempts` violates `@Min(1)`. Startup can fail and report which constraints were violated.

### 14.1. @Valid and nested validation

`@Valid` lets validation descend into the `Retry` child object. `@NotNull` checks for the presence of the object.

If you place constraints on the outer class yet forget `@Valid`, constraints inside nested objects may not be evaluated as expected.

### 14.2. Binding errors differ from validation errors

Value:

~~~properties
app.mail.request-timeout=not-a-duration
~~~

cannot convert to `Duration`: this is a conversion/binding error.

Value:

~~~properties
app.mail.retry.max-attempts=0
~~~

converts to `int`, yet violates `@Min(1)`: this is a validation error.

When reading startup exceptions, look for the offending property name, received value, expected type, and violated constraint.

### 14.3. Jakarta vs. javax by Boot version

Spring Boot 3 and later use the Jakarta namespace such as `jakarta.validation.constraints.NotBlank`. In Spring Boot 2 applications, Bean Validation usually uses `javax.validation.*`. Do not mix imports across major versions.

## 15. Injecting properties into services via constructor

Once the properties bean is registered, services inject it like any other dependency:

~~~java
@Service
public class MailClient {

    private final MailProperties mailProperties;

    public MailClient(MailProperties mailProperties) {
        this.mailProperties = mailProperties;
    }

    public URI destination() {
        return mailProperties.endpoint();
    }

    public Duration timeout() {
        return mailProperties.requestTimeout();
    }
}
~~~

This approach ensures:

- Services do not depend directly on `Environment`.
- String property keys are not duplicated in multiple places.
- Unit tests simply construct a `MailProperties` instance with desired values.
- IDEs can refactor Java symbols instead of scanning arbitrary strings.
- Validation and type conversion are consolidated at the configuration boundary.

A properties object should stick to holding configuration data; do not put HTTP calls, database writes, or business workflows inside its getters or setters.

## 16. Comparing @ConfigurationProperties and @Value

`@Value` is not wrong; it is useful when only a couple of simple values are needed. However, as configuration grows, `@ConfigurationProperties` is usually easier to manage.

| Aspect | `@Value` | `@ConfigurationProperties` |
| --- | --- | --- |
| Usage | On fields, constructor parameters, methods | On classes or `@Bean` methods |
| Scope | Usually a single value | Group of values sharing a prefix |
| Property names | String expressions | One prefix, matching Java fields |
| Nested objects | Needs custom handling | Supported directly |
| Lists and maps | Possible, but requires care with expressions | Binder provides structured support |
| Type safety | Depends on parameter/field | Explicit class contract |
| Group-wide validation | Not its primary strength | Supports Bean Validation |
| Relaxed binding | Do not assume Binder equivalence | Designed for relaxed binding |
| Metadata/IDE completion | Limited by usage | Has configuration metadata processor |
| SpEL | Can evaluate SpEL | Does not treat properties binder as a SpEL template engine |

`@Value` example:

~~~java
@Value("${app.title:My Application}")
private String title;
~~~

If the application needs only a static title, this is straightforward.

When a feature has an endpoint, retry policy, timeouts, credentials, and validation, however, a `@ConfigurationProperties` group expresses the configuration contract far better.

### 16.1. When to keep @Value

- Simple, independent values.
- A small component needing a single property.
- Genuine need for a SpEL expression.

Do not mechanically create a configuration class for every single string. The goal is grouping **functionally related properties**, not inflating the file count.

## 17. Configuration sources and precedence

`@ConfigurationProperties` receives values from `Environment`. Thus, when a property name appears in multiple sources, Spring Boot's precedence decides which source wins.

`application.yml`:

~~~yaml
app:
  payment:
    read-timeout: 5s
~~~

If the runtime environment provides:

~~~text
APP_PAYMENT_READTIMEOUT=10s
~~~

then in a standard Boot setup, the OS environment variable has higher precedence than packaged `application.yml` and can override the timeout to 10 seconds.

Command line:

~~~bash
java -jar app.jar --app.payment.read-timeout=20s
~~~

normally has higher precedence than configuration files and OS environment in Boot's default setup.

However, when a project adds custom `PropertySource`s, a config server, or specialized setup, check the actual source order.

### 17.1. Profile-specific files

For example:

~~~text
application.yml
application-dev.yml
application-prod.yml
~~~

`application.yml`:

~~~yaml
app:
  payment:
    connect-timeout: 2s
    read-timeout: 5s
~~~

`application-prod.yml`:

~~~yaml
app:
  payment:
    read-timeout: 10s
~~~

When the `prod` profile is enabled and files are loaded per Spring Boot's mechanism, the profile's `read-timeout` can override the base; `connect-timeout` continues using the base unless overridden.

Java code stays unchanged:

~~~java
public PaymentClient(PaymentProperties properties) {
    this.properties = properties;
}
~~~

This is a practical advantage: the same artifact can run across environments with different settings.

### 17.2. Lists across multiple sources do not automatically concatenate

If base config has:

~~~yaml
app:
  routing:
    targets:
      - name: primary
        url: https://primary.example.test
~~~

and the production profile redefines `targets`, the binder normally uses the entire list from the higher-precedence source. Do not assume the two lists concatenate.

If you need granular overrides by identifier, `Map<String, Target>` is sometimes a better fit than `List<Target>`.

### 17.3. Modifying files at runtime does not auto-refresh beans

If you update `application.yml` while the application is running, `@ConfigurationProperties` does not guarantee beans rebind immediately. Runtime configuration refresh requires a dedicated mechanism, usually involving change detection, bean coordination, and consistency guarantees.

Do not use properties objects as arbitrarily mutable runtime state stores.

## 18. Metadata helps IDEs suggest properties

Spring Boot includes a configuration processor that can generate metadata for `@ConfigurationProperties` classes, enabling autocompletion and descriptions in IDEs.

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

With Gradle:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

During build, the processor can generate:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Simplified metadata structure example:

~~~json
{
  "groups": [
    {
      "name": "app.payment",
      "type": "com.example.payment.PaymentProperties"
    }
  ],
  "properties": [
    {
      "name": "app.payment.read-timeout",
      "type": "java.time.Duration"
    }
  ]
}
~~~

Actual metadata may include source types, descriptions, default values, and other fields depending on the source code.

### 18.1. Metadata does not replace the runtime binder

The configuration processor serves development and tooling; runtime binding is performed by Spring Boot's Binder and `Environment`.

The fact that an IDE does not suggest a property does not mean it cannot bind. Conversely, IDE suggestions do not prove the deployment environment has supplied valid values.

### 18.2. Property descriptions and hints

Write Javadoc explaining non-obvious fields, such as whether a timeout is a connect timeout or request timeout, recommended units, and which values are required.

For libraries providing starters, good metadata lets users discover supported property names without reading the source directly.

## 19. Testing binding with ApplicationContextRunner

A useful test must verify **the object created by the Binder**, not just manual constructor calls.

Spring Boot provides `ApplicationContextRunner` to spin up a lightweight context:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI endpoint,
        Duration readTimeout,
        @DefaultValue("3") int maxAttempts
) {
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class PaymentPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsPropertiesByPrefix() {
        runner.withPropertyValues(
                "app.payment.endpoint=https://payments.example.test",
                "app.payment.read-timeout=750ms"
        ).run(context -> {
            PaymentProperties props =
                    context.getBean(PaymentProperties.class);

            assertThat(props.endpoint())
                    .isEqualTo(URI.create("https://payments.example.test"));
            assertThat(props.readTimeout())
                    .isEqualTo(Duration.ofMillis(750));
            assertThat(props.maxAttempts())
                    .isEqualTo(3);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PaymentProperties.class)
    static class TestConfig {
    }
}
~~~

This test needs the corresponding `spring-boot-test`, JUnit, and AssertJ dependencies. In Spring Boot applications, `spring-boot-starter-test` normally provides what is needed.

### 19.1. Testing conversion failures

For example:

~~~java
@Test
void rejectsInvalidDuration() {
    runner.withPropertyValues(
            "app.payment.endpoint=https://payments.example.test",
            "app.payment.read-timeout=not-a-duration"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

The value `not-a-duration` does not fit `Duration`. The context should reflect a binding failure instead of silently inventing an arbitrary value.

### 19.2. Testing validation failures

If the class is annotated with `@Validated` and has `@NotBlank`, `@Min`, or `@NotNull`, test cases such as:

- Missing endpoint.
- Blank sender.
- Retry equal to 0.
- Negative timeout if business rules reject it.

A Bean Validation provider must be on the test classpath. Tests should confirm the context fails and, where appropriate, that error details point to the expected property.

### 19.3. Testing nested objects and lists

If a class has nested retry settings, check the values after binding:

~~~java
assertThat(props.retry().maxAttempts()).isEqualTo(3);
assertThat(props.retry().backoff())
        .isEqualTo(Duration.ofMillis(250));
~~~

If there is a list of targets, check the element count, order if significant, and each element's fields. Do not test only a single simple field and assume all nested structures work.

## 20. Complete Spring Boot example: configuring an email client

Suppose an application needs a mail API client. Configuration:

~~~yaml
app:
  mail:
    endpoint: https://mail-api.example.test
    sender: noreply@example.test
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      max-attempts: 3
      backoff: 500ms
~~~

`MailProperties.java`:

~~~java
package com.example.mail;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        @NotNull URI endpoint,
        @NotBlank String sender,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry
) {
    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff
    ) {
    }
}
~~~

`MailClient.java`:

~~~java
package com.example.mail;

import org.springframework.stereotype.Service;

@Service
public class MailClient {

    private final MailProperties properties;

    public MailClient(MailProperties properties) {
        this.properties = properties;
    }

    public String describeConfiguration() {
        return "Endpoint=" + properties.endpoint()
                + ", sender=" + properties.sender()
                + ", timeout=" + properties.requestTimeout();
    }
}
~~~

`Application.java`:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

With Spring Boot and Bean Validation dependencies in place, startup performs:

1. Loads property sources.
2. Scans and registers `MailProperties`.
3. Binds values under the `app.mail` prefix.
4. Converts URL strings to `URI` and timeouts to `Duration`.
5. Validates required fields.
6. Creates `MailClient` and injects the bound properties.

`MailClient` in this example only demonstrates consuming configuration; it does not actually send emails. A real project needs an HTTP client library, authentication, timeouts, bounded retries, and proper error handling.

### 20.1. Changing configuration without editing business code

Local:

~~~yaml
app:
  mail:
    endpoint: http://localhost:9091
~~~

Staging:

~~~yaml
app:
  mail:
    endpoint: https://mail-staging.example.test
~~~

When changing the endpoint via a config source, `MailClient` still injects the same `MailProperties` type. This establishes a clean boundary between code and deployment.

### 20.2. When an API token or password is present

You can add `apiToken` to the properties class, while taking care to protect it:

- Do not commit secrets to Git.
- Do not hard-code secrets in Java source.
- Do not log the entire properties object; a record's `toString()` can expose sensitive data.
- Use a secret manager, environment, or secure configuration system.
- Control access and masking policies on Actuator/configuration endpoints.

`@ConfigurationProperties` is a binding mechanism, **not** a secret-protection mechanism.

## 21. Common errors

### 21.1. Properties bean not found

**Symptom:** Service constructor reports that `PaymentProperties` could not be found.

**Cause:** The class has `@ConfigurationProperties` but was never registered.

**Solution:** Use `@ConfigurationPropertiesScan` on an appropriate package or `@EnableConfigurationProperties(PaymentProperties.class)`.

### 21.2. Wrong prefix or YAML indentation

**Symptom:** Fields remain null or only retain defaults.

**Cause:** Annotation specifies `app.payment` while the file writes `app.payments`, or YAML is indented at the wrong level.

**Solution:** Compare the property structure against the prefix rather than looking only at field names.

### 21.3. Using @Component on an immutable record

**Symptom:** Spring searches for beans of type `URI`, `Duration`, or `String` to inject into the constructor.

**Cause:** Spring treats the record as normal component autowiring.

**Solution:** Remove `@Component` and register via configuration-properties scan/enable.

### 21.4. Wrong data type

**Symptom:** Binding `Duration`, `DataSize`, `URI`, or an enum fails.

**Cause:** Configuration value is invalid or unconvertible.

**Solution:** Specify explicit units, use valid enum constants, and inspect the root cause of the binding error.

### 21.5. Nested object is null

**Symptom:** `props.retry().maxAttempts()` throws `NullPointerException`.

**Cause:** The `retry` group was not supplied, has no default, and is not validated as required.

**Solution:** Add defaults for the nested object or `@Valid @NotNull` to fail fast when a required group is missing.

### 21.6. Validation does not run

**Symptom:** Invalid values are still accepted.

**Cause:** Missing `@Validated`, constraint annotations, `@Valid` on nested objects, or a Bean Validation provider.

**Solution:** Check annotations and the `spring-boot-starter-validation` dependency.

### 21.7. Environment variable name does not match

**Symptom:** Env value does not override YAML.

**Cause:** Rules for converting dots and dashes were misapplied.

**Solution:** Convert canonical names per rule, e.g., `app.payment.read-timeout` to `APP_PAYMENT_READTIMEOUT`.

### 21.8. Profile list overrides base data

**Symptom:** Some items vanish when a profile is enabled.

**Cause:** Lists are typically replaced by configuration from higher-precedence sources rather than automatically appended.

**Solution:** Declare the complete list needed in the profile, or switch to a map if per-key overrides are required.

### 21.9. Expecting config file edits to auto-update beans

**Symptom:** Updating `application.yml` leaves the service using old values.

**Cause:** Runtime refresh is not the default behavior of `@ConfigurationProperties`.

**Solution:** Implement an explicit reload strategy if dynamic config is genuinely required; do not treat properties objects as shared runtime state.

### 21.10. Token leaked in logs

**Symptom:** API key shows up during debugging.

**Cause:** Logging the entire properties object, calling `toString()`, or exposing sensitive properties via unprotected endpoints.

**Solution:** Log only non-sensitive data and enforce proper access and masking policies.

## 22. Workflow for designing a properties group

When adding configuration for a feature:

1. Choose a prefix meaningful to the module, such as `app.mail` or `app.payment`.
2. Decide which fields are required and which are optional.
3. Choose appropriate Java types: `URI`, `Duration`, `DataSize`, enums, lists/maps.
4. Decide between a mutable JavaBean and an immutable record.
5. Name canonical properties in kebab-case.
6. Create nested objects for tightly coupled subgroups.
7. Add defaults only when they are safe and intentional.
8. Add validation and clear failure messages.
9. Register the bean via scan or explicit enable.
10. Inject via constructor into consuming services.
11. Write tests for a valid case and key missing/invalid cases.
12. Document configuration keys, override methods, and secret sources.

A well-designed `@ConfigurationProperties` class acts as the **module's configuration contract**. It documents what data the module needs, their types, and fails clearly when configuration is invalid.

## 23. Practice exercises

### Exercise A: Converting four @Value fields into one class

Given properties:

~~~properties
app.report.endpoint=https://reports.example.test
app.report.timeout=3s
app.report.format=PDF
app.report.enabled=true
~~~

Create `ReportProperties` containing `URI endpoint`, `Duration timeout`, a `Format` enum, and `boolean enabled`. Register the bean and inject it into `ReportService`, replacing the old `@Value` parameters.

### Exercise B: Using records and relaxed binding

Create a record with a `requestTimeout` component, configure `request-timeout` in YAML, and test binding.

Then run with the `APP_REPORT_REQUESTTIMEOUT` environment variable and verify the override result.

### Exercise C: Nested retry

Add the group:

~~~yaml
app:
  report:
    retry:
      max-attempts: 4
      backoff: 300ms
~~~

Create a nested `Retry` record and test omitting this group. Use `@DefaultValue` if retry is optional; use validation if it is required.

### Exercise D: Validation

Try a malformed timeout, a missing endpoint, and retry equal to 0. Distinguish conversion errors from constraint errors in the startup logs.

### Exercise E: Binding a third-party library class

Suppose `ExternalClientOptions` has `setEndpoint` and `setTimeout` setters. Use `@Bean` combined with `@ConfigurationProperties(prefix = "app.external")` to bind it.

Then build an alternative using an `ExternalProperties` record and a factory method, and compare where validation belongs.

### Exercise F: Profiles and lists

Put a list of routing targets in base config and another list in the `prod` profile. Write a test with the profile active and observe how the list is replaced rather than appended.

### Exercise G: Testing the configuration contract

Use `ApplicationContextRunner` to verify three scenarios: valid configuration, missing required field, and invalid data type.

## 24. Self-check questions

**1. What does `@ConfigurationProperties` do?**

It binds a group of properties sharing the same prefix into a structured, strongly typed Java object.

**2. Is the prefix `app.payment` a bean name?**

No. It is a logical prefix for configuration keys in `Environment`.

**3. Is placing `@ConfigurationProperties` on a class enough on its own?**

No. The class must be registered via scan, enable, or an appropriate bean mechanism.

**4. Do record properties need setters?**

No. Constructor binding creates an immutable object with the bound data.

**5. Why not use `@Component` on a constructor-bound record?**

Because Spring may treat constructor parameters as regular bean dependencies rather than binding them from property sources.

**6. What Java component corresponds to `read-timeout`?**

`readTimeout`, via relaxed binding.

**7. What types can `2s` and `20MB` bind to?**

`Duration` and `DataSize`.

**8. What role does `@Validated` play?**

It enables validation of configuration properties against declared constraints, helping detect invalid configuration.

**9. Does `@ConfigurationProperties` auto-reload when files change after startup?**

Not by default. A dedicated refresh/reload mechanism is needed if dynamic config is required.

**10. When is `@Value` still reasonable?**

When only a couple of simple properties are needed and there is no cohesive configuration group to manage.

**11. Should you log a properties record that contains a token?**

No. `toString()` or logging can expose the secret.

## 25. Conclusion

`@ConfigurationProperties` helps Spring Boot **group configuration by prefix into a structured, strongly typed Java object**. It separates business code from configuration sources and prevents property name strings from spreading through controllers, services, and clients.

Use `@ConfigurationPropertiesScan` when you want application-wide package discovery of configuration groups, `@EnableConfigurationProperties` for modules or tests that register specific classes, and `@Bean` with `@ConfigurationProperties` when binding objects created by factory methods. Immutable records suit constructor binding in modern Boot releases; mutable JavaBeans remain useful for setter-based classes.

Use canonical kebab-case property names, defaults for optional settings, validation for required data, constructor injection into consumers, and tests verifying binding from property sources. Finally, remember that binding does not automatically provide runtime refresh or secret protection.

A configuration properties group designed as a module's contract makes the application easier to understand, test, and deploy across environments without changing business logic.
