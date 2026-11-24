# Typed Configuration Model and Benefits of @ConfigurationProperties

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** @ConfigurationProperties

## 1. Why Do We Need a Typed Configuration Model?

A Spring Boot application typically has many parameters that vary by environment: API addresses, timeouts, data size limits, retry counts, feature flags, or connection settings. Initially, each component might read a string from `Environment` or inject values using `@Value`:

~~~java
@Value("${acme.client.base-url}")
private String baseUrl;

@Value("${acme.client.connect-timeout:3s}")
private String timeout;
~~~

As configuration grows, scattered reading reveals several problems: key names are repeated across multiple classes; code must perform type conversion manually; related values are not grouped together; checks for missing or invalid configuration are spread out; and it is difficult to see the full configuration contract of a feature.

**`@ConfigurationProperties` solves this problem by mapping a group of properties from Spring `Environment` into a strongly typed Java object.** Each object describes the configuration contract for a part of the application. For example:

~~~text
acme.client.base-url             -> URI
acme.client.connect-timeout      -> Duration
acme.client.max-payload          -> DataSize
acme.client.retry.max-attempts   -> int
acme.client.retry.backoff        -> Duration
~~~

The application uses a `ClientProperties` bean with corresponding fields, instead of resolving individual strings in each service. This is the **type-safe configuration properties** model: properties are bound and converted to Java types during initialization/binding.

### Lesson Objectives

After this lesson, you will be able to:

- Define a configuration class with `@ConfigurationProperties(prefix = "...")`.
- Bind properties from YAML, properties files, environment variables, or CLI into Java types and nested objects.
- Register configuration beans using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
- Distinguish immutable records from JavaBeans with setters.
- Apply validation so the application detects missing or invalid configuration at startup.
- Understand relaxed binding, default values, precedence, and behavior with lists/maps.
- Choose between `@ConfigurationProperties` and `@Value` based on the use case, while recognizing operational and security limits.

## 2. Overview of How It Works

The data flow can be visualized as follows:

~~~text
application.yml / application.properties
                 |
OS environment / JVM system properties / CLI
                 |
JSON application properties / config imports / ...
                 |
                 v
      Spring Environment
       (PropertySources)
                 |
                 v
      ConfigurationProperties Binder
       - resolves names and sources
       - binds nested properties
       - converts data types
       - applies default values
       - performs validation if configured
                 |
                 v
         ClientProperties bean
                 |
                 v
          Service / Component
~~~

There are three distinct roles:

1. **Configuration sources** provide key names and values. For example, `application.yml` or `ACME_CLIENT_BASE_URL` from the environment.
2. Spring Boot's **Binder** binds properties matching a prefix to fields or constructor parameters, while performing type conversion.
3. **Configuration beans** hold the typed values for business components to consume via constructor injection.

`@ConfigurationProperties` itself **does not read YAML files directly**, nor does it decide which source takes precedence. Loading config data and determining `PropertySource` order are part of Spring Boot's externalized configuration mechanism; the binder uses the resolved values from that environment.

## 3. End-to-End Example with a Java Record

Suppose a service calling an external API needs an endpoint, timeout, payload limit, list of regions, and retry policy.

### 3.1. Declaring Configuration in `application.yml`

~~~yaml
acme:
  client:
    base-url: "https://api.example.test"
    connect-timeout: 3s
    max-payload: 2MB
    allowed-regions:
      - ap-southeast-1
      - ap-northeast-1
    headers:
      x-client-name: catalog
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

The flattened keys take the form:

~~~text
acme.client.base-url
acme.client.connect-timeout
acme.client.max-payload
acme.client.allowed-regions[0]
acme.client.allowed-regions[1]
acme.client.headers.x-client-name
acme.client.retry.max-attempts
acme.client.retry.backoff
~~~

Values such as `3s`, `2MB`, and `250ms` are strings following Spring Boot's configuration syntax; the binder can convert them to `Duration` or `DataSize`.

### 3.2. Defining an Immutable Record

Example for Spring Boot 3.x and Java 17 or later:

~~~java
package com.example.catalog.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "acme.client")
public record ClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        DataSize maxPayload,
        List<String> allowedRegions,
        Map<String, String> headers,
        Retry retry
) {
    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {}
}
~~~

Meaning of each part:

