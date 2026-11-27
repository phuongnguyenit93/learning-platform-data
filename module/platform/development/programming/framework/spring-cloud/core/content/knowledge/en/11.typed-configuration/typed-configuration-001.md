# Choosing @Value, Environment, or @ConfigurationProperties

> **Chapter:** Typed Configuration  
> **Module:** SPRING_CLOUD_CORE

Spring Boot provides several ways to read configuration from `application.yml`, profiles, environment variables, command-line arguments, and sources added by Spring Cloud. Three common approaches are **`@Value`**, **`Environment`**, and **`@ConfigurationProperties`**. They can all read values from the configuration environment, but they serve different needs.

Choosing the wrong mechanism often leaves configuration scattered, hard to type-check, lacking validation, or difficult to test. This lesson helps you pick the right tool based on data shape and usage lifecycle, while illustrating how to bind configuration for a service communication client in the **SPRING_CLOUD_CORE** module.

## 1. The Three Approaches and Their Primary Roles

| Mechanism | Best suited when | Characteristics |
| --- | --- | --- |
| `@Value` | A few simple values need to be injected directly into a bean | Concise, supports placeholders and SpEL, suited for a small property |
| `Environment` | Need to look up properties by name in code, check presence, or choose values via logic | Flexible API, can request target types, accesses multiple property sources |
| `@ConfigurationProperties` | There is a group of related, structured properties that need validation | Typed binding, groups configuration into an object, supports nested objects, lists, maps, and metadata |

All three mechanisms read from the **Spring Environment** or Spring Boot's configuration-source-based binding process. They are not three separate configuration stores and do not create three different sets of values on their own. The effective value is still governed by property sources, profiles, and precedence order.

You can start by asking: is the configuration a single value, a structured group of data, or a key determined only at runtime? The answer usually points to the right choice.

## 2. Using @Value for a Few Simple Properties

`@Value` injects an expression into a field, constructor parameter, or method parameter of a Spring bean. The most common usage is a placeholder:

~~~yaml
spring:
  application:
    name: order-service

catalog:
  client:
    base-url: "https://catalog.internal"
    read-timeout: 3s
~~~

Example injecting a single value:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ApplicationIdentity {

    private final String applicationName;

    public ApplicationIdentity(
            @Value("${spring.application.name:unknown-service}")
            String applicationName) {
        this.applicationName = applicationName;
    }

    public String applicationName() {
        return applicationName;
    }
}
~~~

The placeholder `${spring.application.name:unknown-service}` reads the `spring.application.name` property. If no value can be resolved, the part after `:` serves as the default value.

### 2.1. Placeholders, Default Values, and Data Types

Spring can convert placeholder values into supported target types:

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class RetrySettings {

    private final int maxAttempts;
    private final Duration retryDelay;

    public RetrySettings(
            @Value("${catalog.client.max-attempts:3}") int maxAttempts,
            @Value("${catalog.client.retry-delay:500ms}") Duration retryDelay) {
        this.maxAttempts = maxAttempts;
        this.retryDelay = retryDelay;
    }
}
~~~

Values can be converted using Spring's conversion service. For example, the string `500ms` can be converted to a `Duration`. However, as the number of properties grows, declaring individual `@Value` parameters makes constructors long and makes configuration harder to manage.

### 2.2. SpEL and Placeholders Are Two Different Syntaxes

`@Value` also supports Spring Expression Language (SpEL), for example:

~~~java
@Value("#{systemProperties['user.timezone']}")
private String timezone;
~~~

A placeholder `${...}` reads a property from the Environment. SpEL `#{...}` evaluates an expression against the Spring context. Do not use SpEL for arbitrary input or user-supplied strings; expressions should be hardcoded in source code and used only for well-defined configuration needs.

### 2.3. When Does @Value Stop Being Appropriate?

If a bean needs dozens of values under the same namespace—such as URL, timeout, pool size, retry, and header lists—injecting each key individually scatters configuration throughout the code. `@Value` also does not automatically provide a configuration object with a schema and centralized validation.

`@Value` fits a small number of properties like an application name, a simple flag, or a bean-specific limit. When configuration becomes a meaningful group, switch to `@ConfigurationProperties`.

