# Declaring Base Configuration in application.yml

> **Chapter:** Initialization  
> **Module:** SPRING_CLOUD_CORE

A Spring Boot application typically runs across multiple environments: developer workstations, testing, staging, and production. The source code may stay the same, while the HTTP port, application name, dependent service addresses, timeouts, and connection details vary. **Externalized configuration** lets you move these values out of Java code so the application receives them from appropriate configuration sources.

In the Spring Cloud ecosystem, configuration also defines the application name, discovery parameters, service endpoints, and integration behavior. This lesson focuses on declaring base configuration with **`application.yml`**, how Spring Boot loads and overrides values, how to bind structured configuration into Java, and key considerations when the application uses Spring Cloud Context or Spring Cloud Config.

## 1. What Role Does `application.yml` Play?

`application.yml` is a YAML configuration file that Spring Boot automatically looks for in default configuration locations. It holds hierarchical property pairs. Spring Boot reads these properties into the application's configuration environment (`Environment`), where components can access them via binding or placeholders.

Minimal example:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
~~~

The configuration above has two main properties:

- `server.port`: the HTTP port used by the embedded server.
- `spring.application.name`: the logical name of the Spring application.

In a Spring Cloud project, the application name is commonly used by discovery integrations as the default service ID or part of registration metadata. Exact behavior depends on the provider and its configuration; merely setting `spring.application.name` **does not install a registry or create a complete discovery system**.

### 1.1. YAML Structure and Writing Rules

YAML represents structure through indentation. Spring Boot translates that structure into hierarchical property keys, for example:

| YAML | Property key |
| --- | --- |
| `server.port: 8080` | `server.port` |
| `spring.application.name: order-service` | `spring.application.name` |
| `catalog.client.connect-timeout: 2s` | `catalog.client.connect-timeout` |

Recommended rules to follow:

- Use spaces for indentation, consistently two spaces per level; never use tabs.
- Use `:` to separate a property name from its value.
- Use `-` to declare list elements.
- Comments may follow `#`, but enclose values in quotes if `#` is part of the value itself.
- Prefer kebab-case property names, such as `connect-timeout`, to align with Spring Boot's relaxed binding rules.
- Quote strings containing special characters, `:`, `#`, or formats that YAML might misinterpret as another data type when necessary.
- Avoid declaring the same key twice at the same level; duplicate keys can cause parsers to reject the file or make configuration confusing.

Example with objects, lists, and data types:

~~~yaml
catalog:
  client:
    enabled: true
    base-url: "http://localhost:8090"
    connect-timeout: 2s
    max-attempts: 3
    supported-regions:
      - north
      - south
~~~

The values `true`, `3`, and `2s` can be bound to boolean, integer, and `Duration`. There is no need to make everything a string in Java; let the binder convert values into supported target types.

## 2. Declaring Foundational Spring Boot and Spring Cloud Properties

A base `application.yml` can group configuration by responsibility:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  application:
    name: order-service
  lifecycle:
    timeout-per-shutdown-phase: 20s

catalog:
  client:
    base-url: "http://localhost:8090"
    connect-timeout: 2s
    read-timeout: 5s
    max-attempts: 2

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
~~~

In this example:

- `server.port` sets the HTTP port.
- `server.shutdown: graceful` enables the embedded server's graceful shutdown mechanism.
- `spring.application.name` sets the application name.
- `spring.lifecycle.timeout-per-shutdown-phase` sets the timeout per shutdown phase.
- `catalog.client.*` is a custom application-defined namespace grouping configuration for the catalog client.
- `management.endpoints.web.exposure.include` specifies Actuator endpoints exposed over the web; this example requires Spring Boot Actuator.

Properties under custom application-defined namespaces such as `catalog.client.*` have no effect unless code or a library reads them. In contrast, standard properties like `server.port` are consumed by Spring Boot and its corresponding auto-configurations.

**Organization principle:** group related properties under a meaningful namespace; separate framework configuration (`spring.*`, `server.*`, `management.*`) from business or client configuration owned by the application.

## 3. Reading Configuration in Java

There are two common ways to read configuration values: `@Value` for an individual value and `@ConfigurationProperties` for a structured group of properties.