- `@ConfigurationProperties(prefix = "acme.client")` specifies the group of keys the binder will use.
- `baseUrl` receives `acme.client.base-url` and converts it to `URI`.
- `connectTimeout` receives a value like `3s` and converts it to `Duration`.
- `maxPayload` receives `2MB` and converts it to `DataSize`.
- `allowedRegions` is bound as a `List<String>`.
- `headers` receives entries from the map.
- `retry` is a nested object with `maxAttempts` and `backoff`.

In Spring Boot 3, a record with a suitable single constructor supports constructor binding **without needing `@ConstructorBinding`** for standard cases. Records help keep configuration parameters immutable: components read accessors like `baseUrl()` and `retry().maxAttempts()`, without modifying fields via setters.

That **does not mean** all objects inside a record are deeply immutable. If a record contains a mutable `List`/`Map`, you must consider the semantics and usage of those collections when full immutability is required.

### 3.3. Registering the Configuration Class as a Bean

Place `@ConfigurationPropertiesScan` on the application:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

When scanning within the appropriate package scope, Spring Boot finds classes annotated with `@ConfigurationProperties` and registers them for binding.

Another option is explicit registration:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {}
~~~

You do not need to use both mechanisms simultaneously for the same class. Choose **scan** when multiple configuration classes follow a package convention; choose **explicit enable** when you want to list the specific configuration beans to register.

### 3.4. Consuming the Bean via Constructor Injection

~~~java
package com.example.catalog.service;

import java.net.URI;

import com.example.catalog.config.ClientProperties;
import org.springframework.stereotype.Service;

@Service
public class CatalogClient {

    private final ClientProperties config;

    public CatalogClient(ClientProperties config) {
        this.config = config;
    }

    public URI endpoint() {
        return config.baseUrl();
    }

    public int maxAttempts() {
        return config.retry().maxAttempts();
    }
}
~~~

The service receives **a bound configuration object**. Business code does not need to know whether the values came from internal YAML, an external file, the environment, or command-line arguments.

To use the configuration in a real application, the service can pass `config.connectTimeout()` to an HTTP client builder, or use `config.maxPayload().toBytes()` when a byte limit is needed. The goal is for configuration to carry the **right type** before reaching consuming logic.

## 4. Key Benefits of Typed Configuration

### 4.1. Grouping Configuration by Feature

Compare the two approaches:

~~~java
// Properties are read separately in multiple places.
String baseUrl = env.getProperty("acme.client.base-url");
String timeout = env.getProperty("acme.client.connect-timeout");
String retry = env.getProperty("acme.client.retry.max-attempts");
~~~

With:

~~~java
public CatalogClient(ClientProperties properties) {
    this.properties = properties;
}
~~~

The second approach establishes a clear boundary: `ClientProperties` describes the client's configuration. When adding or removing an option, there is a single centralized place to update the configuration contract.

### 4.2. Systematic Type Conversion

For example, `connect-timeout: 3s` is bound to `Duration`. Code does not have to manually call `Long.parseLong(...)`, multiply by 1,000, or guess millisecond units.

Spring Boot supports converting many common types such as `Duration`, `DataSize`, enums, URL/URI, numeric types, booleans, and various collections. Specific conversion capabilities depend on the target type and registered converters.

If a value cannot be converted to the required type, the binder can report a binding error when the bean is created. This catches many mistakes early that would easily remain hidden if every property were a `String`.

### 4.3. Centralized Validation

You can require the endpoint to be non-null, retry attempts to be positive, timeout to be valid, or the regions list to be non-empty. Configuration bean validation can run during binding, causing the application to **fail fast** when the deployment environment lacks required settings.

### 4.4. Discoverability and Maintainability

A `ClientProperties` record clearly reveals all fields and data types in its constructor signature. Code readers do not have to hunt down scattered placeholder strings across controllers and services.

Spring Boot can generate **configuration metadata** via an annotation processor for configuration classes, supporting IDE completion, property documentation, and warnings for mismatched key names. Metadata is a development aid, not a runtime requirement for the binder to work.

### 4.5. Easy Testing with Deterministic Configuration

In tests, you can explicitly supply property values instead of depending on a developer's local environment variables. If a service only depends on a configuration object, a plain Java unit test can directly instantiate the record with desired values.

For example:

~~~java
ClientProperties properties = new ClientProperties(
        URI.create("https://example.test"),
        Duration.ofSeconds(2),
        DataSize.ofMegabytes(1),
        List.of("test-region"),
        Map.of("x-client-name", "test"),
        new ClientProperties.Retry(2, Duration.ofMillis(100))
);
~~~

This is an example of constructing an object for unit testing; it **does not** test Spring's binding mechanism itself. To test property names or actual type conversion, use a test that starts a context with explicit configuration.

## 5. Immutable Records vs. JavaBeans with Setters

Spring Boot supports multiple target object styles; two common approaches are constructor binding and JavaBean binding.

### 5.1. Constructor Binding with Records

~~~java
@ConfigurationProperties(prefix = "billing")
public record BillingProperties(
        String currency,
        boolean enabled,
        Duration timeout
) {}
~~~

The binder passes values to the record's constructor. Once the object is created, its fields have no setters. This style fits when you want configuration to act as a **fixed descriptor** throughout the bean's lifecycle.

For regular Java classes with multiple constructors, pay attention to the constructor selection rules and `@ConstructorBinding` in your Spring Boot version. A record with a single canonical constructor is the cleanest and clearest path in Boot 3.

### 5.2. JavaBean Binding

Another option:

~~~java
package com.example.catalog.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mail.transport")
public class MailTransportProperties {

    private String host;
    private int port = 25;
    private Duration timeout = Duration.ofSeconds(5);

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

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

In JavaBean binding, Spring Boot creates the object using an appropriate constructor, then binds properties using setters or suitable property structures. Field defaults (`port=25`, `timeout=5s`) can be used when the property is not provided.

If you want the configuration object to be mutable after initialization or need integration with libraries based on JavaBean conventions, this style can be convenient. However, for read-only runtime configuration, immutable objects typically help prevent accidental value modification.

### 5.3. Avoid Using Constructor Binding in the Wrong Context

Constructor binding for `@ConfigurationProperties` is not arbitrarily applied to every bean created by Spring via `@Component`, `@Bean`, or `@Import` as if it were standard dependency injection. For constructor-bound configuration records, register them via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

Do not add `@Component` to every configuration record just so Spring finds it; use the proper configuration properties registration mechanism.

## 6. Relaxed Binding: Java Names Do Not Have to Match YAML Exactly

One benefit of `@ConfigurationProperties` is **relaxed binding**: Spring Boot supports rules that map multiple property name formats to the same Java field.

For example, the Java field:

~~~java
private Duration connectTimeout;
~~~

can receive data from the canonical key:

~~~properties
acme.client.connect-timeout=3s
~~~

In YAML:

~~~yaml
acme:
  client:
    connect-timeout: 3s
~~~

And from an environment variable following the convention:

~~~bash
export ACME_CLIENT_CONNECTTIMEOUT=4s
~~~

For environment variables, Spring Boot typically converts dots to underscores, removes dashes, and converts to uppercase: `acme.client.connect-timeout` becomes `ACME_CLIENT_CONNECTTIMEOUT`. Avoid arbitrarily guessing underscore variants when names have multiple segments; prefer canonical names in files and environment variable names that follow Spring Boot's rules.

### 6.1. Prefix Names Should Use Canonical Form

For example:

~~~java
@ConfigurationProperties(prefix = "acme.client")
public record ClientProperties(Duration connectTimeout) {}
~~~

The prefix `acme.client` uses lowercase letters and dot-separated segments. Spring Boot recommends naming properties in **kebab-case**, such as `connect-timeout`.

When creating new configuration, keep naming conventions consistent so developers, IDEs, and deployment pipelines can locate the exact key names.

### 6.2. Nested Fields

The property `acme.client.retry.max-attempts` has a path consisting of prefix `acme.client`, object `retry`, and field `maxAttempts`. The binder creates nested objects when configuration and a suitable constructor/binding target are present.

There is no need to write a `retry` property containing a JSON string and parse it manually. Child keys can be bound into a nested record or class.

### 6.3. Map Keys Are Not Like Field Names

With `Map<String, String>`, some key names containing dots, slashes, or special characters may require bracket notation to preserve characters when processed by the binder.

For example, in YAML, a map key can be quoted:

~~~yaml
acme:
  client:
    headers:
      "[/special-key]": "value"
~~~

Do not assume every map key is processed identically to Java fields. When working with special key names, refer to Spring Boot's **Binding Maps** rules, especially when using bracket notation or maps with keys containing dots.

## 7. Type Conversion: Duration, DataSize, Enum, List, and Map

### 7.1. `Duration`

~~~yaml
worker:
  connect-timeout: 500ms
  read-timeout: 5s
~~~

~~~java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        Duration connectTimeout,
        Duration readTimeout
) {}
~~~