## 3. Using Environment When Flexible Lookup Is Needed

`Environment` is Spring's abstraction for accessing an application's properties and profiles. You can inject it into a bean:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ServiceEndpointResolver {

    private final Environment environment;

    public ServiceEndpointResolver(Environment environment) {
        this.environment = environment;
    }

    public String endpointFor(String serviceName) {
        String key = "services." + serviceName + ".base-url";
        return environment.getProperty(key);
    }
}
~~~

In this example, the service name is determined at runtime, so you cannot easily declare a fixed placeholder for every key. `Environment` lets you assemble the property name and look it up on demand.

### 3.1. Commonly Used Methods

| API | Purpose |
| --- | --- |
| `getProperty(key)` | Read a property as a String |
| `getProperty(key, TargetType.class)` | Read and convert to the target type |
| `getProperty(key, defaultValue)` | Use the default value when no value can be resolved |
| `getRequiredProperty(key)` | Read a required property; throws an error if no value is present |
| `containsProperty(key)` | Check whether the property has a resolvable value in the Environment |
| `getActiveProfiles()` | Retrieve the currently active profiles |
| `acceptsProfiles(...)` | Check profile conditions using the API of the version in use |

Example reading typed values directly:

~~~java
Duration timeout = environment.getProperty(
        "catalog.client.read-timeout",
        Duration.class,
        Duration.ofSeconds(3));

Integer poolSize = environment.getProperty(
        "catalog.client.pool-size",
        Integer.class);
~~~

This approach is useful when the key name is decided dynamically or when a component needs to read a few discrete values. If you need a group of properties, consider binding them into an object instead of writing multiple `getProperty` calls manually.

### 3.2. Distinguishing Missing, Null, and Empty Strings

`Environment.getProperty` returns null if there is no matching resolvable value. An empty string is a present, non-null String value. Therefore:

~~~java
String label = environment.getProperty("notification.label");

if (label == null) {
    // No resolvable value.
} else if (label.isEmpty()) {
    // Present, but an empty string.
} else if (label.isBlank()) {
    // Whitespace only.
} else {
    // Has content.
}
~~~

`containsProperty` does not distinguish every source state such as absent versus YAML null. It answers whether the Environment has a resolvable property according to Spring's lookup semantics. If you need to investigate which source provides a value, inspect each PropertySource/origin; do not infer it from a single `getProperty` call.

### 3.3. Environment Does Not Automatically Bind and Validate a Configuration Group

`Environment` provides flexible property access, but your code must manually handle reading each key, defaults, conversion, and validation. For instance, if there are five client properties, five separate lookups do not form a unified configuration schema on their own.

You can use `Environment` to select a namespace by tenant or service ID, but you must control key names and validate the result. Never construct property names from untrusted data and use them to access sensitive keys.

## 4. Using @ConfigurationProperties for Structured Configuration

`@ConfigurationProperties` binds a group of properties sharing a prefix into a Java object. This is usually the right choice for client settings, connection pools, discovery, timeouts, retries, or related groups of properties.

YAML example:

~~~yaml
catalog:
  client:
    enabled: true
    base-url: "https://catalog.internal"
    connect-timeout: 1s
    read-timeout: 3s
    max-attempts: 3
    supported-regions:
      - north
      - south
~~~

Configuration record:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        boolean enabled,
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout,
        int maxAttempts,
        List<String> supportedRegions
) {}
~~~

The Spring Boot binder maps keys under the `catalog.client` prefix to the corresponding parameters. Kebab-case names like `base-url` and `connect-timeout` can bind to camelCase Java names like `baseUrl` and `connectTimeout` via relaxed binding.

A record expresses immutable configuration once created. This example uses constructor binding supported by Spring Boot for records in modern versions; for applications on older versions, follow the constructor binding guidelines for that specific Boot version.

### 4.1. Registering the Configuration Bean

You can use `@ConfigurationPropertiesScan` on the application class:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
}
~~~

Or register explicitly:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogClientProperties.class)
public class CatalogClientConfiguration {
}
~~~

Choose a clear registration mechanism and ensure the configuration class sits within the proper scan scope. Without registration, simply adding `@ConfigurationProperties` on a class may not create a bean in every application setup.