### 3.1. `@Value` for a Single Property

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ApplicationIdentity {

    private final String applicationName;

    public ApplicationIdentity(
            @Value("${spring.application.name:unknown-service}") String applicationName) {
        this.applicationName = applicationName;
    }

    public String applicationName() {
        return applicationName;
    }
}
~~~

The expression `${spring.application.name:unknown-service}` reads `spring.application.name`; if the property does not exist, the default value is `unknown-service`.

`@Value` is convenient for a few small values. When there are multiple related properties, using `@ConfigurationProperties` groups them into a clear type that is easier to test and validate.

### 3.2. `@ConfigurationProperties` for a Configuration Group

For the `catalog.client` namespace, you can define a record:

~~~java
import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Min(1) int maxAttempts
) {}
~~~

Spring Boot needs the configuration type registered so the binder creates a bean. You can enable scanning on the application class:

~~~java
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

Or use `@EnableConfigurationProperties(CatalogClientProperties.class)` on a configuration class if you prefer explicit registration.

Key points to understand:

- `prefix = "catalog.client"` specifies the namespace to bind.
- `URI` and `Duration` are suitable types for URLs and durations; Spring Boot provides built-in conversions for these common types.
- `@Validated` integrates with Jakarta Bean Validation to check constraints during binding, provided a compatible validation dependency is present.
- `@NotNull` requires a value to be present; `@Min(1)` requires at least one attempt.
- For a record with a single constructor, Spring Boot supports constructor binding without needing `@ConstructorBinding` in typical cases.

If configuration is missing or violates type/validation constraints, the application can fail immediately at startup. This is usually preferable to letting errors surface later during a production request.

### 3.3. Using the Configuration Bean

A service can receive the configuration bean via constructor injection:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogClientSettings {

    private final CatalogClientProperties properties;

    public CatalogClientSettings(CatalogClientProperties properties) {
        this.properties = properties;
    }

    public String baseUrl() {
        return properties.baseUrl().toString();
    }
}
~~~

This dependency injection pattern makes it clear which components require catalog configuration. In tests, you can supply a different set of properties without modifying business code.

## 4. Placeholders, Default Values, and Environment Variables

Machine-specific or environment-specific values should not be hardcoded in Java. `application.yml` supports placeholders to pull values from other property sources and supply defaults:

~~~yaml
server:
  port: ${SERVER_PORT:8080}

spring:
  application:
    name: ${APP_NAME:order-service}