Suffixes like `ms` and `s` indicate units. Avoid entering a bare number like `5000` and guessing whether it is seconds or milliseconds; for `Duration`, if a number has no unit, the binder applies default unit rules depending on configuration/annotations. Writing explicit units reduces confusion.

### 7.2. `DataSize`

~~~yaml
upload:
  max-file-size: 16MB
~~~

~~~java
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "upload")
public record UploadProperties(DataSize maxFileSize) {}
~~~

`DataSize` is suitable for expressing byte limits. When code needs the byte count, use `maxFileSize.toBytes()`. Pay attention to Spring's supported units and their semantics; do not manually parse string units when the binder already provides conversion.

### 7.3. Enum and Boolean

~~~java
public enum Mode {
    SAFE, FAST
}

@ConfigurationProperties(prefix = "worker")
public record ExecutionProperties(Mode mode, boolean enabled) {}
~~~

~~~yaml
worker:
  mode: SAFE
  enabled: true
~~~

Using an enum instead of a string restricts the set of choices and clarifies semantics in code. When receiving a value that cannot be converted to `Mode`, binding can report an error rather than continuing with an unknown string.

### 7.4. Lists

~~~yaml
routing:
  regions:
    - ap-southeast-1
    - ap-northeast-1
~~~

~~~java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(List<String> regions) {}
~~~

Be aware of **list replacement** when multiple configuration sources provide the same list. Spring Boot typically uses the list from the higher-precedence source instead of concatenating elements from all sources.

### 7.5. Maps

~~~yaml
routing:
  labels:
    owner: backend
    region: apac
~~~

~~~java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(Map<String, String> labels) {}
~~~

Map entries can be merged key-by-key across multiple sources; entries with the same key are chosen by precedence. List and map semantics **differ**, so do not assume every collection deep-merges.

## 8. Validation: Catching Invalid Configuration Early

A typed object only guarantees that the binder attempts to convert data to the target type. It does not automatically guarantee that an endpoint exists, a timeout is valid, or a value falls within business bounds. That is the role of validation.

### 8.1. Adding the Validation Dependency

With Spring Boot 3 and applications using Spring Boot starters, Maven typically declares:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Or Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

This dependency provides standard Bean Validation infrastructure, with annotations in the `jakarta.validation` package in Spring Boot 3.

### 8.2. Declaring Constraints on Properties

~~~java
package com.example.catalog.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "acme.client")
@Validated
public record ValidatedClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @Valid @NotNull Retry retry
) {
    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff
    ) {}
}
~~~

In this example:

- `@Validated` enables validation during configuration properties binding.
- `@NotNull` requires the corresponding fields to have values.
- `@Min(1)` requires `maxAttempts` to be at least 1.
- `@Valid` requires validating constraints on the nested `Retry` object as well.