### 4.2. Nested Properties, Lists, and Maps

Configuration can have deep structure:

~~~yaml
catalog:
  client:
    base-url: "https://catalog.internal"
    headers:
      x-client-name: "order-service"
      x-region: "ap-southeast"
    retry:
      max-attempts: 3
      backoff: 250ms
    endpoints:
      - name: products
        path: /api/products
      - name: categories
        path: /api/categories
~~~

If configuration needs nested objects instead of a flat record, you can use another configuration model as shown below. This is an alternative model to the `CatalogClientProperties` record above; do not register both types with the same prefix if they represent the same configuration group.

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record NestedCatalogClientProperties(
        URI baseUrl,
        Map<String, String> headers,
        Retry retry,
        List<Endpoint> endpoints
) {
    public record Retry(int maxAttempts, Duration backoff) {}
    public record Endpoint(String name, String path) {}
}
~~~

In real configurations, clearly define required fields, default values, and valid bounds. If data from remote config could be missing or mistyped, validation catches issues early rather than letting errors surface during requests.

### 4.3. Conversion for Common Data Types

Spring Boot supports converting many common types:

| Java Type | Example config value | Meaning |
| --- | --- | --- |
| `Duration` | `500ms`, `5s`, `2m` | Duration |
| `DataSize` | `512KB`, `16MB` | Data size |
| `URI` / `URL` | `https://catalog.internal` | Address |
| `List<T>` | YAML list elements | List |
| `Map<K,V>` | Nested key/value group | Property map |
| Enum | `ROUND_ROBIN` | Typed constant |

For durations or data sizes, use dedicated types rather than reading integers and imposing ad-hoc unit conventions. If you need default units or bounds, configure the corresponding annotations and validation according to your Spring Boot version.

## 5. Validation for Typed Configuration

Misconfiguration can cause an application to call the wrong endpoint, create an oversized connection pool, or retry without limit. Validation rejects invalid configuration during startup.

Example:

~~~java
import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.AssertTrue;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog.client")
public record ValidatedCatalogClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Min(1) @Max(5) int maxAttempts
) {
    @AssertTrue(message = "connectTimeout must be positive")
    public boolean isConnectTimeoutPositive() {
        return connectTimeout != null
                && !connectTimeout.isZero()
                && !connectTimeout.isNegative();
    }

    @AssertTrue(message = "readTimeout must be positive")
    public boolean isReadTimeoutPositive() {
        return readTimeout != null
                && !readTimeout.isZero()
                && !readTimeout.isNegative();
    }
}
~~~

A compatible validation dependency must be present for constraints to be enforced. In this example, `@AssertTrue` checks that `Duration` is positive because the standard `@Positive` constraint targets numeric types and does not apply directly to `Duration`. With Spring Boot 3, validation annotations typically belong to the `jakarta.validation` namespace; Boot 2 projects may use `javax.validation` depending on version. Do not mix the two namespaces in the same configuration.

Common constraints:

| Constraint | Condition |
| --- | --- |
| `@NotNull` | Value must not be null |
| `@NotBlank` | String must not be null, empty, or whitespace-only |
| `@NotEmpty` | String/collection must not be null or empty |
| `@Positive` | Number greater than 0 |
| `@Min` / `@Max` | Minimum/maximum numeric bounds |
| `@Pattern` | String must match a regular expression |

If a nested object has its own constraints, use `@Valid` to cascade validation into the child object. Distinguish configuration validation from business request validation: they run at different times and serve different purposes.

## 6. Comparing Through the Same Example

Suppose `order-service` needs a timeout to call `catalog-service`.