catalog:
  client:
    base-url: ${CATALOG_BASE_URL:http://localhost:8090}
    connect-timeout: ${CATALOG_CONNECT_TIMEOUT:2s}
~~~

Syntax:

- `${NAME}`: reads property `NAME`; if absent, resolution may fail depending on where it is used.
- `${NAME:default}`: uses `default` if the property is not provided.

You can set environment variables when running the application:

~~~powershell
$env:SERVER_PORT = "8180"
$env:APP_NAME = "order-service"
$env:CATALOG_BASE_URL = "https://catalog.internal"
java -jar order-service.jar
~~~

Or on Linux/macOS:

~~~bash
SERVER_PORT=8180 APP_NAME=order-service \
CATALOG_BASE_URL=https://catalog.internal \
java -jar order-service.jar
~~~

Spring Boot applies relaxed binding to environment variable names. The standard rule is uppercase letters, replacing dots with underscores, and removing hyphens. For example, `spring.application.name` can be set via `SPRING_APPLICATION_NAME`; `catalog.client.connect-timeout` can be set via `CATALOG_CLIENT_CONNECTTIMEOUT`.

Values in environment variables are typically read as strings and converted to the target type during binding. Verify variable names against the conversion rules, especially for indexed lists and maps.

### 4.1. Do Not Commit Secrets to Configuration Files

Never place database passwords, tokens, private keys, or production credentials in an `application.yml` committed to Git.

Use environment variables, the deployment platform's secret manager, or secret files mounted into containers. Example configuration referencing variables only:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

Do not set weak default values for production secrets. If a required secret is not provided, having the application fail with a configuration error at startup is much easier to detect than silently running with insecure credentials.

Spring Boot also supports `configtree:` imports for configuration sources mounted as directories, where filenames represent property keys and file contents represent values. This mechanism is useful for secrets mounted as files by container platforms; verify the path and read permissions of the application process.

## 5. Environment-Specific Configuration with Profiles

An application often needs different values in local, test, and production environments. **Spring Profiles** allow activating a group of settings by environment name.

### 5.1. Separating `application.yml` and `application-{profile}.yml`

Common file layout:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-prod.yml
~~~

Common file:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

catalog:
  client:
    connect-timeout: 2s
    read-timeout: 5s
~~~

`application-local.yml`:

~~~yaml
server:
  port: 8081

catalog:
  client:
    base-url: "http://localhost:8090"
~~~

`application-prod.yml`:

~~~yaml
server:
  port: 8080

catalog:
  client:
    base-url: "https://catalog.internal"
    connect-timeout: 800ms
    read-timeout: 2s
~~~

When the `prod` profile is active, Spring Boot loads both the common configuration and the corresponding profile configuration. Properties in profile-specific configs can override matching keys in the common configuration.

Activating a profile via an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar order-service.jar
~~~

Or via command-line arguments:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

Do not default to the production profile inside the packaged configuration file if the same artifact must be deployed across multiple environments. The deployment environment should determine the active profile.

### 5.2. Using Multiple Documents in One YAML File

You can place multiple documents in a single `application.yml`, separated by `---`:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

---
spring:
  config:
    activate:
      on-profile: local

catalog:
  client:
    base-url: "http://localhost:8090"

---
spring:
  config:
    activate:
      on-profile: prod

catalog:
  client:
    base-url: "https://catalog.internal"
~~~

A document with `spring.config.activate.on-profile` is only applied when the corresponding profile is active. This approach works well for short configurations; when each environment has many properties, separate files are usually easier to read and maintain.

`spring.profiles.active` and `spring.profiles.include` must be declared in a profile-unconditional document; do not place them inside a document restricted to a single profile. Multiple profiles can be activated together, such as `local,debug`, though conflicts must be checked when multiple sources declare the same property.

### 5.3. Profiles Are Not a Security Mechanism

Profiles are a mechanism for selecting configuration and beans per environment. They do not encrypt secrets, isolate networks, enforce access permissions, or guarantee that production cannot accidentally use local settings. Those safeguards must be enforced by pipelines, deployment platforms, secret managers, and security policies.

## 6. Configuration Sources and Precedence

`application.yml` is only **one of many property sources** that Spring Boot can use. The final value is chosen according to the precedence order of property sources. Higher-precedence sources override lower-precedence ones when the same key is declared.

In a typical application, common sources include:

- Configuration files packaged inside the application (`application.yml`).
- Configuration files external to the JAR/container image.
- Profile-specific configuration files.
- Process environment variables.
- Java system properties, e.g., `-Dserver.port=8180`.
- Command-line arguments, e.g., `--server.port=8181`.
- Configuration sources provided for tests.

Exact ordering depends on the source type and startup context; do not infer it solely from filenames. In particular, test property sources can have high precedence inside a test context. When conflicts arise, inspect the application's actual property sources and the Spring Boot documentation for the exact version in use.

Example where multiple sources declare `server.port`:

| Source | Value |
| --- | ---: |
| `application.yml` | 8080 |
| `application-prod.yml` | 8081 |
| Environment variable `SERVER_PORT` | 8082 |
| Argument `--server.port=8180` | 8180 |

When running with the `prod` profile, environment variable, and command-line argument in the example above, the final value is typically `8180` because command-line arguments have higher precedence than the preceding standard configuration sources.

### 6.1. External Configuration Locations

Spring Boot searches for configuration in default locations, including the classpath and locations external to the application. You can add locations with `spring.config.additional-location` or specify replacement locations with `spring.config.location`.

Important difference:

- `spring.config.additional-location`: adds locations to the default search set.
- `spring.config.location`: specifies the configuration locations to search, replacing the default locations.

These properties must be supplied early enough for Config Data loading to use them, usually via environment variables, system properties, or command-line arguments. If you want to extend a packaged image's configuration while keeping internal defaults, `additional-location` is usually the better choice.

Example:

~~~bash
java -jar order-service.jar \
  --spring.config.additional-location=optional:file:./config/
~~~

The `optional:` prefix lets the application continue if the specified location does not exist. If the configuration is mandatory, avoid `optional:` because a missing-file error could be masked.

## 7. Loading Additional Configuration with `spring.config.import`

Spring Boot Config Data supports importing additional configuration sources directly inside `application.yml`.

Example importing an external file:

~~~yaml
spring:
  config:
    import: "optional:file:./config/extra.yml"
~~~

The imported file enters the configuration environment according to Config Data ordering rules. Use `optional:` when the source is non-mandatory; omit `optional:` if the application must fail when the source is unreachable.

### 7.1. Connecting to Spring Cloud Config Server

In an application using Spring Cloud Config, you can import configuration from Config Server:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://localhost:8888"
~~~

The application needs a Config Client dependency compatible with the Spring Boot and Spring Cloud release train in use. The application name, profiles, and labels can be used by Config Server to return the matching configuration set.

If Config Server is a required source for correct operation, remove `optional:` so the application fails fast when configuration cannot be loaded. If running with local configuration when the server is unavailable is permitted, `optional:` can be used, but fallback behavior must be carefully evaluated to avoid starting with unsafe configuration.

Do not confuse **Config Server** with a **service registry**: Config Server distributes configuration properties; a registry/discovery system manages service instance information. They solve different problems, even though a system may use both.

## 8. Structured Configuration for Service Communication

In Spring Cloud, many properties relate to inter-service communication. They can be organized under dedicated namespaces:

~~~yaml
catalog:
  client:
    base-url: "https://catalog.internal"
    connect-timeout: 1s
    read-timeout: 3s
    max-attempts: 2

inventory:
  discovery:
    service-id: inventory-service
  client:
    connect-timeout: 500ms
    read-timeout: 2s
~~~

Benefits:

- Each configuration group has a clear owner.
- Easy to bind into independent `@ConfigurationProperties` classes.
- Individual keys can be overridden per profile or environment.
- Constraints can be validated at startup.
- Reduces scattering `@Value` and property keys across business classes.

Do not assume custom properties like `inventory.discovery.service-id` are automatically read by Spring Cloud Commons. If the application intends to use it, code must bind and pass that value to the appropriate component—or use the standard property supported by the specific integration.

### 8.1. Configuration Does Not Replace Discovery

A fixed `base-url` works well when calling a stable endpoint or gateway. If you want to call by service ID and have Spring Cloud LoadBalancer pick an instance, the HTTP client must be integrated with load balancing and a discovery source must supply the corresponding instances.

Example calling by service ID:

~~~java
WebClient client = loadBalancedBuilder.build();

client.get()
      .uri("http://inventory-service/stock/{sku}", sku);
~~~

In this example, `inventory-service` is a logical name. Service ID resolution requires `@LoadBalanced` integration and Spring Cloud LoadBalancer; it does not work automatically simply because YAML contains an `inventory.discovery.service-id` key.

## 9. Changing Configuration While the Application Is Running

By default, `application.yml` is read during application startup. Editing the file on disk **does not mean running beans will immediately pick up new values**.

Distinguish three separate steps:

1. **Changing the configuration source:** updating environment variables, files, or Config Server.
2. **Reloading/refreshing the application environment:** triggering a mechanism for the application to observe new properties, depending on the source type and integration.
3. **Applying new values to beans:** beans must re-read values or be recreated according to a supported mechanism.

Spring Cloud Context provides mechanisms such as `@RefreshScope` and refresh events for cases requiring refreshable beans. Example:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class CatalogEndpoint {

    private final String baseUrl;

    public CatalogEndpoint(
            @Value("${catalog.client.base-url}") String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String baseUrl() {
        return baseUrl;
    }
}
~~~

When an appropriate refresh mechanism is triggered, beans in refresh scope can be recreated to read the new values. However:

- `@RefreshScope` does not automatically watch for file edits.
- Not every bean or every piece of state can be refreshed safely.
- Existing connections, thread pools, or created clients may require their own update strategies.
- Triggering refresh depends on endpoints/events and the application's security setup.
- Changing configuration is not equivalent to changing source code or deploying a new application version.

Do not expose refresh endpoints to untrusted networks. If using Spring Cloud Config Monitor/Bus or another refresh mechanism, configure proper authentication, authorization, and event distribution flows.

## 10. Testing Configuration

Configuration is part of application behavior, so both binding and override values should be tested.

### 10.1. Overriding Properties in Tests

With Spring Boot Test, properties can be passed directly:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "catalog.client.base-url=http://localhost:9999",
    "catalog.client.connect-timeout=250ms",
    "catalog.client.read-timeout=1s",
    "catalog.client.max-attempts=1"
})
class CatalogClientPropertiesTest {