To test the example, register `ValidatedClientProperties` via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` and configure all fields. You do not need to simultaneously register another class with the same prefix if the application only needs one bean describing that configuration.

### 8.3. Missing Values and Type Errors Are Different Categories

Suppose the file contains:

~~~yaml
acme:
  client:
    base-url: "https://api.example.test"
    connect-timeout: "not-a-duration"
    retry:
      max-attempts: 0
      backoff: 100ms
~~~

`connect-timeout` can cause a **conversion/binding** error because it cannot be converted to `Duration`. If fixed to `2s` while keeping `max-attempts: 0`, a **validation** error from `@Min(1)` can occur.

When a setting is required, specify the appropriate constraint clearly. For strings that must not be empty or whitespace-only, `@NotBlank` is typically used rather than just `@NotNull`. For bounded integers, use `@Min`, `@Max`, or a custom validator.

### 8.4. Validating Nested Objects

With nested records, the `@Valid` annotation on the parent field is important so validation cascades into child constraints. `@NotNull` on the nested object helps catch cases where the entire object is omitted.

If you only place `@Min(1)` inside `Retry` without ensuring validation cascades into the nested object, do not assume every deep constraint will automatically be checked as expected. Validation configuration must be set up explicitly with an appropriate validator provider.

### 8.5. Failing Fast at Deployment

A new deployment that forgets to supply `acme.client.base-url` can render the configuration bean invalid. Having the application refuse to start in this situation is usually better than letting the first request hit a `NullPointerException`.

However, startup validation **does not replace** runtime condition checks: an endpoint may be syntactically valid yet unreachable, credentials may have expired, or remote data may change. Validation verifies the configuration contract, whereas connectivity and business state are separate concerns.

## 9. Default Values in Typed Configuration

There are at least three common ways to design defaults.

### 9.1. Defaults in Configuration Files

~~~yaml
acme:
  client:
    connect-timeout: 3s
    retry:
      max-attempts: 3
~~~

This approach is easy to read and can be overridden by higher-precedence sources such as environment variables or CLI arguments.

### 9.2. Defaults in JavaBean Fields

~~~java
private Duration timeout = Duration.ofSeconds(5);
private boolean enabled = true;
~~~

For JavaBeans with setters, initialized values can be retained when no corresponding property is bound. However, this ties defaults to Java source code, so changing a default policy requires changing code or overriding via externalized configuration.

### 9.3. `@DefaultValue` with Constructor Binding

In Spring Boot 3, `@DefaultValue` can be used on constructor-bound parameters:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        @DefaultValue("10s") Duration timeout,
        @DefaultValue("false") boolean enabled
) {}
~~~

When `reports.timeout` or `reports.enabled` is not provided, the binder can use the default value from the annotation. Note that validation can still be applied to the final bound value.

Default values should be business-safe. **Do not** use a dummy password or fake production URL as a silent fallback for required configuration.

## 10. Configuration Sources and Precedence

`@ConfigurationProperties` is not limited to data from `application.yml`. The binder reads properties gathered by Spring Boot in `Environment`.

Common sources include:

- `application.properties` or `application.yml` packaged inside the JAR.
- External configuration files outside the JAR and files imported via `spring.config.import`.
- Environment variables, such as `ACME_CLIENT_BASE_URL`.
- Java system properties, such as `-Dacme.client.base-url=...`.
- `SPRING_APPLICATION_JSON`.
- Command-line arguments, such as `--acme.client.base-url=...`.
- Servlet-specific sources, tests, or custom `PropertySource` implementations when configured.

### 10.1. When the Same Key Appears in Multiple Sources

`application.yml`:

~~~yaml
acme:
  client:
    base-url: "https://default.example"
    connect-timeout: 3s
~~~

Environment variable:

~~~bash
export ACME_CLIENT_BASEURL=https://staging.example
~~~

Run command:

~~~bash
java -jar catalog.jar \
  --acme.client.connect-timeout=1s
~~~

With Spring Boot's default precedence in this example, the `ClientProperties` bean typically receives:

~~~text
baseUrl        = https://staging.example
connectTimeout = 1s
~~~

Different sources supply values **per key**; the binder does not treat an entire file's object as an indivisible record. If only `connect-timeout` is overridden, other fields can still come from YAML.

### 10.2. With Profile-Specific / Conditional Documents

~~~yaml
acme:
  client:
    connect-timeout: 3s

---
spring:
  config:
    activate:
      on-profile: "prod"

acme:
  client:
    connect-timeout: 1s
~~~

When the `prod` profile is active, the latter document can override `connect-timeout` within this file. Boot then still evaluates other config data, environment, and CLI sources according to precedence. `@ConfigurationProperties` only binds the **final resolved** value; it does not activate profiles itself.

### 10.3. Lists and Maps Across Multiple Property Sources

An important note: lists typically follow a **replace the entire list** rule when bound from a higher-precedence source; maps can merge entry-by-entry. Therefore, configuration containing lists/maps must be understood according to binder semantics rather than assuming objects always deep-merge every element.

### 10.4. Directives Choosing Where to Load Files Are Processed Early

Properties such as `spring.config.location` or `spring.config.additional-location` must be provided very early in the startup lifecycle so Boot knows where to locate config data. `@ConfigurationProperties` beans are bound **after** the appropriate configuration collection phase; they cannot replace the bootstrap mechanism to go find unloaded files themselves.

## 11. Comparing `@ConfigurationProperties`, `@Value`, and `Environment`

| Criterion | `@ConfigurationProperties` | `@Value` | `Environment` |
| --- | --- | --- | --- |
| Primary purpose | Bind a typed configuration group | Inject a single expression/value | Look up properties via API |
| Nested configuration | Convenient, supports nested objects | Must declare each placeholder individually | Look up each key manually |
| Type conversion | Binder supports many types and collections | Supports conversion via Spring | Provides overloads with target type |
| Validation | Integrates Bean Validation when configured | Requires designing appropriate checks | Caller handles and checks manually |
| Discoverability | Class describes the configuration contract | Keys scattered at usage sites | String keys in code |
| Relaxed binding | Dedicated binder mechanism, kebab-case recommended | Not all rules match Binder | Depends on lookup/conversion path |
| Expression/SpEL | Focused on property binding, not a SpEL evaluator | Supports expressions via `@Value` | Property lookup, not `@Value` itself |

### 11.1. When to Use `@Value`?

When a small component needs a single simple property:

~~~java
@Component
public class FeatureBanner {

    private final String title;

    public FeatureBanner(
            @Value("${feature.banner-title:Welcome}") String title) {
        this.title = title;
    }
}
~~~

Using `@Value` is reasonable when there are only one or a few independent values and you do not need to define a dedicated configuration model.

### 11.2. When to Use `@ConfigurationProperties`?

If configuration has multiple related fields, nested objects, collections, specialized types, or constraints, a properties class expresses intent much more clearly.

For example:

~~~java
@ConfigurationProperties(prefix = "feature.banner")
public record BannerProperties(
        String title,
        boolean enabled,
        Duration refreshInterval
) {}
~~~

Services receive `BannerProperties`, tests can supply explicit overrides, and validators can verify the entire set of values at startup.

### 11.3. When to Use `Environment` Directly?

`Environment` fits framework integration, diagnostic tools, or logic that genuinely needs to query dynamic property names. In business code with a fixed set of properties, repeating `getProperty("...")` across multiple classes makes the configuration contract hard to manage.

## 12. Configuration Metadata and IDE Support

Spring Boot provides an annotation processor that generates metadata for `@ConfigurationProperties` classes. In Gradle Groovy DSL:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Or with Maven, configure annotation processing appropriately for your plugin/compiler and add the `spring-boot-configuration-processor` dependency in the proper scope.

Metadata is typically placed in the artifact at `META-INF/spring-configuration-metadata.json`. IDEs can leverage it to suggest keys, types, and property descriptions. To document each option for users, write JavaDoc on the class and appropriate fields/constructor components so the processor or tooling recognizes them as supported.

**The annotation processor is not the Binder.** Missing metadata may reduce IDE suggestions, but it does not mean the `@ConfigurationProperties` bean fails to work. Conversely, having metadata does not guarantee a bean is registered or configuration is valid.

## 13. Principles for Organizing Configuration Properties in a Project

### 13.1. Split by Capability, Do Not Dump Everything into One Class

Instead of one `ApplicationProperties` object containing hundreds of unrelated fields, you can have:

~~~text
HttpClientProperties       -> acme.http-client.*
StorageProperties          -> acme.storage.*
NotificationProperties     -> acme.notification.*
SecurityIntegrationProps   -> acme.security-integration.*
~~~

Each class belongs to the part of the application responsible for consuming those values. For example, the HTTP client uses `HttpClientProperties`; the storage service uses `StorageProperties`.

This organization gives each module its own configuration contract and validation, while reducing unnecessary dependencies between services.

### 13.2. Choose Meaningful Namespaces

Use dedicated prefixes like `acme.storage` or `catalog.import-job` for application properties, avoiding misusing framework namespaces like `spring.*` for business options.

A stable prefix makes configuration easy to find, document, and override across environments. Renaming a public key is a deployment contract change; consider compatibility with manifests, Helm charts, environment variables, tests, and documentation.

### 13.3. Keep Business Logic Out of Properties Classes

A `@ConfigurationProperties` class should represent configuration data and necessary constraints. Do not turn it into a service that makes HTTP calls, accesses databases, or manipulates the filesystem in its constructor.

A readable configuration class with minimal side effects is easier to bind, validate, and test. Business logic using the values belongs in dependent beans.

### 13.4. Distinguish Configuration from Continuously Changing State

Values like endpoints, timeouts, and retry policies are suitable for binding as configuration. Runtime state such as in-flight request counts, counters, cache entries, or continuously refreshed tokens should not be stored as fields in `@ConfigurationProperties` and treated as live runtime data sources.

If hot configuration updates are needed, design an explicit refresh/rebind mechanism with concurrency and bean lifecycle control; basic `@ConfigurationProperties` does not automatically detect every file or environment variable edit.

## 14. Security and Operations

### 14.1. Typed Configuration Can Still Contain Secrets

A class such as:

~~~java
@ConfigurationProperties(prefix = "integration.auth")
public record AuthProperties(String username, String password) {}
~~~

only describes where properties are used. It **does not encrypt, mask, or protect secrets** merely via the annotation. Secrets must still come from secure sources, such as a secret manager or restricted-permission volume mounts.

Note that `record.toString()` can print record fields. **Do not log entire configuration objects containing passwords, tokens, or private keys.** For diagnostics, log only key names and presence status, or selectively non-sensitive values.

### 14.2. Do Not Put Sensitive Values in Arbitrary Error Messages

When binding fails, some framework diagnostics may include property details. Configure logging and diagnostic endpoints appropriately, control access to Actuator `env` / `configprops`, and configure sanitization for sensitive values. Do not pass a secret-holding configuration object into custom exceptions or logs.

### 14.3. Configuration Reflects Binding Time Only

When a Kubernetes Secret, ConfigMap, or externalized file changes, fields in singleton properties beans are not automatically rebound by default. For configuration that must change at runtime, design controlled restarts/rollouts or a refresh mechanism. Do not treat a bean bound at startup as an always-current source of truth for data that changes every second.

### 14.4. Binding Does Not Verify External Systems

A valid `URI` might point to a down server; a valid `Duration` might be too low for real latency; a properly formatted credential might be revoked. Bean Validation checks the **application's internal configuration contract**, not external system state.

If startup must prove a dependency is ready, that requires a separate health/connectivity mechanism with appropriate timeouts and failure policies.

## 15. Common Errors and Diagnostics

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Cannot inject `ClientProperties` | Not registered via scan/enable, or wrong scan package | Add appropriate `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Fields are null or default values | Wrong prefix/key; source not loaded; missing property | Verify `acme.client.*` and actual configuration sources |
| Cannot convert `connect-timeout` | Invalid value for `Duration` | Use explicit units such as `500ms`, `3s` |
| Validation does not run as expected | Missing `@Validated`, validator dependency, or cascading `@Valid` | Set up Bean Validation properly |
| Nested object is not bound | Wrong branch in YAML or mismatched constructor/target | Match `retry.max-attempts` with field `retry.maxAttempts` |
| List loses default elements | Higher-precedence source replaces the list | Review list binding semantics and source precedence |
| Map key with dots is altered | Appropriate bracket notation not used | Review Spring Boot map key rules |
| Environment reports different value from local | External JAR/env/CLI sources have different precedence | Check actual `PropertySource`s and config data |
| Bean keeps old value after ConfigMap change | Bean not refreshed/rebound or app not restarted | Design explicit rollout/refresh handling |
| IDE does not suggest property names | Missing configuration metadata processor | Add the processor if IDE assistance is desired |
| Record holding password exposed in logs | Object logged via `toString()` | Log only non-sensitive data and protect secrets |