### 6.1. Using @Value

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CatalogTimeoutWithValue {

    private final Duration readTimeout;

    public CatalogTimeoutWithValue(
            @Value("${catalog.client.read-timeout:3s}")
            Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

Suitable when a bean only needs a single value with no accompanying group of settings.

### 6.2. Using Environment

~~~java
import java.time.Duration;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CatalogTimeoutWithEnvironment {

    private final Environment environment;

    public CatalogTimeoutWithEnvironment(Environment environment) {
        this.environment = environment;
    }

    public Duration readTimeoutFor(String clientName) {
        String key = "clients." + clientName + ".read-timeout";
        return environment.getProperty(
                key, Duration.class, Duration.ofSeconds(3));
    }
}
~~~

Suitable when the key is chosen at runtime, such as a client name coming from an internal registry. Constrain the valid set of clients/keys and test the name-selection logic.

### 6.3. Using @ConfigurationProperties

~~~java
@ConfigurationProperties(prefix = "catalog.client")
public record CatalogTimeoutProperties(
        Duration readTimeout,
        Duration connectTimeout,
        int maxAttempts
) {}
~~~

Suitable when properties jointly describe a client and are shared across multiple beans. The bean can be constructor-injected, tested independently, and validated centrally.

### 6.4. Quick Selection Table

| Need | Start with | Reason |
| --- | --- | --- |
| A simple flag or single name in a bean | `@Value` | Short, clear, minimal structure |
| Reading a dynamically determined key | `Environment` | Property name is only known at runtime |
| Getting a group of properties with a shared prefix | `@ConfigurationProperties` | Typed binding and grouped configuration |
| Validating multiple fields together | `@ConfigurationProperties` | Constraints can be attached at object level |
| Needing nested objects, lists, or maps | `@ConfigurationProperties` | Supports structured binding |
| Inspecting profiles or property sources | `Environment` | API exposes environment information |
| Using a fixed SpEL expression | `@Value` | Supports expressions |
| Wanting configuration metadata for IDEs | `@ConfigurationProperties` | Can generate configuration metadata |

There is no rule forcing an application to use only one mechanism. An application can use `@ConfigurationProperties` for client groups, `@Value` for a standalone flag, and `Environment` for a dynamic lookup case. What matters is that each usage has a clear purpose and does not create multiple sources of truth for the same property.

## 7. Configuration Sources and Precedence Still Apply to All Three

Whether using `@Value`, `Environment`, or `@ConfigurationProperties`, the resolved value still depends on active configuration sources. For example:

- `application.yml` provides the default timeout.
- `application-production.yml` overrides the timeout for production.
- Environment variables override values according to deployment settings.
- Command-line arguments can take higher precedence for a specific run.
- Spring Cloud Config or custom property sources can supply remote configuration.

Example:

~~~yaml
catalog:
  client:
    read-timeout: 3s
~~~

In production:

~~~yaml
catalog:
  client:
    read-timeout: 1500ms
~~~

If the `CATALOG_CLIENT_READTIMEOUT` environment variable is also provided, the final value depends on property source precedence. The different ways of reading configuration do not pick different sources on their own; they all read from the Environment or binder that has already aggregated those sources.

Avoid placing the same property in too many places without reason. When conflicts occur, know the effective value and which source supplied it. Actuator `env`/`configprops` can assist diagnostics if exposed and secured properly.

## 8. Typed Configuration in Spring Cloud Applications

Spring Cloud properties are typically groups of related settings:

~~~yaml
spring:
  application:
    name: order-service

catalog:
  client:
    base-url: "https://catalog.internal"
    connect-timeout: 1s
    read-timeout: 3s
    max-attempts: 2

discovery:
  client:
    prefer-same-zone: true
    zone: ap-southeast
~~~

You can use `@ConfigurationProperties` to bind application-owned groups like `catalog.client`. Standard Spring Boot/Spring Cloud properties must still adhere to the exact prefixes and types defined by the libraries. Do not invent key names and assume a starter will read them automatically.

### 8.1. Do Not Confuse Typed Configuration with Refresh

`@ConfigurationProperties` solves **how to bind structured data**. It does not automatically make configuration change immediately when a file or Config Server is updated.

In Spring Cloud Context, `@RefreshScope` and the refresh mechanism allow certain beans to be recreated after the Environment refreshes. However, you must verify which beans are refreshed, which property sources were updated, and which clients/connections must be rebuilt. Using typed configuration does not enable refresh by itself.

### 8.2. Be Careful with Secrets

Typed configuration can hold URIs, usernames, or connection parameters, but secrets should not be stored in committed configuration files. Retrieve credentials from a secret manager, environment variables, or mounted secret files. Never expose secrets through logs, Actuator, or exception messages.

## 9. Testing Each Mechanism

Tests should verify both resolved values and behavior when configuration is missing or invalid.

### 9.1. Testing @ConfigurationProperties

`ApplicationContextRunner` lets you spin up a lightweight Spring context with specific properties:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsTypedValues() {
        runner.withPropertyValues(
                "catalog.client.read-timeout=1500ms",
                "catalog.client.max-attempts=2")
            .run(context -> {
                CatalogClientProperties properties =
                        context.getBean(CatalogClientProperties.class);

                assertThat(properties.readTimeout())
                        .isEqualTo(Duration.ofMillis(1500));
                assertThat(properties.maxAttempts()).isEqualTo(2);
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogClientProperties.class)
    static class TestConfig {
    }
}
~~~

This test does not need to boot the full application or connect to a Config Server. It focuses on verifying that the binder converts values to the right types. If the configuration class has validation, you can add tests with invalid values and assert that the context fails to start.

### 9.2. Testing @Value

Use `@SpringBootTest(properties = ...)` or a small context to supply test properties. Verify present values, missing keys with fallbacks, and empty strings if allowed by business logic. Do not test only the happy path.

### 9.3. Testing Environment

You can use `MockEnvironment` in unit tests for components that only read properties:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class EndpointResolverTest {

    @Test
    void readsEndpointByDynamicKey() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty(
                        "services.catalog.base-url",
                        "https://catalog.test");

        String endpoint = environment.getProperty(
                "services.catalog.base-url");

        assertThat(endpoint).isEqualTo("https://catalog.test");
    }
}
~~~

If code selects keys dynamically, also test invalid key names, missing properties, and empty values. This test does not prove that profiles, Config Data, or a remote Config Server are configured properly; those flows require dedicated integration tests.

## 10. Common Pitfalls and How to Avoid Them

1. **Overusing `@Value`:** constructors and classes become long and hard to maintain; group related properties with `@ConfigurationProperties`.
2. **Using `Environment` for all configuration:** code has to read and validate many keys manually; use it only when dynamic access or Environment inspection is truly needed.
3. **Forgetting to register `@ConfigurationProperties`:** check `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
4. **Wrong prefix or key name:** check the prefix, kebab-case, and YAML structure; write binding tests.
5. **Using primitives when you need to distinguish missing from false/zero:** use wrapper types or explicit default rules.
6. **Skipping validation for URLs/timeouts/retries:** add constraints and test invalid configuration at startup.
7. **Assuming every empty string means missing:** check null, empty, and blank according to business semantics.
8. **Using SpEL unnecessarily:** prefer simple placeholders; use fixed expressions only when genuinely needed.
9. **Assuming typed binding auto-refreshes:** design the refresh mechanism and bean lifecycle separately.
10. **Confusing custom properties with starter properties:** only keys read by your code or the library have any effect.

## 11. Selection and Implementation Workflow

When adding configuration for a component in Spring Cloud, you can follow this sequence:

1. Determine whether the data is a single property, a structured group, or a dynamically determined key.
2. Use `@Value` for a few simple values; use `Environment` when dynamic lookup is required; use `@ConfigurationProperties` for configuration groups.
3. Define explicit types such as `Duration`, `URI`, `DataSize`, enums, lists, or nested records.
4. Register the configuration bean and add validation for required values.
5. Define configuration sources, profiles, and precedence order for local/test/production.
6. Do not commit secrets; use an appropriate secret source.
7. Write tests for binding, fallbacks, empty values, and invalid configuration.
8. If runtime refresh is needed, design the refresh mechanism separately and verify bean/client recreation.
9. Verify compatible Spring Boot/Spring Cloud versions and dependencies.

**Key takeaway:** `@Value` fits a few simple values; `Environment` fits flexible property queries when keys are decided at runtime; `@ConfigurationProperties` fits a typed, structured, validated configuration group. All three rely on Spring's configuration sources, so they still follow profiles, property source precedence, and configuration loading lifecycles. Choosing the mechanism based on data shape and control requirements keeps Spring Cloud configuration clear, testable, and easy to operate.