    @Autowired
    CatalogClientProperties properties;

    @Test
    void bindsConfiguredValues() {
        assertThat(properties.baseUrl().toString())
                .isEqualTo("http://localhost:9999");
        assertThat(properties.connectTimeout().toMillis())
                .isEqualTo(250);
        assertThat(properties.maxAttempts()).isEqualTo(1);
    }
}
~~~

This test verifies that the binder converts values into the expected Java types. Ensure the test context enables `@ConfigurationPropertiesScan` or registers the configuration class.

### 10.2. Configuration Troubleshooting Checklist

| Situation | What to check |
| --- | --- |
| Application uses the wrong port | `server.port`, environment variables, command line, and active profiles |
| Configuration bean is not created | `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Property fails to bind | Prefix, key name, data type, environment variable name, and YAML indentation |
| Profile does not apply | `spring.profiles.active`, filename, and `spring.config.activate.on-profile` |
| Value unexpectedly overridden | Higher-precedence property sources and external configuration sources |
| Cannot fetch configuration from Config Server | Config Client dependency, URL, `spring.config.import`, network, and profile/label |
| New value has no effect | When the bean bound, whether a refresh event ran, and whether the bean supports refresh |
| Application runs with an empty secret | Placeholder, secret source, file read permissions, and startup validation rules |

When diagnosing issues, inspect the environment and property sources of the exact process. Avoid logging full configurations or secrets. If using Actuator to inspect `env`/`configprops`, expose them only where needed, keep sanitization enabled, and protect them with authentication/authorization.

## 11. Common Mistakes and How to Avoid Them

1. **Wrong indentation level:** YAML may still be valid while placing the property under a different namespace. Verify key structure after parsing and binding.
2. **Using tabs:** YAML generally rejects tabs for indentation. Use spaces.
3. **Assuming editing a file auto-refreshes beans:** configuration is typically loaded at startup; use a proper refresh mechanism or restart.
4. **Confusing application name with a registry:** `spring.application.name` supplies the name; discovery integration and a registry or instance source are still needed.
5. **Putting secrets in Git:** move secrets to a securely managed store and grant read access to the application.
6. **Using profiles as a security substitute:** profiles only select configuration/beans, not isolation or authorization.
7. **Using `optional:` for mandatory sources:** the application might start missing critical config; use it only when an explicit fallback exists.
8. **Declaring custom properties without binding them:** Spring Boot does not assume every YAML key is active configuration; code or a library must read it.
9. **Not managing Boot/Cloud versions:** Config Client, Context, and starters must belong to a release train compatible with Spring Boot.

## 12. Recommended Configuration Initialization Workflow

When starting a Spring Boot service with Spring Cloud, you can follow this order:

1. Set `spring.application.name` and truly essential foundational properties.
2. Define application-specific configuration groups, e.g., `catalog.client.*`.
3. Bind property groups to `@ConfigurationProperties`; add validation for required fields and valid bounds.
4. Set safe defaults without embedding production secrets or production URLs into the artifact.
5. Create profiles or external configuration sources for local, test, and production.
6. Choose how configuration is loaded from files, environment variables, Config Server, or config trees based on infrastructure.
7. Test binding, overrides, profiles, and missing-configuration scenarios.
8. Add refresh scope only when runtime updates are required and refresh-safe beans have been identified.
9. Double-check Spring Cloud dependencies against the release train compatible with Spring Boot.

**Key takeaway:** `application.yml` is a convenient starting point for declaring structured configuration. Spring Boot loads those values into `Environment`, binds them to beans or resolves placeholders, and combines them with profiles and external configuration sources according to precedence rules. In Spring Cloud, distinguish between application configuration, centralized configuration, discovery, and refresh; each mechanism has its own lifecycle and responsibility.