### 15.1. Inspecting Values and Configuration Sources

For a **non-sensitive** key, you can use `ConfigurableEnvironment` to inspect sources and values:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public ConfigurationProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "acme.client.connect-timeout";

        System.out.println("Resolved: "
                + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

This snippet is for diagnostics only. `PropertySource` names and representations can vary across versions or configuration sources; do not use string source names in business logic.

Some sources do not use the exact same relaxed binding rules when queried directly via `getProperty(...)` as when bound via the Binder; use canonical names where appropriate, and when in doubt, inspect origin metadata/protected Actuator endpoints or test actual binding.

### 15.2. When Startup Fails Due to Configuration

If Spring Boot reports `BindException` or a binding/validation error related to `acme.client`, check in order:

1. **Is the bean registered?** Does `@ConfigurationPropertiesScan` cover the properties class's package?
2. **Is the prefix correct?** Code might declare `acme.client`, while the file mistakenly writes `acme.clients`.
3. **Was the file loaded?** Correct location, active profile, config import, and working directory?
4. **Was the property overridden?** OS environment, system properties, JSON/CLI, or test properties?
5. **Can the value be converted?** E.g., `2s` for `Duration`, `16MB` for `DataSize`.
6. **Are constraints satisfied?** `@NotNull`, `@Min`, or nested validators.
7. **Are target types correct?** List, map, record constructor, or JavaBean setters properly defined?
8. **Are secrets leaked in error logs?** Protect sensitive values and adjust diagnostics.

Do not disable validation or remove constraints just to let a deployment start with invalid configuration. Identify and fix the offending source property.

## 16. Practice Exercises

### Exercise A: Migrating from `@Value` to Typed Config

Initially, a service uses:

~~~java
@Value("${order.client.endpoint}")
private String endpoint;

@Value("${order.client.timeout:5s}")
private String timeout;

@Value("${order.client.retries:2}")
private int retries;
~~~

Create an `OrderClientProperties` record with prefix `order.client`, using `URI`, `Duration`, and `int` respectively, register it with `@ConfigurationPropertiesScan`, and inject it into the service. Verify the code no longer needs to parse timeout from a string.

### Exercise B: Nested Properties

Create `application.yml`:

~~~yaml
order:
  client:
    endpoint: "https://orders.example.test"
    timeout: 4s
    retry:
      enabled: true
      attempts: 3
~~~

Define `OrderClientProperties` with a nested `Retry` record. Print a non-sensitive result such as `timeout` or `retry.attempts` at startup to observe binding.

### Exercise C: Validation

Add `@Validated` and constraints requiring `endpoint` to be non-null, `timeout` non-null, and `retry.attempts >= 1`. Run the application with `attempts=0` and observe the validation error. Then fix it to `3` and test an invalid `timeout` type to distinguish conversion errors from constraint errors.

### Exercise D: Environment Overrides

Given the default:

~~~yaml
order:
  client:
    timeout: 5s
~~~

Run with:

~~~bash
export ORDER_CLIENT_TIMEOUT=2s
java -jar order.jar --order.client.timeout=1s
~~~

Predict that the CLI argument takes precedence over the environment variable and default file when Spring Boot's default precedence is not customized. Bind to `Duration` and observe the actual value.

### Exercise E: Lists and Maps

Declare `routing.regions` as a list and `routing.labels` as a map. Provide a higher-precedence config source overriding only part of the keys. Verify the difference between list replacement and map entry merging.

### Exercise F: Choosing the Right Style

In the following three scenarios, explain which API to choose:

1. A component needs a single simple flag with no related properties.
2. An HTTP client needs an endpoint, timeout, retry settings, region list, and validation.
3. An internal tool needs to query property names entered by an operator at runtime.

Hint: `@Value` may suffice for scenario 1; `@ConfigurationProperties` fits scenario 2; `Environment` can fit scenario 3 with proper validation and error handling.

## 17. Key Takeaways

- `@ConfigurationProperties` describes **a typed configuration group** bound from `Environment` into a Java object. The annotation does not read YAML directly and does not alter source precedence.
- Use canonical prefixes and kebab-case key names. Relaxed binding maps YAML/properties/environment variables to Java fields.
- Spring Boot 3 supports constructor binding with records; use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` to register beans.
- The Binder supports `Duration`, `DataSize`, enums, lists, maps, nested objects, and type conversion. Lists and maps have different binding semantics across multiple sources.
- Combine `@Validated` and Bean Validation to detect missing or invalid configuration early during startup.
- `@Value` suits a few scalars; `Environment` is useful for dynamic lookups; `@ConfigurationProperties` fits when you need a stable, maintainable, and testable configuration contract.
- Protect secrets in sources and logs; a record containing a password can expose values via `toString()`. External configuration changes do not automatically update running beans by default.

## References

- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): definition, binding, registration, and benefits of `@ConfigurationProperties`.
- [Spring Boot Reference — Relaxed Binding](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding): naming rules and source-based binding.
- [Spring Boot Reference — Properties Conversion](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion): type conversion, `Duration`, and `DataSize`.
- [Spring Boot Reference — Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation): configuration bean validation.
- [Spring Boot Reference — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html): IDE metadata support and annotation processor.
- [Spring Framework Reference — Using `@Value`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html): injecting and resolving placeholders.
